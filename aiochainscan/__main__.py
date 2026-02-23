"""Entry point for running aiochainscan as a module.

Usage:
    python -m aiochainscan list
    python -m aiochainscan check
    python -m aiochainscan generate-env
"""

from aiochainscan.cli import main

if __name__ == '__main__':
    main()
