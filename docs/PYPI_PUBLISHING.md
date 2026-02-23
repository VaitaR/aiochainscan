# Publishing aiochainscan to PyPI

This guide explains how to publish the package to PyPI so users can install it with `pip install aiochainscan`.

## Prerequisites

1. **PyPI Account**: Create accounts on:
   - PyPI (production): https://pypi.org/account/register/
   - TestPyPI (testing): https://test.pypi.org/account/register/

2. **API Tokens**: Generate API tokens for both:
   - PyPI: https://pypi.org/manage/account/token/
   - TestPyPI: https://test.pypi.org/manage/account/token/

3. **Install build tools**:
   ```sh
   pip install build twine
   ```

## Step 1: Pre-Publishing Checklist

Before publishing, ensure:

- [ ] All tests pass: `pytest`
- [ ] Linting passes: `ruff check`
- [ ] Type checking passes: `mypy --strict aiochainscan`
- [ ] Documentation is up to date
- [ ] CHANGELOG is updated with version changes
- [ ] Version in `pyproject.toml` is correct
- [ ] Installation works: Run `verify_installation.py` after local build

## Step 2: Build the Package

The package uses [maturin](https://www.maturin.rs/) to build wheels with the Rust extension.

### Building with Rust Extension (Recommended)

```sh
# Install maturin
pip install maturin

# Clean previous builds
rm -rf dist/ build/ *.egg-info target/

# Build wheel with Rust extension
maturin build --release

# Verify the build
ls dist/
# Should show platform-specific wheel like:
# - aiochainscan-0.4.0-cp312-cp312-macosx_11_0_arm64.whl
```

### Building Source Distribution Only

```sh
# Build sdist (for users who will compile Rust themselves)
maturin sdist

# Or using standard build tool
python -m build --sdist
```

### Local Development Build

```sh
# Install in development mode with Rust compilation
maturin develop --release

# Test the installation
python -c "from aiochainscan import aiochainscan_fastabi; print('Rust extension loaded!')"
```

## Step 3: Verify the Built Package

```sh
# Check the package metadata
twine check dist/*

# Test installation in a clean environment
python -m venv /tmp/test-package
source /tmp/test-package/bin/activate

# Install the wheel (adjust filename for your platform)
pip install dist/aiochainscan-*.whl

# Run verification script
python verify_installation.py

# Test basic functionality
python -c "import aiochainscan; print(aiochainscan.__version__)"

# Test Rust extension (optional)
python -c "from aiochainscan import aiochainscan_fastabi; print('Rust extension OK')"

deactivate
rm -rf /tmp/test-package
```

## Step 4: Test Upload to TestPyPI

First, test the upload on TestPyPI:

```sh
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Enter your TestPyPI API token when prompted
# Or configure ~/.pypirc (see below)
```

Test installation from TestPyPI:

```sh
# Create test environment
python -m venv /tmp/test-testpypi
source /tmp/test-testpypi/bin/activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    aiochainscan

# Verify
python verify_installation.py

deactivate
rm -rf /tmp/test-testpypi
```

## Step 5: Upload to Production PyPI

If TestPyPI installation works correctly:

```sh
# Upload to production PyPI
twine upload dist/*

# Enter your PyPI API token when prompted
```

## Step 6: Verify Production Installation

```sh
# Install from PyPI
pip install aiochainscan

# Verify
python -c "import aiochainscan; print('Version:', aiochainscan.__version__)"
```

## Configuration: ~/.pypirc

To avoid entering credentials every time, create `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YOUR_PRODUCTION_API_TOKEN_HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TEST_API_TOKEN_HERE
```

**Security**: Keep this file secure:
```sh
chmod 600 ~/.pypirc
```

## Automated Publishing via GitHub Actions

The repository includes a CI/CD workflow that automatically builds pre-compiled wheels and publishes to PyPI when a release is created.

### Pre-compiled Wheels with cibuildwheel

The project uses [cibuildwheel](https://cibuildwheel.readthedocs.io/) to build platform-specific wheels that include the compiled Rust extension (`fastabi`). This means users don't need Rust installed to use the fast ABI decoder.

#### Supported Platforms

| Platform | Architecture | Python Versions |
|----------|--------------|-----------------|
| Linux (glibc) | x86_64, aarch64 | 3.10, 3.11, 3.12, 3.13 |
| macOS | Apple Silicon (arm64) | 3.10, 3.11, 3.12, 3.13 |
| Windows | x86_64 | 3.10, 3.11, 3.12, 3.13 |

**Note**: musllinux and PyPy are not supported.

#### How cibuildwheel Works

1. **Matrix Build**: The workflow runs on `ubuntu-latest`, `windows-latest`, and `macos-14` (Apple Silicon)
2. **Rust Compilation**: Each platform compiles the Rust extension natively using maturin
3. **Wheel Generation**: Creates wheels like `aiochainscan-0.4.0-cp312-cp312-manylinux_2_17_x86_64.whl`
4. **Testing**: Each wheel is tested by importing the package before upload
5. **Publication**: All wheels + source distribution are uploaded to PyPI

#### Build Configuration

The build is configured in:
- `.github/workflows/wheels.yml` - GitHub Actions workflow
- `pyproject.toml` - maturin build settings under `[tool.maturin]`
- `aiochainscan/fastabi/Cargo.toml` - Rust crate configuration

### To trigger automated publishing:

1. **Update version** in `pyproject.toml`
2. **Commit and push** changes
3. **Create a GitHub release**:
   ```sh
   # Tag the release
   git tag -a v0.4.0 -m "Release v0.4.0"
   git push origin v0.4.0

   # Or use GitHub UI to create release
   ```

4. The CI workflow will automatically:
   - Build wheels for all supported platforms (Linux, macOS, Windows)
   - Build source distribution (sdist)
   - Run import tests on each wheel
   - Publish all artifacts to PyPI

### Manual Wheel Build

You can trigger a manual wheel build without publishing:

1. Go to Actions → "Build and Publish Wheels"
2. Click "Run workflow"
3. Download artifacts from the workflow run

### Configure PyPI Trusted Publishing (Recommended)

The workflow uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) which doesn't require API tokens:

1. Go to PyPI → Your Project → Publishing
2. Add a new trusted publisher:
   - Owner: `VaitaR`
   - Repository: `aiochainscan`
   - Workflow: `wheels.yml`
   - Environment: (leave blank)

### Alternative: Configure PyPI Token

If not using trusted publishing:

1. Go to repository Settings → Secrets → Actions
2. Add a new secret: `PYPI_API_TOKEN`
3. Paste your PyPI API token
4. Update the workflow to use the token

## Version Management

Follow semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

Update version in:
- `pyproject.toml`: `version = "0.2.1"`
- Create git tag: `git tag v0.2.1`

## Post-Publishing Checklist

After successful publication:

- [ ] Verify package on PyPI: https://pypi.org/project/aiochainscan/
- [ ] Test installation: `pip install aiochainscan`
- [ ] Update GitHub release notes
- [ ] Announce on social media / community channels
- [ ] Update documentation site (if applicable)

## Troubleshooting

### "File already exists" error

PyPI doesn't allow re-uploading the same version. Solutions:
- Delete the release from PyPI (if just published)
- Increment version number and rebuild

### Missing files in wheel

Check `MANIFEST.in` and rebuild:
```sh
rm -rf dist/ build/
python -m build
twine check dist/*
```

### Import errors after installation

Verify package structure:
```sh
unzip -l dist/*.whl | grep aiochainscan/
```

Should show all Python modules.

## References

- PyPI: https://pypi.org/
- Python Packaging Guide: https://packaging.python.org/
- Twine: https://twine.readthedocs.io/
- Semantic Versioning: https://semver.org/
