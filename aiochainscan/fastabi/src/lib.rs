use ethers::abi::{Abi, Function, Token, FunctionExt};
use ethers::utils::keccak256;
use once_cell::sync::OnceCell;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple, PyAny};
use pythonize::depythonize;
use rayon::prelude::*;
use dashmap::DashMap;
use twox_hash::XxHash64;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::sync::Arc;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum FastAbiError {
    #[error("Invalid ABI: {0}")]
    InvalidAbi(String),
    #[error("Decode error: {0}")]
    DecodeError(String),
    #[error("Unknown function selector")]
    UnknownSelector,
}

impl From<FastAbiError> for PyErr {
    fn from(err: FastAbiError) -> PyErr {
        pyo3::exceptions::PyValueError::new_err(err.to_string())
    }
}

// Global ABI cache with selector maps for multiple ABIs
static ABI_CACHE: OnceCell<DashMap<u64, Arc<AbiData>>> = OnceCell::new();

#[derive(Clone)]
struct AbiData {
    abi: Arc<Abi>,
    selector_map: HashMap<[u8; 4], Function>,
}

fn calculate_abi_hash(abi_json: &str) -> u64 {
    let mut hasher = XxHash64::default();
    abi_json.hash(&mut hasher);
    hasher.finish()
}

fn calculate_function_selector(function: &Function) -> [u8; 4] {
    // Create the canonical function signature: "name(type1,type2,...)"
    let input_types: Vec<String> = function.inputs.iter()
        .map(|input| input.kind.to_string())
        .collect();
    let canonical_signature = format!("{}({})", function.name, input_types.join(","));
    
    let hash = keccak256(canonical_signature.as_bytes());
    let mut selector = [0u8; 4];
    selector.copy_from_slice(&hash[0..4]);
    selector
}

fn get_abi_data_from_json(abi_json: &str) -> PyResult<Arc<AbiData>> {
    let cache = ABI_CACHE.get_or_init(|| DashMap::new());
    let abi_hash = calculate_abi_hash(abi_json);
    
    // Check cache first
    if let Some(cached) = cache.get(&abi_hash) {
        return Ok(Arc::clone(&cached));
    }
    
    // Parse ABI and build selector map
    let abi: Abi = serde_json::from_str(abi_json).map_err(|e| {
        FastAbiError::InvalidAbi(format!("Failed to parse ABI: {}", e))
    })?;
    
    let mut selector_map = HashMap::new();
    for function in abi.functions() {
        let selector = calculate_function_selector(function);
        selector_map.insert(selector, function.clone());
    }
    
    let abi_data = Arc::new(AbiData {
        abi: Arc::new(abi),
        selector_map,
    });
    
    // Cache it
    cache.insert(abi_hash, Arc::clone(&abi_data));
    Ok(abi_data)
}

fn get_abi_data_direct(py_abi: &Bound<'_, PyAny>) -> PyResult<Arc<AbiData>> {
    let cache = ABI_CACHE.get_or_init(|| DashMap::new());
    
    // For direct Python objects, we'll use the repr as a simple hash
    let abi_key = py_abi.repr()?.to_string();
    let abi_hash = calculate_abi_hash(&abi_key);
    
    // Check cache first
    if let Some(cached) = cache.get(&abi_hash) {
        return Ok(Arc::clone(&cached));
    }
    
    // Parse ABI directly from Python object
    let abi: Abi = depythonize(py_abi).map_err(|e| {
        FastAbiError::InvalidAbi(format!("Failed to depythonize ABI: {}", e))
    })?;
    
    let mut selector_map = HashMap::new();
    for function in abi.functions() {
        let selector = calculate_function_selector(function);
        selector_map.insert(selector, function.clone());
    }
    
    let abi_data = Arc::new(AbiData {
        abi: Arc::new(abi),
        selector_map,
    });
    
    // Cache it
    cache.insert(abi_hash, Arc::clone(&abi_data));
    Ok(abi_data)
}

