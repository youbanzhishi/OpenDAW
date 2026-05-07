"""
__main__.py — Enable `python -m vcmix` invocation.

Usage:
    python -m vcmix render project.yaml
    python -m vcmix validate project.yaml

Dependencies: vcmix.cli
"""

from vcmix.cli import main

if __name__ == "__main__":
    main()
