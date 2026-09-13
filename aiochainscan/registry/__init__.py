"""Chain registry package: static data, derived views, and target resolution.

Submodules:

- :mod:`aiochainscan.registry.data` — the static measured tables and their
  read accessors (imports nothing above data).
- :mod:`aiochainscan.registry.views` — the derived per-scanner view tables,
  the import-time topology validator, the runtime mutation seam and the
  config-manager presentation rows (never imports config).
- :mod:`aiochainscan.registry.resolve` — ``ScannerTarget`` resolution (may
  import config for key lookups).

Import the submodules directly. This package imports none of them, so that
``aiochainscan.registry.views`` stays importable from
``aiochainscan.config`` without dragging the resolution engine — and with it
``aiochainscan.config`` — into the import.
"""