// Convert token to raw Python types (optimized)
fn token_to_raw_py(py: Python<'_>, token: Token) -> PyResult<PyObject> {
    match token {
        Token::Address(addr) => {
            // Return as memoryview for zero-copy efficiency
            let addr_bytes = addr.as_bytes();
            let py_bytes = PyBytes::new_bound(py, addr_bytes);
            let memoryview = py.import_bound("builtins")?.call_method1("memoryview", (py_bytes,))?;
            Ok(memoryview.into())
        }
        Token::Uint(uint) => {
            // Return native int when possible, string for very large numbers
            if let Ok(as_u64) = u64::try_from(uint) {
                Ok(as_u64.into_py(py))
            } else {
                Ok(uint.to_string().into_py(py))
            }
        }
        Token::Int(int) => {
            // Return native int when possible
            if let Ok(as_i64) = i64::try_from(int) {
                Ok(as_i64.into_py(py))
            } else {
                Ok(int.to_string().into_py(py))
            }
        }
        Token::Bool(b) => Ok(b.into_py(py)),
        Token::String(s) => Ok(s.into_py(py)),
        Token::Bytes(bytes) => {
            // Return as memoryview for large byte arrays
            if bytes.len() > 32 {  // Only for larger arrays to avoid overhead
                let py_bytes = PyBytes::new_bound(py, &bytes);
                let memoryview = py.import_bound("builtins")?.call_method1("memoryview", (py_bytes,))?;
                Ok(memoryview.into())
            } else {
                Ok(PyBytes::new_bound(py, &bytes).into())
            }
        }
        Token::FixedBytes(bytes) => {
            // Return as memoryview for large byte arrays
            if bytes.len() > 32 {
                let py_bytes = PyBytes::new_bound(py, &bytes);
                let memoryview = py.import_bound("builtins")?.call_method1("memoryview", (py_bytes,))?;
                Ok(memoryview.into())
            } else {
                Ok(PyBytes::new_bound(py, &bytes).into())
            }
        }
        Token::Array(tokens) => {
            let py_items: Result<Vec<_>, _> = tokens.into_iter()
                .map(|token| token_to_raw_py(py, token))
                .collect();
            Ok(PyTuple::new_bound(py, py_items?).into())
        }
        Token::FixedArray(tokens) => {
            let py_items: Result<Vec<_>, _> = tokens.into_iter()
                .map(|token| token_to_raw_py(py, token))
                .collect();
            Ok(PyTuple::new_bound(py, py_items?).into())
        }
        Token::Tuple(tokens) => {
            let py_items: Result<Vec<_>, _> = tokens.into_iter()
                .map(|token| token_to_raw_py(py, token))
                .collect();
            Ok(PyTuple::new_bound(py, py_items?).into())
        }
    }
}

fn token_to_py(py: Python<'_>, token: Token) -> PyResult<PyObject> {
    match token {
        Token::Address(addr) => Ok(format!("0x{:x}", addr).into_py(py)),
        Token::Uint(uint) => {
            // Try to convert to u64 first
            if let Ok(as_u64) = u64::try_from(uint) {
                // If it fits in i64 range, return as int, otherwise as string
                if as_u64 <= i64::MAX as u64 {
                    Ok(as_u64.into_py(py))
                } else {
                    Ok(uint.to_string().into_py(py))
                }
            } else {
                Ok(uint.to_string().into_py(py))
            }
        }
        Token::Int(int) => {
            // For signed integers, try to fit in i64
            if let Ok(as_u64) = u64::try_from(int) {
                if as_u64 <= i64::MAX as u64 {
                    Ok((as_u64 as i64).into_py(py))
                } else {
                    Ok(int.to_string().into_py(py))
                }
            } else {
                Ok(int.to_string().into_py(py))
            }
        }
        Token::Bool(b) => Ok(b.into_py(py)),
        Token::String(s) => Ok(s.into_py(py)),
        Token::Bytes(bytes) => Ok(format!("0x{}", hex::encode(bytes)).into_py(py)),
        Token::FixedBytes(bytes) => Ok(format!("0x{}", hex::encode(bytes)).into_py(py)),
        Token::Array(tokens) => {
            let py_list = PyList::new_bound(py, Vec::<PyObject>::new());
            for token in tokens {
                py_list.append(token_to_py(py, token)?)?;
            }
            Ok(py_list.into())
        }
        Token::FixedArray(tokens) => {
            let py_list = PyList::new_bound(py, Vec::<PyObject>::new());
            for token in tokens {
                py_list.append(token_to_py(py, token)?)?;
            }
            Ok(py_list.into())
        }
        Token::Tuple(tokens) => {
            let py_items: Result<Vec<_>, _> = tokens.into_iter()
                .map(|token| token_to_py(py, token))
                .collect();
            Ok(PyTuple::new_bound(py, py_items?).into())
        }
    }
}

