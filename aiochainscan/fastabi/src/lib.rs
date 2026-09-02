use ethers::abi::{Abi, Function, ParamType, Token};
use ethers::utils::keccak256;
use mini_moka::sync::Cache;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyAny};
use pythonize::depythonize;
use twox_hash::XxHash64;
use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use std::iter::repeat;
use std::sync::{Arc, OnceLock};
use thiserror::Error;
#[cfg(feature = "arrow")]
use arrow::array::{ArrayRef, StringArray};
#[cfg(feature = "arrow")]
use arrow::datatypes::{DataType, Field, Schema};
#[cfg(feature = "arrow")]
use arrow::record_batch::RecordBatch;
#[cfg(feature = "arrow")]
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
                .map(|input| format!("{}:{}", input.name, input.kind))
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
// ---------------------------------------------------------------------------
// Canonical-encoding validation
//
// ethabi decodes leniently: it ignores the padding bytes of a static value and
// follows a dynamic offset that points back into the head area. The pure-Python
// floor in aiochainscan/abi_pure.py rejects both, as the ABI spec requires, so
// without this pass the same calldata would decode differently depending on
// whether the Rust extension is installed. Checks are byte-slice comparisons on
// the raw words -- no bignum, so the cost is a few memcmp per static leaf.
// ---------------------------------------------------------------------------

fn is_dynamic_type(param: &ParamType) -> bool {
    match param {
        ParamType::Bytes | ParamType::String | ParamType::Array(_) => true,
        ParamType::FixedArray(inner, _) => is_dynamic_type(inner),
        ParamType::Tuple(types) => types.iter().any(is_dynamic_type),
        _ => false,
    }
}

fn static_size_of(param: &ParamType) -> usize {
    match param {
        ParamType::FixedArray(inner, len) if !is_dynamic_type(inner) => {
            static_size_of(inner) * len
        }
        ParamType::Tuple(types) if !is_dynamic_type(param) => {
            types.iter().map(static_size_of).sum()
        }
        _ => 32,
    }
}

fn head_size_of(param: &ParamType) -> usize {
    if is_dynamic_type(param) {
        32
    } else {
        static_size_of(param)
    }
}

fn word_at(data: &[u8], offset: usize) -> Result<&[u8], String> {
    data.get(offset..offset + 32)
        .ok_or_else(|| format!("truncated at offset {}", offset))
}

fn read_offset(data: &[u8], offset: usize) -> Result<usize, String> {
    let word = word_at(data, offset)?;
    if word[..24].iter().any(|b| *b != 0) {
        return Err(format!("offset word at {} exceeds addressable range", offset));
    }
    let mut buf = [0u8; 8];
    buf.copy_from_slice(&word[24..32]);
    Ok(u64::from_be_bytes(buf) as usize)
}

fn validate_leaf(param: &ParamType, data: &[u8], offset: usize) -> Result<(), String> {
    let word = word_at(data, offset)?;
    match param {
        ParamType::Uint(bits) => {
            let pad = 32 - bits / 8;
            if word[..pad].iter().any(|b| *b != 0) {
                return Err(format!("uint{}: padding is not zero", bits));
            }
        }
        ParamType::Int(bits) => {
            let pad = 32 - bits / 8;
            if pad > 0 {
                let fill = if word[pad] & 0x80 != 0 { 0xffu8 } else { 0x00u8 };
                if word[..pad].iter().any(|b| *b != fill) {
                    return Err(format!("int{}: padding is not the sign extension", bits));
                }
            }
        }
        ParamType::Bool => {
            if word[..31].iter().any(|b| *b != 0) || word[31] > 1 {
                return Err("bool: word is neither 0 nor 1".to_string());
            }
        }
        ParamType::Address => {
            if word[..12].iter().any(|b| *b != 0) {
                return Err("address: padding is not zero".to_string());
            }
        }
        ParamType::FixedBytes(len) => {
            if word[*len..].iter().any(|b| *b != 0) {
                return Err(format!("bytes{}: trailing padding is not zero", len));
            }
        }
        _ => {}
    }
    Ok(())
}

fn validate_node(param: &ParamType, data: &[u8], offset: usize) -> Result<(), String> {
    match param {
        ParamType::Array(inner) => {
            let count = read_offset(data, offset)?;
            // Every element occupies at least head_size bytes, so a count the
            // buffer cannot hold is a corrupted length word.
            let span = count
                .checked_mul(head_size_of(inner))
                .and_then(|bytes| bytes.checked_add(offset + 32));
            if span.map_or(true, |end| end > data.len()) {
                return Err(format!("array declares {} items, more than the data holds", count));
            }
            validate_sequence(repeat(inner.as_ref()).take(count), data, offset + 32)
        }
        ParamType::FixedArray(inner, len) => {
            validate_sequence(repeat(inner.as_ref()).take(*len), data, offset)
        }
        ParamType::Tuple(types) => validate_sequence(types.iter(), data, offset),
        ParamType::Bytes => validate_dynamic_bytes(data, offset).map(|_| ()),
        ParamType::String => {
            let bytes = validate_dynamic_bytes(data, offset)?;
            // ethabi converts lossily, so without this a byte sequence that is
            // not UTF-8 decodes to U+FFFD here and is rejected on the pure
            // floor -- the same calldata reading differently per tier.
            std::str::from_utf8(bytes)
                .map(|_| ())
                .map_err(|error| format!("string: not valid UTF-8 ({})", error))
        }
        _ => validate_leaf(param, data, offset),
    }
}

