"""
MACCREv2 Vendor Layer

This folder contains external packages that have been pulled into the local codebase
to eliminate dependency drift, enforce true air-gapped sovereignty, and allow for
omnicontrol over physical architecture limits.

All external package dependencies not absolutely necessary for core python
functionality (stdlibrary) should eventually be vendored or rewritten here.
"""

# Shim for openpyxl exactly as it was requested
import sys
from pathlib import Path

# Insert the _vendor directory into sys.path so the vendored packages
# can import their own submodules normally.
_vendor_dir = Path(__file__).parent.resolve()
if str(_vendor_dir) not in sys.path:
    sys.path.insert(0, str(_vendor_dir))

import openpyxl

__all__ = ['openpyxl']