/// Decode a single transaction input (cached ABI)
#[pyfunction]
fn decode_one<'p>(
    py: Python<'p>,
    calldata: &[u8],
    abi_json: &str,
) -> PyResult<Py<PyDict>> {
    if calldata.len() < 4 {
        let result = PyDict::new_bound(py);
        result.set_item("function_name", "")?;
        result.set_item("decoded_data", PyDict::new_bound(py))?;
        return Ok(result.unbind());
    }
    
    let abi_data = get_abi_data_from_json(abi_json)?;
    let selector = &calldata[..4];
    let mut selector_array = [0u8; 4];
    selector_array.copy_from_slice(selector);
    
    // O(1) lookup using cached selector map
    let function = abi_data.selector_map.get(&selector_array)
        .ok_or(FastAbiError::UnknownSelector)?;
    
    let tokens = function.decode_input(&calldata[4..])
        .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;
    
    let result = PyDict::new_bound(py);
    result.set_item("function_name", &function.name)?;
    
    // Decode parameters
    let py_params = PyDict::new_bound(py);
    for (param, token) in function.inputs.iter().zip(tokens) {
        let param_name = if param.name.is_empty() {
            format!("param_{}", py_params.len())
        } else {
            param.name.clone()
        };
        py_params.set_item(param_name, token_to_py(py, token)?)?;
    }
    result.set_item("decoded_data", py_params)?;
    
    Ok(result.unbind())
}

/// ULTRA-FAST: Decode many transactions returning raw tuples (function_name, raw_params_tuple)
#[pyfunction]
fn decode_many_raw<'p>(
    py: Python<'p>,
    calldatas: Vec<Vec<u8>>,
    abi_json: &str,
) -> PyResult<Vec<Py<PyTuple>>> {
    let abi_data = get_abi_data_from_json(abi_json)?;
    
    // Release GIL and do ALL computation in parallel
    let results: Result<Vec<_>, FastAbiError> = py.allow_threads(|| {
        calldatas
            .par_iter()  // PARALLEL processing with rayon
            .map(|calldata| {
                if calldata.len() < 4 {
                    return Ok((String::new(), Vec::new()));
                }
                
                let selector = &calldata[..4];
                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(selector);
                
                // O(1) lookup using cached selector map
                let function = abi_data.selector_map.get(&selector_array)
                    .ok_or(FastAbiError::UnknownSelector)?;
                
                let tokens = function.decode_input(&calldata[4..])
                    .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;
                
                Ok((function.name.clone(), tokens))
            })
            .collect()
    });
    
    // Convert results to raw Python tuples (minimal overhead)
    let decoded_results = results.map_err(FastAbiError::from)?;
    let mut py_results = Vec::new();
    
    for (func_name, tokens) in decoded_results {
        if !func_name.is_empty() {
            // Convert tokens to raw Python objects
            let raw_params: Result<Vec<_>, _> = tokens.into_iter()
                .map(|token| token_to_raw_py(py, token))
                .collect();
            
            let result_tuple = PyTuple::new_bound(py, [
                func_name.into_py(py),
                PyTuple::new_bound(py, raw_params?).into(),
            ]);
            py_results.push(result_tuple.unbind());
        } else {
            // Empty result
            let result_tuple = PyTuple::new_bound(py, [
                "".to_string().into_py(py),
                PyTuple::new_bound(py, Vec::<PyObject>::new()).into(),
            ]);
            py_results.push(result_tuple.unbind());
        }
    }
    
    Ok(py_results)
}

/// ULTIMATE PERFORMANCE: Return ready list[list] without PyTuple wrapping
#[pyfunction]
fn decode_many_flat<'p>(
    py: Python<'p>,
    calldatas: Vec<Vec<u8>>,
    abi_json: &str,
) -> PyResult<Vec<Py<PyList>>> {
    let abi_data = get_abi_data_from_json(abi_json)?;
    
    // Release GIL and do ALL computation in parallel
    let results: Result<Vec<_>, FastAbiError> = py.allow_threads(|| {
        calldatas
            .par_iter()  // PARALLEL processing with rayon
            .map(|calldata| {
                if calldata.len() < 4 {
                    return Ok((String::new(), Vec::new()));
                }
                
                let selector = &calldata[..4];
                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(selector);
                
                // O(1) lookup using cached selector map
                let function = abi_data.selector_map.get(&selector_array)
                    .ok_or(FastAbiError::UnknownSelector)?;
                
                let tokens = function.decode_input(&calldata[4..])
                    .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;
                
                Ok((function.name.clone(), tokens))
            })
            .collect()
    });
    
    // Convert results to flat Python lists (minimal overhead)
    let decoded_results = results.map_err(FastAbiError::from)?;
    let mut py_results = Vec::new();
    
    for (func_name, tokens) in decoded_results {
        if !func_name.is_empty() {
            // Create flat list: [function_name, param1, param2, ...]
            let result_list = PyList::new_bound(py, Vec::<PyObject>::new());
            result_list.append(func_name.into_py(py))?;
            
            // Add parameters directly to the list
            for token in tokens {
                result_list.append(token_to_raw_py(py, token)?)?;
            }
            
            py_results.push(result_list.unbind());
        } else {
            // Empty result - just function name
            let result_list = PyList::new_bound(py, [func_name.into_py(py)]);
            py_results.push(result_list.unbind());
        }
    }
    
    Ok(py_results)
}

