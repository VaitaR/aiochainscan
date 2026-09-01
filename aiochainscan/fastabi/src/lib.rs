use ethers::abi::{Abi, Function, Token};
use ethers::utils::keccak256;
use mini_moka::sync::Cache;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyAny};
use pythonize::depythonize;
use twox_hash::XxHash64;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::sync::{Arc, OnceLock};
use thiserror::Error;
use arrow::array::{ArrayRef, StringArray};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use pyo3_arrow::PyRecordBatch;

const ABI_CACHE_CAPACITY: usize = 1000;  // Maximum number of ABIs to cache

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

// Lock-free, thread-safe ABI cache (ready for Python 3.13+ no-GIL)
static ABI_CACHE: OnceLock<Cache<u64, Arc<AbiData>>> = OnceLock::new();

// Lock-free micro-cache for last decode_input call
// Uses DashMap with a single key for atomic read/write without Mutex
static LAST_INPUT_CACHE: OnceLock<dashmap::DashMap<u8, (u64, u64, String)>> = OnceLock::new();

fn get_abi_cache() -> &'static Cache<u64, Arc<AbiData>> {
    ABI_CACHE.get_or_init(|| {
        Cache::builder()
            .max_capacity(ABI_CACHE_CAPACITY as u64)
            .build()
    })
}

fn get_last_input_cache() -> &'static dashmap::DashMap<u8, (u64, u64, String)> {
    LAST_INPUT_CACHE.get_or_init(|| dashmap::DashMap::with_capacity(1))
}

#[derive(Clone)]
struct AbiData {
    selector_map: HashMap<[u8; 4], Function>,
}

fn calculate_abi_hash(abi_json: &str) -> u64 {
    let mut hasher = XxHash64::default();
    abi_json.hash(&mut hasher);
    hasher.finish()
}

fn calculate_abi_hash_memoized(abi_json: &str) -> u64 {
    // Always hash by content. Never cache by pointer/length because
    // Python allocators can reuse freed addresses for different strings.
    calculate_abi_hash(abi_json)
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
    let cache = get_abi_cache();
    let abi_hash = calculate_abi_hash_memoized(abi_json);

    // Lock-free get (mini-moka is thread-safe)
    if let Some(cached) = cache.get(&abi_hash) {
        return Ok(cached);
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
        selector_map,
    });

    // Lock-free insert (mini-moka handles eviction internally)
    cache.insert(abi_hash, Arc::clone(&abi_data));
    Ok(abi_data)
}

fn get_abi_data_direct(py_abi: &Bound<'_, PyAny>) -> PyResult<Arc<AbiData>> {
    let cache = get_abi_cache();

    // Parse ABI directly from Python object
    let abi: Abi = depythonize(py_abi).map_err(|e| {
        FastAbiError::InvalidAbi(format!("Failed to depythonize ABI: {}", e))
    })?;

    // Build a canonical signature list for a stable cache key
    let mut canonical_sigs: Vec<String> = abi
        .functions()
        .map(|function| {
            let input_types: Vec<String> = function
                .inputs
                .iter()
                .map(|input| input.kind.to_string())
                .collect();
            format!("{}({})", function.name, input_types.join(","))
        })
        .collect();
    canonical_sigs.sort_unstable();
    let abi_key = canonical_sigs.join(";");
    let abi_hash = calculate_abi_hash(&abi_key);

    // Lock-free get (mini-moka is thread-safe)
    if let Some(cached) = cache.get(&abi_hash) {
        return Ok(cached);
    }

    // Build selector map
    let mut selector_map = HashMap::new();
    for function in abi.functions() {
        let selector = calculate_function_selector(function);
        selector_map.insert(selector, function.clone());
    }

    let abi_data = Arc::new(AbiData {
        selector_map,
    });

    // Lock-free insert (mini-moka handles eviction internally)
    cache.insert(abi_hash, Arc::clone(&abi_data));
    Ok(abi_data)
}

