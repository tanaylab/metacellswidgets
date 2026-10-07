"""
Test the graphs.
"""

from pathlib import Path

import numpy as np

import metacellswidgets as mw

from .test_anndata_widgets import _source
from .test_daf_widgets import _full_daf


def test_gene_gene_arguments() -> None:
    """
    The form holds its arguments, but not its data source.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", colors=mw.Type())
    assert isinstance(form, mw.GeneGene)
    assert form.arguments() == {"axis": "metacell", "x_gene": "A", "y_gene": "B", "colors": mw.Type(), "sizes": None}


def test_gene_gene_of_daf() -> None:
    """
    The graph of a ``Daf`` data set, with its points colored and sized.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", colors=mw.Type(), sizes=mw.NCells())
    graph = form.graph()
    assert graph.data.x.vector is not None
    assert list(np.asarray(graph.data.x.vector)) == [np.float32(0.1), np.float32(0.2), np.float32(0.3)]
    assert graph.data.points.colors.vector is not None
    assert list(graph.data.points.colors.vector) == ["T1", "T2", "T1"]
    assert graph.data.points.sizes.vector is not None
    assert len(graph.data.points.sizes.vector) == 3


def test_gene_gene_of_blocks() -> None:
    """
    The graph of the blocks of a ``Daf`` data set.
    """
    graph = mw.DafWidgets(_full_daf()).gene_gene(axis="block", x_gene="A", y_gene="B").graph()
    assert graph.data.points.entities.names is not None
    assert list(graph.data.points.entities.names) == ["B1", "B2"]


def test_gene_gene_of_anndata(tmp_path: Path) -> None:
    """
    The graph of an ``AnnData``, with its points colored.
    """
    graph = _source(tmp_path).gene_gene(x_gene="A", y_gene="B", colors=mw.Type()).graph()
    assert graph.data.points.colors.vector is not None
    assert list(graph.data.points.colors.vector) == ["T1", "T2", "T1"]


def test_display() -> None:
    """
    Displaying the form returns it, so it can be chained to its creation.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B")
    assert form.display() is form