/// Decode a single transaction input (NO JSON - direct Python ABI)
#[pyfunction]
fn decode_one_direct<'p>(
    py: Python<'p>,
    calldata: &[u8],
    py_abi: &Bound<'p, PyAny>,
) -> PyResult<Py<PyDict>> {
    if calldata.len() < 4 {
        let result = PyDict::new_bound(py);
        result.set_item("function_name", "")?;
        result.set_item("decoded_data", PyDict::new_bound(py))?;
        return Ok(result.unbind());
    }
    
    let abi_data = get_abi_data_direct(py_abi)?;
    let selector = &calldata[..4];
    let mut selector_array = [0u8; 4];
    selector_array.copy_from_slice(selector);
    
    // O(1) lookup using cached selector map  
    let function = abi_data.selector_map.get(&selector_array)
        .ok_or(FastAbiError::UnknownSelector)?;
    
    let tokens = function.decode_input(&calldata[4..])
        .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;
    
    let result = PyDict::new_bound(py);
    result.set_item("function_name", &function.name)?;
    
    // Decode parameters
    let py_params = PyDict::new_bound(py);
    for (param, token) in function.inputs.iter().zip(tokens) {
        let param_name = if param.name.is_empty() {
            format!("param_{}", py_params.len())
        } else {
            param.name.clone()
        };
        py_params.set_item(param_name, token_to_py(py, token)?)?;
    }
    result.set_item("decoded_data", py_params)?;
    
    Ok(result.unbind())
}

/// Decode multiple transaction inputs in batch with GIL release
#[pyfunction]
fn decode_many<'p>(
    py: Python<'p>,
    calldatas: Vec<Vec<u8>>,
    abi_json: &str,
) -> PyResult<Vec<Py<PyDict>>> {
    let abi_data = get_abi_data_from_json(abi_json)?;
    
    // Release GIL and do heavy computation in parallel
    let results: Result<Vec<_>, FastAbiError> = py.allow_threads(|| {
        calldatas
            .par_iter()  // PARALLEL processing
            .map(|calldata| {
                if calldata.len() < 4 {
                    return Ok((String::new(), Vec::new()));
                }
                
                let selector = &calldata[..4];
                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(selector);
                
                // O(1) lookup using cached selector map
                let function = abi_data.selector_map.get(&selector_array)
                    .ok_or(FastAbiError::UnknownSelector)?;
                
                let tokens = function.decode_input(&calldata[4..])
                    .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;
                
                Ok((function.name.clone(), tokens))
            })
            .collect()
    });
    
    // Convert results to Python objects (with GIL)
    let decoded_results = results.map_err(FastAbiError::from)?;
    let mut py_results = Vec::new();
    
    for (func_name, tokens) in decoded_results {
        let result = PyDict::new_bound(py);
        result.set_item("function_name", &func_name)?;
        
        if !func_name.is_empty() {
            // Find function again to get parameter names
            let function = abi_data.abi.functions()
                .find(|f| f.name == func_name)
                .ok_or(FastAbiError::UnknownSelector)?;
            
            let py_params = PyDict::new_bound(py);
            for (param, token) in function.inputs.iter().zip(tokens) {
                let param_name = if param.name.is_empty() {
                    format!("param_{}", py_params.len())
                } else {
                    param.name.clone()
                };
                py_params.set_item(param_name, token_to_py(py, token)?)?;
            }
            result.set_item("decoded_data", py_params)?;
        } else {
            result.set_item("decoded_data", PyDict::new_bound(py))?;
        }
        
        py_results.push(result.unbind());
    }
    
    Ok(py_results)
}