/// Decode a single transaction input (cached ABI)
/// Returns JSON string to avoid GIL blocking during Python object creation
#[pyfunction]
fn decode_one(
    py: Python<'_>,
    calldata: &[u8],
    abi_json: &str,
) -> PyResult<String> {
    if calldata.len() < 4 {
        return Ok(serde_json::json!({
            "function_name": "",
            "decoded_data": {}
        }).to_string());
    }

    let abi_data = get_abi_data_from_json(abi_json)?;

    // Release GIL for computation and JSON serialization
    let json_result: Result<String, FastAbiError> = py.allow_threads(|| {
        let selector = &calldata[..4];
        let mut selector_array = [0u8; 4];
        selector_array.copy_from_slice(selector);

        // O(1) lookup using cached selector map
        let function = abi_data.selector_map.get(&selector_array)
            .ok_or(FastAbiError::UnknownSelector)?;

        let tokens = function.decode_input(&calldata[4..])
            .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;

        // Build decoded_data map
        let mut decoded_data = serde_json::Map::new();
        for (i, (param, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
            let param_name = if param.name.is_empty() {
                format!("param_{}", i)
            } else {
                param.name.clone()
            };
            decoded_data.insert(param_name, convert_token_to_json(token));
        }

        let result = serde_json::json!({
            "function_name": function.name,
            "decoded_data": decoded_data
        });

        Ok(result.to_string())
    });

    json_result.map_err(|e| e.into())
}

/// ULTRA-FAST: Decode many transactions returning raw tuples as JSON
/// Returns JSON string: [[function_name, [param1, param2, ...]], ...]
#[pyfunction]
fn decode_many_raw(
    py: Python<'_>,
    calldatas: Vec<Vec<u8>>,
    abi_json: &str,
) -> PyResult<String> {
    let abi_data = get_abi_data_from_json(abi_json)?;

    // Release GIL and process sequentially.
    // Python side already parallelizes with asyncio.to_thread, so additional
    // internal Rayon parallelism causes thread oversubscription.
    let json_result: Result<String, FastAbiError> = py.allow_threads(|| {
        let process_calldata = |calldata: &[u8]| -> serde_json::Value {
            if calldata.len() < 4 {
                return serde_json::json!(["", []]);
            }
            let selector = &calldata[..4];
            let mut selector_array = [0u8; 4];
            selector_array.copy_from_slice(selector);
            let function = match abi_data.selector_map.get(&selector_array) {
                Some(f) => f,
                None => return serde_json::json!(["", []]),
            };
            let tokens = match function.decode_input(&calldata[4..]) {
                Ok(t) => t,
                Err(_) => return serde_json::json!(["", []]),
            };

            let params: Vec<serde_json::Value> = tokens.iter()
                .map(convert_token_to_json)
                .collect();

            serde_json::json!([function.name, params])
        };

        let results: Vec<serde_json::Value> =
            calldatas.iter().map(|c| process_calldata(c)).collect();

        serde_json::to_string(&results)
            .map_err(|e| FastAbiError::DecodeError(format!("JSON serialization failed: {}", e)))
    });

    json_result.map_err(|e| e.into())
}

/// ULTIMATE PERFORMANCE: Return flat lists as JSON
/// Returns JSON string: [[function_name, param1, param2, ...], ...]
#[pyfunction]
fn decode_many_flat(
    py: Python<'_>,
    calldatas: Vec<Vec<u8>>,
    abi_json: &str,
) -> PyResult<String> {
    let abi_data = get_abi_data_from_json(abi_json)?;

    // Release GIL and do ALL computation in parallel including JSON serialization
    let json_result: Result<String, FastAbiError> = py.allow_threads(|| {
        let results: Vec<serde_json::Value> = calldatas
            .iter()
            .map(|calldata| {
                if calldata.len() < 4 {
                    return serde_json::json!([""]);
                }

                let selector = &calldata[..4];
                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(selector);

                // O(1) lookup using cached selector map
                let function = match abi_data.selector_map.get(&selector_array) {
                    Some(f) => f,
                    None => return serde_json::json!([""]),
                };

                let tokens = match function.decode_input(&calldata[4..]) {
                    Ok(t) => t,
                    Err(_) => return serde_json::json!([""]),
                };

                // Build flat array: [function_name, param1, param2, ...]
                let mut result = vec![serde_json::Value::String(function.name.clone())];
                for token in tokens.iter() {
                    result.push(convert_token_to_json(token));
                }

                serde_json::Value::Array(result)
            })
            .collect();

        serde_json::to_string(&results)
            .map_err(|e| FastAbiError::DecodeError(format!("JSON serialization failed: {}", e)))
    });

    json_result.map_err(|e| e.into())
}

/// Decode a single transaction input (NO JSON - direct Python ABI)
/// Returns JSON string to avoid GIL blocking during Python object creation
#[pyfunction]
fn decode_one_direct(
    py: Python<'_>,
    calldata: &[u8],
    py_abi: &Bound<'_, PyAny>,
) -> PyResult<String> {
    if calldata.len() < 4 {
        return Ok(serde_json::json!({
            "function_name": "",
            "decoded_data": {}
        }).to_string());
    }

    let abi_data = get_abi_data_direct(py_abi)?;

    // Release GIL for computation and JSON serialization
    let json_result: Result<String, FastAbiError> = py.allow_threads(|| {
        let selector = &calldata[..4];
        let mut selector_array = [0u8; 4];
        selector_array.copy_from_slice(selector);

        // O(1) lookup using cached selector map
        let function = abi_data.selector_map.get(&selector_array)
            .ok_or(FastAbiError::UnknownSelector)?;

        let tokens = function.decode_input(&calldata[4..])
            .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;

        // Build decoded_data map
        let mut decoded_data = serde_json::Map::new();
        for (i, (param, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
            let param_name = if param.name.is_empty() {
                format!("param_{}", i)
            } else {
                param.name.clone()
            };
            decoded_data.insert(param_name, convert_token_to_json(token));
        }

        let result = serde_json::json!({
            "function_name": function.name,
            "decoded_data": decoded_data
        });

        Ok(result.to_string())
    });

    json_result.map_err(|e| e.into())
}

/// Decode multiple transaction inputs in batch with GIL release
/// Returns JSON string to avoid GIL blocking during Python object creation
#[pyfunction]
fn decode_many(
    py: Python<'_>,
    calldatas: Vec<Vec<u8>>,
    abi_json: &str,
) -> PyResult<String> {
    let abi_data = get_abi_data_from_json(abi_json)?;

    // Release GIL and do ALL computation in parallel, including JSON serialization
    let json_result: Result<String, FastAbiError> = py.allow_threads(|| {
        let results: Result<Vec<_>, FastAbiError> = calldatas
            .iter()
            .map(|calldata| {
                if calldata.len() < 4 {
                    return Ok(serde_json::json!({
                        "function_name": "",
                        "decoded_data": {}
                    }));
                }

                let selector = &calldata[..4];
                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(selector);

                // O(1) lookup using cached selector map
                let function = match abi_data.selector_map.get(&selector_array) {
                    Some(f) => f,
                    None => return Ok(serde_json::json!({
                        "function_name": "",
                        "decoded_data": {}
                    })),
                };

                let tokens = match function.decode_input(&calldata[4..]) {
                    Ok(t) => t,
                    Err(_) => return Ok(serde_json::json!({
                        "function_name": "",
                        "decoded_data": {}
                    })),
                };

                // Build decoded_data map
                let mut decoded_data = serde_json::Map::new();
                for (i, (param, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
                    let param_name = if param.name.is_empty() {
                        format!("param_{}", i)
                    } else {
                        param.name.clone()
                    };
                    decoded_data.insert(param_name, convert_token_to_json(token));
                }

                Ok(serde_json::json!({
                    "function_name": function.name,
                    "decoded_data": decoded_data
                }))
            })
            .collect();

        let json_values = results?;
        serde_json::to_string(&json_values)
            .map_err(|e| FastAbiError::DecodeError(format!("JSON serialization failed: {}", e)))
    });

    json_result.map_err(|e| e.into())
}

/// Decode multiple transaction inputs in batch (NO JSON - direct Python ABI)
/// Returns JSON string to avoid GIL blocking during Python object creation
#[pyfunction]
fn decode_many_direct(
    py: Python<'_>,
    calldatas: Vec<Vec<u8>>,
    py_abi: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let abi_data = get_abi_data_direct(py_abi)?;

    // Release GIL and do ALL computation including JSON serialization.
    // Keep Rust path single-threaded to avoid conflict with Python executor threads.
    let json_result: Result<String, FastAbiError> = py.allow_threads(|| {
        let process_calldata = |calldata: &[u8]| -> serde_json::Value {
            if calldata.len() < 4 {
                return serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                });
            }
            let selector = &calldata[..4];
            let mut selector_array = [0u8; 4];
            selector_array.copy_from_slice(selector);
            let function = match abi_data.selector_map.get(&selector_array) {
                Some(f) => f,
                None => return serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                }),
            };
            let tokens = match function.decode_input(&calldata[4..]) {
                Ok(t) => t,
                Err(_) => return serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                }),
            };

            let mut decoded_data = serde_json::Map::new();
            for (i, (param, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
                let param_name = if param.name.is_empty() {
                    format!("param_{}", i)
                } else {
                    param.name.clone()
                };
                decoded_data.insert(param_name, convert_token_to_json(token));
            }

            serde_json::json!({
                "function_name": function.name,
                "decoded_data": decoded_data
            })
        };

        let results: Vec<serde_json::Value> =
            calldatas.iter().map(|c| process_calldata(c)).collect();

        serde_json::to_string(&results)
            .map_err(|e| FastAbiError::DecodeError(format!("JSON serialization failed: {}", e)))
    });

    json_result.map_err(|e| e.into())
}

