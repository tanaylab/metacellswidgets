"""
Test the graphs.
"""

from pathlib import Path

import numpy as np
import pytest
from somegraphspy import PointsGraph

import metacellswidgets as mw

from .test_anndata_widgets import _source
from .test_daf_widgets import _full_daf
from .test_daf_widgets import _sparse_daf


def test_gene_gene_arguments() -> None:
    """
    The form holds its arguments, but not its data source.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", colors=mw.Type())
    assert isinstance(form, mw.GeneGene)
    assert form.arguments() == {
        "axis": "metacell",
        "x_gene": "A",
        "y_gene": "B",
        "colors": mw.Type(),
        "sizes": None,
        "hovers": None,
        "selected_box": None,
        "selected_lasso": None,
        "tweaks": None,
    }


def test_gene_gene_repr() -> None:
    """
    The ``repr`` of a form writes its properties with their bare class names.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", sizes=mw.TotalUMIs())
    assert repr(form) == (
        "GeneGene(axis='metacell', x_gene='A', y_gene='B', colors=None, sizes=TotalUMIs(), hovers=None, "
        "selected_box=None, selected_lasso=None, tweaks=None)"
    )


def test_gene_gene_tweaks() -> None:
    """
    The tweaks change the graph after it is built, in order, and are written into the code of the cell.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(
        x_gene="A", y_gene="B", tweaks=[mw.Size(width=600), mw.Size(width=640), mw.Title(text="Genes")]
    )
    graph = form.graph()
    assert graph.configuration.figure.width == 640
    assert graph.data.figure_title == "Genes"
    assert repr(form).endswith(
        "tweaks=[Size(width=600, height=None), Size(width=640, height=None), Title(text='Genes')])"
    )


def test_gene_gene_equality() -> None:
    """
    Forms are equal when they have the same data source and the same arguments.
    """
    source = mw.DafWidgets(_full_daf())
    form = source.gene_gene(x_gene="A", y_gene="B", colors=mw.Type())
    assert form == source.gene_gene(x_gene="A", y_gene="B", colors=mw.Type())
    assert form != source.gene_gene(x_gene="A", y_gene="B")
    assert form != mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", colors=mw.Type())


def test_gene_gene_of_daf() -> None:
    """
    The graph of a ``Daf`` data set, with its points colored and sized.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", colors=mw.Type(), sizes=mw.NCells())
    graph = form.graph()
    assert isinstance(graph, PointsGraph)
    assert mw.GeneGene.graph_type is PointsGraph
    assert graph.data.x.vector is not None
    assert list(np.asarray(graph.data.x.vector)) == [np.float32(0.1), np.float32(0.2), np.float32(0.3)]
    assert graph.data.points.colors.vector is not None
    assert list(graph.data.points.colors.vector) == ["T1", "T2", "T1"]
    assert graph.data.points.sizes.vector is not None
    assert len(graph.data.points.sizes.vector) == 3


def test_gene_gene_hovers() -> None:
    """
    Hover properties add lines to the hover of each point, without coloring or sizing it.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", hovers=[mw.Type()])
    graph = form.graph()
    assert graph.data.points.colors.vector is None
    assert graph.data.points.entities.hovers is not None
    assert all("type: " in hover for hover in graph.data.points.entities.hovers)


def test_gene_gene_hovers_are_new() -> None:
    """
    A hover which the colors, the sizes, or another hover already show is an error. While editing, the hovers offer
    only what the points don't already show, and a hover which the colors come to show is removed.
    """
    source = mw.DafWidgets(_full_daf())
    with pytest.raises(ValueError):
        source.gene_gene(x_gene="A", y_gene="B", colors=mw.Type(), hovers=[mw.Type()])
    with pytest.raises(ValueError):
        source.gene_gene(x_gene="A", y_gene="B", hovers=[mw.Type(), mw.Type()])

    form = source.gene_gene(x_gene="A", y_gene="B", hovers=[mw.Type()])
    editor = form.editor()
    colors = editor.children[1].children[1]
    hovers = editor.children[3]
    hover_rows = hovers.children[0].children[0].children[1].children
    blank_row = hover_rows[-1]
    assert mw.Type not in [choice for _label, choice in blank_row.children[0].options]
    assert mw.Type in [choice for _label, choice in hover_rows[0].children[0].children[0].options]

    colors.children[0].value = mw.Type
    assert form.colors == mw.Type()
    assert form.hovers == []
    assert mw.Type not in [choice for _label, choice in blank_row.children[0].options]


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


def test_gene_gene_exists(tmp_path: Path) -> None:
    """
    The graph exists for a data source with the expression of genes.
    """
    assert mw.GeneGene.exists(mw.DafWidgets(_full_daf()))
    assert not mw.GeneGene.exists(mw.DafWidgets(_sparse_daf()))
    assert mw.GeneGene.exists(_source(tmp_path))


def test_display() -> None:
    """
    Displaying the form returns it, so it can be chained to its creation.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B")
    assert form.display() is form


def test_display_formats() -> None:
    """
    The graph may be shown as a static image, and any other format is an error.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B")
    assert form.display(format="svg") is form
    assert form.display(format="png") is form
    with pytest.raises(ValueError, match="unknown format: jpeg"):
        form.display(format="jpeg")  # type: ignore
