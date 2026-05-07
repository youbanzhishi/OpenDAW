"""
setup.py — Minimal shim for legacy pip / editable installs.

Usage:
    pip install -e .          # editable install
    pip install .             # regular install

This file exists solely for compatibility with tools that do not yet
support pyproject.toml-based builds. All metadata lives in pyproject.toml.

Dependencies: None (metadata in pyproject.toml)
"""
from setuptools import setup

setup()