/// Decode multiple transaction inputs from hex strings (ultimate optimization)
/// Returns JSON string to avoid GIL blocking during Python object creation
#[pyfunction]
fn decode_many_hex(
    py: Python<'_>,
    hex_inputs: Vec<String>,
    abi_json: &str,
) -> PyResult<String> {
    let abi_data = get_abi_data_from_json(abi_json)?;

    // Release GIL and do everything including hex parsing and JSON serialization.
    // Keep Rust path single-threaded to avoid thread-pool oversubscription.
    let json_result: Result<String, FastAbiError> = py.allow_threads(|| {
        let process_hex = |hex_input: &str| -> serde_json::Value {
            let hex_clean = if hex_input.starts_with("0x") { &hex_input[2..] } else { hex_input };
            let calldata = match hex::decode(hex_clean) {
                Ok(b) => b,
                Err(_) => return serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                }),
            };
            if calldata.len() < 4 {
                return serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                });
            }
            let selector = &calldata[..4];
            let mut selector_array = [0u8; 4];
            selector_array.copy_from_slice(selector);
            let function = match abi_data.selector_map.get(&selector_array) {
                Some(f) => f,
                None => return serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                }),
            };
            let tokens = match function.decode_input(&calldata[4..]) {
                Ok(t) => t,
                Err(_) => return serde_json::json!({
                    "function_name": "",
                    "decoded_data": {}
                }),
            };

            let mut decoded_data = serde_json::Map::new();
            for (i, (param, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
                let param_name = if param.name.is_empty() {
                    format!("param_{}", i)
                } else {
                    param.name.clone()
                };
                decoded_data.insert(param_name, convert_token_to_json(token));
            }

            serde_json::json!({
                "function_name": function.name,
                "decoded_data": decoded_data
            })
        };

        let results: Vec<serde_json::Value> =
            hex_inputs.iter().map(|h| process_hex(h)).collect();

        serde_json::to_string(&results)
            .map_err(|e| FastAbiError::DecodeError(format!("JSON serialization failed: {}", e)))
    });

    json_result.map_err(|e| e.into())
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
    // Use global ABI cache and precomputed selector map
    let abi_data = get_abi_data_from_json(abi_json)?;
    let abi_hash = calculate_abi_hash_memoized(abi_json);

    // Fast-path: if exactly same input bytes and ABI as previous call, return cached JSON
    // Hash the data instead of using raw pointer - Python can reuse memory addresses!
    let data_hash = {
        let mut hasher = XxHash64::default();
        data.hash(&mut hasher);
        hasher.finish()
    };
    let last_cache = get_last_input_cache();
    if let Some(entry) = last_cache.get(&0u8) {
        let (d_hash, a_hash, ref cached) = *entry;
        if d_hash == data_hash && a_hash == abi_hash {
            return Ok(cached.clone());
        }
    }

    let mut selector = [0u8; 4];
    selector.copy_from_slice(&data[0..4]);

    if let Some(function) = abi_data.selector_map.get(&selector) {
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
                let out = result.to_string();
                // Update micro-cache with data hash, not pointer
                get_last_input_cache().insert(0u8, (data_hash, abi_hash, out.clone()));
                Ok(out)
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

/// Zero-copy decode: returns Arrow RecordBatch directly to Python/Polars.
/// Columns: "function_name" (Utf8) + one Utf8 column per ABI parameter.
/// All values are stringified for uniform schema across heterogeneous calldata.
#[pyfunction]
fn decode_many_to_arrow(
    py: Python<'_>,
    calldatas: Vec<Vec<u8>>,
    abi_json: &str,
) -> PyResult<PyRecordBatch> {
    let abi_data = get_abi_data_from_json(abi_json)?;
    let n = calldatas.len();

    // First pass: collect all unique parameter names across all functions
    // to build a stable schema
    let mut all_param_names: Vec<String> = Vec::new();
    let mut seen_params: std::collections::HashSet<String> = std::collections::HashSet::new();
    for func in abi_data.selector_map.values() {
        for (i, input) in func.inputs.iter().enumerate() {
            let name = if input.name.is_empty() {
                format!("param_{}", i)
            } else {
                input.name.clone()
            };
            if seen_params.insert(name.clone()) {
                all_param_names.push(name);
            }
        }
    }

    // Build columns — release GIL during heavy computation
    let (func_names, param_columns): (Vec<Option<String>>, Vec<Vec<Option<String>>>) =
        py.allow_threads(|| {
            let mut func_names_col: Vec<Option<String>> = Vec::with_capacity(n);
            let mut param_cols: Vec<Vec<Option<String>>> =
                vec![Vec::with_capacity(n); all_param_names.len()];

            for calldata in &calldatas {
                if calldata.len() < 4 {
                    func_names_col.push(Some(String::new()));
                    for col in &mut param_cols {
                        col.push(None);
                    }
                    continue;
                }

                let mut selector_array = [0u8; 4];
                selector_array.copy_from_slice(&calldata[..4]);

                match abi_data.selector_map.get(&selector_array) {
                    Some(function) => {
                        func_names_col.push(Some(function.name.clone()));

                        let tokens = match function.decode_input(&calldata[4..]) {
                            Ok(t) => t,
                            Err(_) => {
                                for col in &mut param_cols {
                                    col.push(None);
                                }
                                continue;
                            }
                        };

                        // Build a map of param_name → stringified value
                        let mut decoded: HashMap<String, String> = HashMap::new();
                        for (i, (input, token)) in
                            function.inputs.iter().zip(tokens.iter()).enumerate()
                        {
                            let name = if input.name.is_empty() {
                                format!("param_{}", i)
                            } else {
                                input.name.clone()
                            };
                            let value = convert_token_to_json(token).to_string();
                            // Strip surrounding quotes from JSON string values
                            let clean = value.trim_matches('"').to_string();
                            decoded.insert(name, clean);
                        }

                        for (j, param_name) in all_param_names.iter().enumerate() {
                            param_cols[j].push(decoded.get(param_name).cloned());
                        }
                    }
                    None => {
                        func_names_col.push(Some(String::new()));
                        for col in &mut param_cols {
                            col.push(None);
                        }
                    }
                }
            }

            (func_names_col, param_cols)
        });

    // Build Arrow arrays
    let func_name_array: ArrayRef = Arc::new(StringArray::from(func_names));

    let mut fields = vec![Field::new("function_name", DataType::Utf8, false)];
    let mut columns: Vec<ArrayRef> = vec![func_name_array];

    for (i, param_name) in all_param_names.iter().enumerate() {
        let array: ArrayRef = Arc::new(StringArray::from(param_columns[i].clone()));
        fields.push(Field::new(param_name, DataType::Utf8, true));
        columns.push(array);
    }

    let schema = Arc::new(Schema::new(fields));
    let batch = RecordBatch::try_new(schema, columns).map_err(|e| {
        pyo3::exceptions::PyValueError::new_err(format!("Arrow error: {}", e))
    })?;

    Ok(PyRecordBatch::new(batch))
}

/// Keccak-256 digest (Ethereum flavor, distinct from NIST SHA-3-256).
#[pyfunction(name = "keccak256")]
fn keccak256_py<'py>(py: Python<'py>, input: &[u8]) -> Bound<'py, PyBytes> {
    let digest = keccak256(input);
    PyBytes::new_bound(py, &digest)
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
    m.add_function(wrap_pyfunction!(decode_many_to_arrow, m)?)?; // Zero-copy Arrow
    m.add_function(wrap_pyfunction!(keccak256_py, m)?)?; // Hash primitive for selectors/EIP-55
    Ok(())
}
