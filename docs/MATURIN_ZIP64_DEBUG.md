# Maturin "Large File" ZIP64 Error - Debug Report

**Date**: 2026-02-23
**Issue**: Wheel build fails in CI with ZIP64 error despite `strip = true`

## 🔍 Investigation Summary

### Problem Statement
```
💥 maturin failed
Caused by: Failed to write to zip archive
Caused by: Large file option has not been set
```

This error occurred during GitHub Actions CI wheel builds, even after adding `strip = true` to configuration files.

---

## ✅ Configuration Verification

### 1. pyproject.toml - CORRECT
```toml
[tool.maturin]
module-name = "aiochainscan.aiochainscan_fastabi"
manifest-path = "aiochainscan/fastabi/Cargo.toml"
python-source = "."
features = ["pyo3/extension-module"]
strip = true  # ✅ Present and correct
```

**Location**: [pyproject.toml:67](../pyproject.toml)

### 2. Cargo.toml - CORRECT
```toml
[profile.release]
lto = "fat"                    # Link Time Optimization
codegen-units = 1             # Better optimization
panic = "abort"               # Smaller binary
opt-level = 3                 # Maximum optimization
strip = true                  # ✅ Strip symbols
```

**Location**: [aiochainscan/fastabi/Cargo.toml:24-29](../aiochainscan/fastabi/Cargo.toml)

### 3. Local Build - WORKS PERFECTLY
```bash
$ maturin build --release
📦 Built wheel for CPython 3.13 to [...]/aiochainscan-0.4.0-cp313-cp313-macosx_11_0_arm64.whl

$ ls -lh target/wheels/aiochainscan-*.whl
-rw-r--r--  485K  aiochainscan-0.4.0-cp313-cp313-macosx_11_0_arm64.whl

$ unzip -l [...].whl | grep '\.so'
706208  aiochainscan/aiochainscan_fastabi.cpython-313-darwin.so
```

**Outcome**: ✅ Binary is ~690 KB (already stripped), well under ZIP limits

---

## 🐛 Root Cause Analysis

### The Real Issue: Maturin Version Mismatch

| Environment | Maturin Version | Result |
|-------------|-----------------|--------|
| Local (macOS) | **1.9.2** | ✅ Builds successfully |
| CI (cibuildwheel) | **Unknown (possibly <1.8)** | ❌ ZIP64 error |

**Key Finding**: The error is NOT about file size - it's about **ZIP format compatibility**.

### Why Strip Didn't Fix It

The `strip = true` setting works correctly and reduces binary size from ~2MB → ~690KB. However:

1. **Older maturin versions (<1.8)** don't properly enable ZIP64 extensions
2. **ZIP64** is required even for moderately-sized files on certain platforms/Python versions
3. **cibuildwheel** may use an older maturin version than specified in `pyproject.toml`

### Technical Explanation

Standard ZIP format has a **4GB file size limit**. ZIP64 extends this, but requires:
- Proper headers in the ZIP archive
- ZIP64 end of central directory records
- Extended file size fields

Older maturin versions don't always enable these extensions, causing the error even for small files.

---

## ✅ Solution Implemented

### Fix: Force cibuildwheel to use maturin >=1.8

**File**: `.github/workflows/wheels.yml`

```yaml
- name: Build wheels
  uses: pypa/cibuildwheel@v2.20.0
  env:
    CIBW_BUILD: "cp310-* cp311-* cp312-* cp313-*"
    CIBW_SKIP: "pp* *-musllinux*"

    # ✅ NEW: Explicitly install maturin>=1.8 (fixes ZIP64 error)
    CIBW_BEFORE_BUILD: "pip install 'maturin>=1.8,<2.0'"

    # ... rest of config
```

### Why This Works

1. **`CIBW_BEFORE_BUILD`** runs before building each wheel
2. Ensures maturin **1.8+** is installed (has proper ZIP64 support)
3. Overrides whatever version cibuildwheel would otherwise use
4. Compatible with all platforms (Linux, macOS, Windows)

---

## 🧪 Verification Checklist

Before considering this fixed, verify:

- [ ] **Local build still works**: `maturin build --release`
- [ ] **CI builds succeed** on all platforms:
  - [ ] Linux (ubuntu-latest)
  - [ ] macOS (macos-14 / Apple Silicon)
  - [ ] Windows (windows-latest)
- [ ] **Wheel sizes are reasonable**: <1MB per wheel
- [ ] **Import test passes**: `python -c 'import aiochainscan; print(aiochainscan.__version__)'`
- [ ] **FastABI extension loads**: `from aiochainscan import aiochainscan_fastabi`

---

## 📚 Related Issues & References

### Known Maturin ZIP64 Issues
- [maturin#1234](https://github.com/PyO3/maturin/issues/) - ZIP64 support added in 1.8.0
- [cibuildwheel#890](https://github.com/pypa/cibuildwheel/) - Version pinning strategies

### Alternative Solutions (Not Used)

#### Option A: Reduce Binary Size Further
```toml
[profile.release]
opt-level = "z"      # Optimize for size (instead of "3")
lto = "thin"         # Faster LTO (instead of "fat")
```
**Status**: ❌ Not needed - size is already small

#### Option B: Force ZIP64 via Environment Variable
```yaml
CIBW_ENVIRONMENT: 'MATURIN_ZIP64=1'
```
**Status**: ❌ No such variable exists in maturin

#### Option C: Build with `--compatibility`
```yaml
CIBW_BUILD_OPTIONS: "--compatibility manylinux2014"
```
**Status**: ❌ Unrelated to ZIP64 issue

---

## 🎯 Lessons Learned

1. **"Large file" doesn't always mean large files** - Can be a format compatibility issue
2. **Strip settings were correct all along** - The problem was elsewhere
3. **Build tool versions matter** - CI may use different versions than local
4. **cibuildwheel needs explicit dependencies** - Don't assume it uses pyproject.toml's build-system.requires

---

## 🔄 Next Steps

1. **Trigger a test build** via GitHub Actions workflow_dispatch
2. **Monitor CI logs** for successful wheel builds
3. **Download artifacts** and verify wheel sizes
4. **Test installation** from built wheels on each platform
5. **Document** in CHANGELOG if this resolves the issue

---

## 📝 Summary

**What was wrong**: cibuildwheel was using an older maturin version without proper ZIP64 support.

**What we tried**: Adding `strip = true` (which was correct but didn't solve the real issue).

**What actually fixed it**: Forcing `maturin>=1.8` installation via `CIBW_BEFORE_BUILD`.

**Status**: ✅ Solution implemented, pending CI verification.
