"""
Test the trees of graphs.
"""

import metacellswidgets as mw

from .test_daf_widgets import _full_daf
from .test_daf_widgets import _sparse_daf


def test_leaves() -> None:
    """
    The leaves are the graph classes, in the order they are shown, from all the branches.
    """
    tree = mw.Branch("Graphs", [mw.Branch("Expression", [mw.GeneGene]), mw.Branch("Empty", [])])
    assert tree.leaves() == [mw.GeneGene]


def test_visible() -> None:
    """
    The visible tree drops the graphs which don't exist for the data source, and the branches left empty.
    """
    tree = mw.Branch("Graphs", [mw.Branch("Expression", [mw.GeneGene]), mw.Branch("Empty", [])])
    assert tree.visible(mw.DafWidgets(_full_daf())) == mw.Branch("Graphs", [mw.Branch("Expression", [mw.GeneGene])])
    assert tree.visible(mw.DafWidgets(_sparse_daf())) is None
