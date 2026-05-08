"""
__main__.py -- Enable `python -m vcmix` invocation.

Usage:
    python -m vcmix render project.yaml
    python -m vcmix validate project.yaml

Dependencies: vcmix.cli
"""

import os
import sys

# Force UTF-8 on Windows to avoid UnicodeEncodeError with charmap codec
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from vcmix.cli import main

if __name__ == "__main__":
    main()
