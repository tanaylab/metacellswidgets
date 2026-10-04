"""
Test the package as a whole.
"""

import metacellswidgets as mw


def test_version() -> None:
    """
    The package imports, and reports its version.
    """
    assert mw.__version__ == "0.1.0"
