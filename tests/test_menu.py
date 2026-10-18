"""
Test the menu of the graphs.
"""

from typing import Any
from typing import List

import pytest

import metacellswidgets as mw

from .test_genes_heatmap import _daf

# A tree with a sub-menu, so a path may have more than one level.
_TREE = mw.Branch("Graphs", [mw.GeneGene, mw.Branch("Heatmaps", [mw.GenesHeatmap])])


def _labels(menu: mw.GraphMenu) -> List[List[str]]:
    """
    The labels of the options of each dropdown of the menu.
    """
    return [[label for label, _value in dropdown.options] for dropdown in menu.children]


def _choose(menu: mw.GraphMenu, level: int, node: Any) -> None:
    """
    Choose the ``node`` in the dropdown of the ``level``, as a user would.
    """
    menu.children[level].value = node


def test_menu() -> None:
    """
    The menu starts with one dropdown with nothing chosen. Choosing a sub-menu adds a dropdown of its children, and
    choosing a graph sets the value. Choosing at a higher level drops the levels below it.
    """
    menu = mw.GraphMenu(mw.DafWidgets(_daf()), _TREE)
    assert _labels(menu) == [["Choose...", "GeneGene", "Heatmaps"]]
    assert menu.value is None

    _choose(menu, 0, _TREE.children[1])
    assert _labels(menu) == [["Choose...", "GeneGene", "Heatmaps"], ["Choose...", "GenesHeatmap"]]
    assert menu.value is None

    _choose(menu, 1, mw.GenesHeatmap)
    assert menu.value is mw.GenesHeatmap

    _choose(menu, 0, mw.GeneGene)
    assert len(menu.children) == 1
    assert menu.value is mw.GeneGene


def test_menu_current() -> None:
    """
    The menu starts with the path to the current graph.
    """
    menu = mw.GraphMenu(mw.DafWidgets(_daf()), _TREE, mw.GenesHeatmap)
    assert len(menu.children) == 2
    assert menu.children[1].value is mw.GenesHeatmap
    assert menu.value is mw.GenesHeatmap


def test_menu_method() -> None:
    """
    A menu must be shown at the top level of a cell.
    """
    with pytest.raises(RuntimeError, match="top level of a cell"):
        mw.DafWidgets(_daf()).menu()