// Generic over the iterator so no call site has to materialize a Vec of cloned
// ParamTypes: this pass runs on every decode, and one malloc per call is
// measurable against a ~0.5 us decode.
/// Bounds-check a dynamic byte sequence and reject non-zero bytes between its
/// end and the 32-byte boundary. Only the padding actually present is checked:
/// a missing final pad is a truncation the length check already owns.
fn validate_dynamic_bytes(data: &[u8], offset: usize) -> Result<&[u8], String> {
    let length = read_offset(data, offset)?;
    let start = offset + 32;
    let end = start
        .checked_add(length)
        .ok_or_else(|| format!("bytes length {} overflows the offset", length))?;
    let bytes = data
        .get(start..end)
        .ok_or_else(|| format!("bytes declares {} bytes, more than the data holds", length))?;
    let padding = (32 - end % 32) % 32;
    if padding > 0 {
        let stop = std::cmp::min(end + padding, data.len());
        if data[end..stop].iter().any(|b| *b != 0) {
            return Err("trailing padding of a dynamic value is not zero".to_string());
        }
    }
    Ok(bytes)
}

fn validate_sequence<'a, I>(params: I, data: &[u8], base: usize) -> Result<(), String>
where
    I: Iterator<Item = &'a ParamType> + Clone,
{
    let head_size: usize = params.clone().map(head_size_of).sum();
    let mut cursor = base;
    for param in params {
        if is_dynamic_type(param) {
            let pointer = read_offset(data, cursor)?;
            if pointer < head_size {
                return Err(format!(
                    "dynamic offset {} points inside the {}-byte head area",
                    pointer, head_size
                ));
            }
            validate_node(param, data, base + pointer)?;
            cursor += 32;
        } else {
            validate_node(param, data, cursor)?;
            cursor += static_size_of(param);
        }
    }
    Ok(())
}

