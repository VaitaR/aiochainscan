#!/usr/bin/env python3
"""Setup script for aiochainscan package.

This setup.py provides backward compatibility and explicit configuration
for the aiochainscan Python package. The primary build configuration is
in pyproject.toml using setuptools backend.

For the optional Rust-based fast ABI decoder, use:
    pip install aiochainscan[fast]
    maturin develop --manifest-path aiochainscan/fastabi/Cargo.toml
"""

from setuptools import find_packages, setup

setup(
    name='aiochainscan',
    packages=find_packages(include=['aiochainscan', 'aiochainscan.*']),
    include_package_data=True,
    package_data={
        'aiochainscan': [
            'py.typed',
            '*.pyi',
            'fastabi/Cargo.toml',
            'fastabi/Cargo.lock',
            'fastabi/src/*.rs',
        ],
    },
)
