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

```sh
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build source distribution and wheel
python -m build

# Verify the build
ls dist/
# Should show:
# - aiochainscan-0.2.1.tar.gz (source distribution)
# - aiochainscan-0.2.1-py3-none-any.whl (wheel)
```

## Step 3: Verify the Built Package

```sh
# Check the package metadata
twine check dist/*

# Test installation in a clean environment
python -m venv /tmp/test-package
source /tmp/test-package/bin/activate
pip install dist/aiochainscan-0.2.1-py3-none-any.whl

# Run verification script
python verify_installation.py

# Test basic functionality
python -c "import aiochainscan; print(aiochainscan.__version__)"

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

The repository includes a CI/CD workflow that automatically publishes to PyPI when a release is created.

### To trigger automated publishing:

1. **Update version** in `pyproject.toml`
2. **Commit and push** changes
3. **Create a GitHub release**:
   ```sh
   # Tag the release
   git tag -a v0.2.1 -m "Release v0.2.1"
   git push origin v0.2.1

   # Or use GitHub UI to create release
   ```

4. The CI workflow will automatically:
   - Run tests and linting
   - Build the package
   - Publish to PyPI

### Configure PyPI token in GitHub:

1. Go to repository Settings → Secrets → Actions
2. Add a new secret: `PYPI_API_TOKEN`
3. Paste your PyPI API token

The workflow uses trusted publishing (no token needed if configured).

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