/// Decode a function's arguments, rejecting non-canonical encodings.
fn decode_input_strict(
    function: &Function,
    calldata: &[u8],
) -> Result<Vec<Token>, ethers::abi::Error> {
    validate_sequence(function.inputs.iter().map(|p| &p.kind), calldata, 0)
        .map_err(|message| ethers::abi::Error::Other(message.into()))?;
    Function::decode_input(function, calldata)
}


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

        let tokens = decode_input_strict(function, &calldata[4..])
            .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;

        // Build decoded_data map
        let mut decoded_data = serde_json::Map::new();
        for (i, (param, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
            let param_name = if param.name.is_empty() {
                format!("param_{}", i)
            } else {
                param.name.clone()
            };
            decoded_data.insert(param_name, convert_token_to_json(token, &param.kind));
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
            let tokens = match decode_input_strict(function, &calldata[4..]) {
                Ok(t) => t,
                Err(_) => return serde_json::json!(["", []]),
            };

            let params: Vec<serde_json::Value> = function.inputs.iter()
                .zip(tokens.iter())
                .map(|(param, token)| convert_token_to_json(token, &param.kind))
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

                let tokens = match decode_input_strict(function, &calldata[4..]) {
                    Ok(t) => t,
                    Err(_) => return serde_json::json!([""]),
                };

                // Build flat array: [function_name, param1, param2, ...]
                let mut result = vec![serde_json::Value::String(function.name.clone())];
                for (index, token) in tokens.iter().enumerate() {
                    result.push(convert_token_to_json(token, &function.inputs[index].kind));
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

        let tokens = decode_input_strict(function, &calldata[4..])
            .map_err(|e| FastAbiError::DecodeError(e.to_string()))?;

        // Build decoded_data map
        let mut decoded_data = serde_json::Map::new();
        for (i, (param, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
            let param_name = if param.name.is_empty() {
                format!("param_{}", i)
            } else {
                param.name.clone()
            };
            decoded_data.insert(param_name, convert_token_to_json(token, &param.kind));
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

                let tokens = match decode_input_strict(function, &calldata[4..]) {
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
                    decoded_data.insert(param_name, convert_token_to_json(token, &param.kind));
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
            let tokens = match decode_input_strict(function, &calldata[4..]) {
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
                decoded_data.insert(param_name, convert_token_to_json(token, &param.kind));
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
            let tokens = match decode_input_strict(function, &calldata[4..]) {
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
                decoded_data.insert(param_name, convert_token_to_json(token, &param.kind));
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

        match decode_input_strict(function, calldata) {
            Ok(tokens) => {
                let mut decoded_data = serde_json::Map::new();

                for (i, (input, token)) in function.inputs.iter().zip(tokens.iter()).enumerate() {
                    let param_name = if input.name.is_empty() {
                        format!("param_{}", i)
                    } else {
                        input.name.clone()
                    };
                    decoded_data.insert(param_name, convert_token_to_json(token, &input.kind));
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

fn unsigned_to_json(value: &ethers::types::U256) -> serde_json::Value {
    if let Ok(as_u64) = u64::try_from(*value) {
        if as_u64 <= i64::MAX as u64 {
            return serde_json::Value::Number(serde_json::Number::from(as_u64));
        }
    }
    serde_json::Value::String(value.to_string())
}

fn signed_to_json(value: &ethers::types::U256, width: usize) -> serde_json::Value {
    let (normalized, modulus) = if width == 256 {
        (*value, None)
    } else {
        let modulus = ethers::types::U256::one() << width;
        (*value & (modulus - ethers::types::U256::one()), Some(modulus))
    };
    let negative = width > 0 && normalized.bit(width - 1);
    if !negative {
        return unsigned_to_json(&normalized);
    }

    // ethabi stores signed values as their unsigned two's-complement word.
    let magnitude = match modulus {
        Some(modulus) => modulus - normalized,
        None => {
            let (magnitude, _) = (!normalized).overflowing_add(ethers::types::U256::one());
            magnitude
        }
    };
    let max_negative_magnitude = ethers::types::U256::one() << 63;
    if magnitude <= max_negative_magnitude {
        let magnitude_u64 = magnitude.as_u64();
        let signed = if magnitude_u64 == (1u64 << 63) {
            i64::MIN
        } else {
            -(magnitude_u64 as i64)
        };
        serde_json::Value::Number(serde_json::Number::from(signed))
    } else {
        serde_json::Value::String(format!("-{}", magnitude))
    }
}

// ParamType is required for signed ints because Token::Int alone does not
// retain the ABI bit width.
fn convert_token_to_json(token: &Token, param_type: &ParamType) -> serde_json::Value {
    match token {
        Token::Address(addr) => serde_json::Value::String(format!("0x{:x}", addr)),
        Token::Uint(uint) => unsigned_to_json(uint),
        Token::Int(int) => {
            let width = match param_type {
                ParamType::Int(width) => *width,
                _ => 256,
            };
            signed_to_json(int, width)
        }
        Token::Bool(b) => serde_json::Value::Bool(*b),
        Token::String(s) => serde_json::Value::String(s.clone()),
        Token::Bytes(bytes) => serde_json::Value::String(format!("0x{}", hex::encode(bytes))),
        Token::FixedBytes(bytes) => serde_json::Value::String(format!("0x{}", hex::encode(bytes))),
        Token::Array(tokens) => {
            let inner = match param_type {
                ParamType::Array(inner) => inner.as_ref(),
                _ => param_type,
            };
            serde_json::Value::Array(
                tokens.iter().map(|token| convert_token_to_json(token, inner)).collect(),
            )
        }
        Token::FixedArray(tokens) => {
            let inner = match param_type {
                ParamType::FixedArray(inner, _) => inner.as_ref(),
                _ => param_type,
            };
            serde_json::Value::Array(
                tokens.iter().map(|token| convert_token_to_json(token, inner)).collect(),
            )
        }
        Token::Tuple(tokens) => {
            let component_types: &[ParamType] = match param_type {
                ParamType::Tuple(types) => types,
                _ => &[],
            };
            serde_json::Value::Array(
                tokens.iter().enumerate().map(|(index, token)| {
                    let component_type = component_types.get(index).unwrap_or(param_type);
                    convert_token_to_json(token, component_type)
                }).collect(),
            )
        }
    }
}

/// Zero-copy decode: returns Arrow RecordBatch directly to Python/Polars.
/// Columns: "function_name" (Utf8) + one Utf8 column per ABI parameter.
/// All values are stringified for uniform schema across heterogeneous calldata.
#[cfg(feature = "arrow")]
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

                        let tokens = match decode_input_strict(function, &calldata[4..]) {
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
                            let value = convert_token_to_json(token, &input.kind);
                            let clean = match value {
                                serde_json::Value::String(value) => value,
                                value => value.to_string(),
                            };
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
    #[cfg(feature = "arrow")]
    m.add_function(wrap_pyfunction!(decode_many_to_arrow, m)?)?; // Zero-copy Arrow
    m.add_function(wrap_pyfunction!(keccak256_py, m)?)?; // Hash primitive for selectors/EIP-55
    // Decode semantics (string validity, padding strictness, fixed-point width)
    // are versioned with the crate: decode.py refuses an extension older than
    // its _MIN_FASTABI_VERSION rather than letting the two tiers disagree.
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