/// Decode multiple transaction inputs in batch (NO JSON - direct Python ABI)
#[pyfunction]
fn decode_many_direct<'p>(
    py: Python<'p>,
    calldatas: Vec<Vec<u8>>,
    py_abi: &Bound<'p, PyAny>,
) -> PyResult<Vec<Py<PyDict>>> {
    let abi_data = get_abi_data_direct(py_abi)?;
    
    // Release GIL and do heavy computation in parallel
    let results: Result<Vec<_>, FastAbiError> = py.allow_threads(|| {
        calldatas
            .into_iter()
            .map(|calldata| {
                let calldata = &calldata[..];
                if calldata.len() < 4 {
                    return Ok((String::new(), Vec::new()));
                }
                
                let selector = &calldata[..4];
                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(selector);
                
                // O(1) lookup using cached selector map
                let function = abi_data.selector_map.get(&selector_array)
                    .ok_or(FastAbiError::UnknownSelector)?;
                
                let tokens = function.decode_input(&calldata[4..])
                    .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;
                
                Ok((function.name.clone(), tokens))
            })
            .collect()
    });
    
    // Convert results to Python objects (with GIL)
    let decoded_results = results.map_err(FastAbiError::from)?;
    let mut py_results = Vec::new();
    
    for (func_name, tokens) in decoded_results {
        let result = PyDict::new_bound(py);
        result.set_item("function_name", &func_name)?;
        
        if !func_name.is_empty() {
            // Find function again to get parameter names
            let function = abi_data.abi.functions()
                .find(|f| f.name == func_name)
                .ok_or(FastAbiError::UnknownSelector)?;
            
            let py_params = PyDict::new_bound(py);
            for (param, token) in function.inputs.iter().zip(tokens) {
                let param_name = if param.name.is_empty() {
                    format!("param_{}", py_params.len())
                } else {
                    param.name.clone()
                };
                py_params.set_item(param_name, token_to_py(py, token)?)?;
            }
            result.set_item("decoded_data", py_params)?;
        } else {
            result.set_item("decoded_data", PyDict::new_bound(py))?;
        }
        
        py_results.push(result.unbind());
    }
    
    Ok(py_results)
}

/// Decode multiple transaction inputs from hex strings (ultimate optimization)
#[pyfunction]
fn decode_many_hex<'p>(
    py: Python<'p>,
    hex_inputs: Vec<String>,
    abi_json: &str,
) -> PyResult<Vec<Py<PyDict>>> {
    let abi_data = get_abi_data_from_json(abi_json)?;
    
    // Release GIL and do everything including hex parsing
    let results: Result<Vec<_>, FastAbiError> = py.allow_threads(|| {
        hex_inputs
            .into_iter()
            .map(|hex_input| {
                // Parse hex in Rust
                let hex_clean = if hex_input.starts_with("0x") {
                    &hex_input[2..]
                } else {
                    &hex_input
                };
                
                let calldata = hex::decode(hex_clean)
                    .map_err(|e| FastAbiError::DecodeError(format!("Invalid hex: {}", e)))?;
                
                if calldata.len() < 4 {
                    return Ok((String::new(), Vec::new()));
                }
                
                let selector = &calldata[..4];
                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(selector);
                
                // O(1) lookup using cached selector map
                let function = abi_data.selector_map.get(&selector_array)
                    .ok_or(FastAbiError::UnknownSelector)?;
                
                let tokens = function.decode_input(&calldata[4..])
                    .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;
                
                Ok((function.name.clone(), tokens))
            })
            .collect()
    });
    
    // Convert results to Python objects (with GIL)
    let decoded_results = results.map_err(FastAbiError::from)?;
    let mut py_results = Vec::new();
    
    for (func_name, tokens) in decoded_results {
        let result = PyDict::new_bound(py);
        result.set_item("function_name", &func_name)?;
        
        if !func_name.is_empty() {
            let function = abi_data.abi.functions()
                .find(|f| f.name == func_name)
                .ok_or(FastAbiError::UnknownSelector)?;
            
            let py_params = PyDict::new_bound(py);
            for (param, token) in function.inputs.iter().zip(tokens) {
                let param_name = if param.name.is_empty() {
                    format!("param_{}", py_params.len())
                } else {
                    param.name.clone()
                };
                py_params.set_item(param_name, token_to_py(py, token)?)?;
            }
            result.set_item("decoded_data", py_params)?;
        } else {
            result.set_item("decoded_data", PyDict::new_bound(py))?;
        }
        
        py_results.push(result.unbind());
    }
    
    Ok(py_results)
}

