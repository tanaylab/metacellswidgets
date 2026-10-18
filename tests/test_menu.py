"""
Test the menu of the graphs.
"""

from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

import pytest

import metacellswidgets as mw
from metacellswidgets.forms import _kind_tree
from metacellswidgets.forms import _pooled
from metacellswidgets.forms import _switched_form

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


def test_switched_form() -> None:
    """
    A form switched to takes the pooled values whose name and type annotation fit it, the later forms' values replacing
    the earlier ones', and ``None`` for its other required arguments.
    """
    source = mw.DafWidgets(_daf())
    blank = _switched_form(mw.GeneGene, source, {}, None).arguments()
    assert (blank["axis"], blank["x_gene"], blank["y_gene"], blank["tweaks"]) == ("metacell", None, None, None)

    pool: Dict[str, Tuple[Any, Any]] = {}
    _pooled(pool, source.gene_gene(x_gene="A", y_gene="B", colors=mw.Type(), selected_box=(0.1, 0.2, 0.1, 0.2)))
    _pooled(pool, source.genes_heatmap(axis="block", tweaks=[mw.Title(text="T")]))
    restored = _switched_form(mw.GeneGene, source, pool, None)
    expected = source.gene_gene(
        axis="block",
        x_gene="A",
        y_gene="B",
        colors=mw.Type(),
        selected_box=(0.1, 0.2, 0.1, 0.2),
        tweaks=[mw.Title(text="T")],
    )
    assert restored.arguments() == expected.arguments()


def test_kind_tree() -> None:
    """
    The tree of a kind's menu is found through its ``graph_menu``.
    """
    assert _kind_tree(mw.DafWidgets(_daf())) is mw.DafWidgets.tree


def test_menu_method() -> None:
    """
    A menu must be shown at the top level of a cell.
    """
    with pytest.raises(RuntimeError, match="top level of a cell"):
        mw.DafWidgets(_daf()).menu()
