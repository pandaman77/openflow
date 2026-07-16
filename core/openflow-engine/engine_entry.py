"""PyInstaller entry point.

__main__.py uses package-relative imports, so it can't be frozen directly
as a top-level script; this shim imports the package absolutely.
"""

import sys

from openflow_engine.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
