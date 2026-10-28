"""
Test the calls of a typical session, which ``MetacellsWidgetsPy`` makes while it is precompiled.
"""

from metacellswidgets.workloads import run_workload


def test_run_workload() -> None:
    """
    The calls succeed, so precompiling ``MetacellsWidgetsPy`` succeeds too.
    """
    run_workload()
