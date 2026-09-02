# Publishing aiochainscan to PyPI

Since the Track A split there are **two distributions**:

- `aiochainscan` — pure Python, built by **hatchling** from the repo root
  (universal wheel + sdist, no Rust toolchain needed).
- `aiochainscan-fastabi` — the optional Rust accelerator, built by **maturin**
  from `aiochainscan/fastabi/` (native per-platform wheels; the importable
  module is top-level `aiochainscan_fastabi`).

## Prerequisites

1. **PyPI Account**: create accounts on
   [PyPI](https://pypi.org/account/register/) and
   [TestPyPI](https://test.pypi.org/account/register/).
2. **API Tokens** ([PyPI](https://pypi.org/manage/account/token/),
   [TestPyPI](https://test.pypi.org/manage/account/token/)) — or use Trusted
   Publishing (below).
3. **Build tools**:
   ```sh
   pip install build twine maturin
   ```

## Step 1: Pre-Publishing Checklist

- [ ] `make ci-local` green (lint, format, import-lint, mypy --strict, pytest)
- [ ] `mypy --strict aiochainscan` clean
- [ ] Documentation (`README.md`, `AGENTS.md`, `docs/`) matches the release
- [ ] `CHANGELOG.md` updated; version bumped in **both** `pyproject.toml`
      (base) and `aiochainscan/fastabi/pyproject.toml` (accelerator) as needed

## Step 2: Build

```sh
# Base distribution (hatchling) — from the repo root
rm -rf dist/
python -m build                       # wheel + sdist, pure Python

# Smoke test: import with no Rust toolchain on PATH
python -c "import aiochainscan; print(aiochainscan.__version__)"

# Accelerator distribution (maturin) — only when its version changes
cd aiochainscan/fastabi
rm -rf target/wheels
uv run --with maturin maturin build --release
cd ../..
```

`python -m build` for the base package does **not** compile Rust — that is the
point of the split.

## Step 3: Verify the Built Packages

```sh
twine check dist/*

python -m venv /tmp/test-package
/tmp/test-package/bin/pip install dist/aiochainscan-*.whl
/tmp/test-package/bin/python -c "import aiochainscan; print('base OK')"
# Optional accelerator check (needs a matching-platform fastabi wheel):
/tmp/test-package/bin/pip install aiochainscan_fastabi --no-deps
/tmp/test-package/bin/python -c "import aiochainscan_fastabi; print('fastabi OK')"
rm -rf /tmp/test-package
```

## Step 4: Test Upload to TestPyPI

```sh
twine upload --repository testpypi dist/*
```

```sh
python -m venv /tmp/test-testpypi
/tmp/test-testpypi/bin/pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ aiochainscan
/tmp/test-testpypi/bin/python -c "import aiochainscan; print('OK')"
rm -rf /tmp/test-testpypi
```

## Step 5: Upload to Production PyPI

```sh
twine upload dist/*
```

PyPI does not allow re-uploading the same version — to fix a bad release,
bump the version and rebuild.

## Automated Publishing via GitHub Actions

> **Currently DISABLED** (`disabled_manually`, Actions-minutes budget). Do not
> wait on CI. Re-enable with:
> `gh workflow enable ci.yml test-install.yml wheels.yml --repo VaitaR/aiochainscan`
> and use `make ci-local` as the local gate meanwhile.

`wheels.yml` builds both distributions on a release tag:

1. `aiochainscan` — pure-Python wheel + sdist, plus a smoke import test without
   Rust on PATH.
2. `aiochainscan-fastabi` — native wheels via **cibuildwheel**
   (Linux x86_64/aarch64, macOS arm64, Windows x86_64; Python 3.12/3.13; musl
   and PyPy not supported).

To trigger: bump versions → tag (`git tag -a v1.0.0 -m "Release v1.0.0" && git
push origin v1.0.0`) → the workflow builds and publishes all artifacts.

**Trusted Publishing** (recommended, no tokens): PyPI → Your Project →
Publishing → add publisher `VaitaR/aiochainscan`, workflow `wheels.yml`.
Otherwise add a `PYPI_API_TOKEN` repository secret and use it in the workflow.

## Version Management

Semantic versioning (MAJOR.MINOR.PATCH). Update `version =` in
`pyproject.toml` (and `aiochainscan/fastabi/pyproject.toml` when the
accelerator changes), then tag the release.

## Troubleshooting

### "File already exists" error
PyPI rejects duplicate versions — increment the version and rebuild.

### Import errors after installation
```sh
unzip -l dist/*.whl | grep aiochainscan/
```
The base wheel must contain the `aiochainscan/` package and `py.typed`; the
fastabi wheel must contain the top-level `aiochainscan_fastabi` extension
module. Packaging is controlled by `[tool.hatch.build.targets.wheel]` in
`pyproject.toml` and `[tool.maturin]` in `aiochainscan/fastabi/pyproject.toml`.

### maturin build fails with a ZIP64 "Large file" error
Requires `maturin>=1.8` (see the pin comment in
`aiochainscan/fastabi/pyproject.toml`); CI sets it to avoid PEP 517 isolation
issues.

## References

- [Python Packaging Guide](https://packaging.python.org/)
- [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
- [maturin](https://www.maturin.rs/) · [cibuildwheel](https://github.com/pypa/cibuildwheel)
- [Semantic Versioning](https://semver.org/)