/// Legacy JSON-based function for backward compatibility
#[pyfunction]
fn decode_input(input_data: &Bound<'_, PyBytes>, abi_json: &str) -> PyResult<String> {
    let data = input_data.as_bytes();
    
    if data.len() < 4 {
        return Ok(serde_json::json!({
            "function_name": "",
            "decoded_data": {}
        }).to_string());
    }
    
    // Parse ABI from JSON
    let abi: Abi = serde_json::from_str(abi_json)
        .map_err(|e| FastAbiError::InvalidAbi(e.to_string()))?;
    
    let mut function_map = HashMap::new();
    for function in abi.functions() {
        let selector = calculate_function_selector(function);
        function_map.insert(selector, function.clone());
    }
    
    let mut selector = [0u8; 4];
    selector.copy_from_slice(&data[0..4]);
    
    if let Some(function) = function_map.get(&selector) {
        let calldata = &data[4..];
        
        match function.decode_input(calldata) {
            Ok(tokens) => {
                let mut decoded_data = serde_json::Map::new();
                
                for (i, (input, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
                    let param_name = if input.name.is_empty() {
                        format!("param_{}", i)
                    } else {
                        input.name.clone()
                    };
                    decoded_data.insert(param_name, convert_token_to_json(token));
                }
                
                let result = serde_json::json!({
                    "function_name": function.name,
                    "decoded_data": decoded_data
                });
                
                Ok(result.to_string())
            }
            Err(_e) => {
                Ok(serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                }).to_string())
            }
        }
    } else {
        Ok(serde_json::json!({
            "function_name": "",
            "decoded_data": {}
        }).to_string())
    }
}

// Legacy function for JSON conversion
fn convert_token_to_json(token: &Token) -> serde_json::Value {
    match token {
        Token::Address(addr) => serde_json::Value::String(format!("0x{:x}", addr)),
        Token::Uint(uint) => {
            if let Ok(as_u64) = u64::try_from(*uint) {
                if as_u64 <= i64::MAX as u64 {
                    serde_json::Value::Number(serde_json::Number::from(as_u64))
                } else {
                    serde_json::Value::String(uint.to_string())
                }
            } else {
                serde_json::Value::String(uint.to_string())
            }
        }
        Token::Int(int) => {
            if let Ok(as_u64) = u64::try_from(*int) {
                if as_u64 <= i64::MAX as u64 {
                    serde_json::Value::Number(serde_json::Number::from(as_u64 as i64))
                } else {
                    serde_json::Value::String(int.to_string())
                }
            } else {
                serde_json::Value::String(int.to_string())
            }
        }
        Token::Bool(b) => serde_json::Value::Bool(*b),
        Token::String(s) => serde_json::Value::String(s.clone()),
        Token::Bytes(bytes) => serde_json::Value::String(format!("0x{}", hex::encode(bytes))),
        Token::FixedBytes(bytes) => serde_json::Value::String(format!("0x{}", hex::encode(bytes))),
        Token::Array(tokens) => {
            serde_json::Value::Array(tokens.iter().map(convert_token_to_json).collect())
        }
        Token::FixedArray(tokens) => {
            serde_json::Value::Array(tokens.iter().map(convert_token_to_json).collect())
        }
        Token::Tuple(tokens) => {
            serde_json::Value::Array(tokens.iter().map(convert_token_to_json).collect())
        }
    }
}

/// Python module for fast ABI decoding
#[pymodule]
fn aiochainscan_fastabi(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decode_one, m)?)?;
    m.add_function(wrap_pyfunction!(decode_one_direct, m)?)?;
    m.add_function(wrap_pyfunction!(decode_many, m)?)?;
    m.add_function(wrap_pyfunction!(decode_many_direct, m)?)?;
    m.add_function(wrap_pyfunction!(decode_many_raw, m)?)?; // ULTRA-FAST tuples
    m.add_function(wrap_pyfunction!(decode_many_flat, m)?)?; // ULTIMATE flat lists
    m.add_function(wrap_pyfunction!(decode_many_hex, m)?)?;
    m.add_function(wrap_pyfunction!(decode_input, m)?)?; // Legacy
    Ok(())
}