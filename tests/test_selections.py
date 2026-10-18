"""
Test selecting the points of a gene-gene graph.
"""

import math
from typing import Any

import pytest
from plotly.callbacks import BoxSelector  # type: ignore
from plotly.callbacks import LassoSelector  # type: ignore
from somegraphspy import PointsGraph
from somegraphspy import ScaleConfiguration

import metacellswidgets as mw
from metacellswidgets.selections import _data_value
from metacellswidgets.selections import _lasso_of
from metacellswidgets.selections import _plotted
from metacellswidgets.selections import _rounded

from .test_daf_widgets import _full_daf


def _form(**keywords: Any) -> mw.GeneGene:
    """
    A gene-gene form of the full data set, where gene ``A`` is 0.1, 0.2 and 0.3 in the three metacells, and gene ``B`` is
    0.2 in all of them.
    """
    return mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", **keywords)


def _graph(form: mw.GeneGene) -> PointsGraph:
    """
    The graph the form shows, kept by it.
    """
    graph = form._shown_graph()  # pylint: disable=protected-access
    assert isinstance(graph, PointsGraph)
    return graph


def test_scales() -> None:
    """
    A data value converts to the coordinate it is plotted at, and back, on a log scale (with its regularization), and on
    a percent scale.
    """
    scale = _graph(_form()).configuration.x_axis.scale
    assert _plotted(scale, 0.25) == pytest.approx(math.log2(0.25 + scale.log_regularization))
    assert _data_value(scale, _plotted(scale, 0.25)) == pytest.approx(0.25)
    percent = ScaleConfiguration(percent=True)
    assert _plotted(percent, 0.25) == pytest.approx(25.0)
    assert _data_value(percent, 25.0) == pytest.approx(0.25)


def test_rounding_and_thinning() -> None:
    """
    Values are rounded to 4 significant digits, and a lasso is thinned to at most 40 vertices, keeping its ends.
    """
    assert _rounded(0.0123456) == 0.01235
    assert _rounded(123456.0) == 123500.0
    graph = _graph(_form())
    xs = [float(index) for index in range(100)]
    lasso = _lasso_of(graph, xs, xs)
    assert len(lasso) == 40
    assert lasso[0][0] == _rounded(_data_value(graph.configuration.x_axis.scale, 0.0))
    assert lasso[-1][0] == _rounded(_data_value(graph.configuration.x_axis.scale, 99.0))


def test_selected_names() -> None:
    """
    The selected names are those of the points inside the box or the lasso, in data units. With no selection, there are
    none. Both a box and a lasso is an error.
    """
    assert not _form().selected_names()
    assert _form(selected_box=(0.15, 0.35, 0.1, 0.3)).selected_names() == ["M2", "M3"]
    lasso = [(0.15, 0.1), (0.35, 0.1), (0.35, 0.3), (0.15, 0.3)]
    assert _form(selected_lasso=lasso).selected_names() == ["M2", "M3"]
    with pytest.raises(ValueError):
        _form(selected_box=(0.15, 0.35, 0.1, 0.3), selected_lasso=lasso)


def test_selected_names_use_the_shown_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The selected names come from the graph last shown, unless an argument other than the selection changed since. Then
    the graph is built again, and since its points differ, the selection is cleared.
    """
    form = _form(selected_box=(0.15, 0.35, 0.1, 0.3))
    _graph(form)

    def no_graph() -> None:
        raise AssertionError("the graph was built again")

    monkeypatch.setattr(form, "graph", no_graph)
    assert form.selected_names() == ["M2", "M3"]
    form.selected_box = (0.05, 0.15, 0.1, 0.3)
    assert form.selected_names() == ["M1"]

    monkeypatch.undo()
    form.x_gene = "C"
    assert not form.selected_names()
    assert form.selected_box is None


def test_look_keeps_the_selection() -> None:
    """
    Showing the graph again with another look keeps the selection; with other points, it clears it.
    """
    form = _form(selected_box=(0.15, 0.35, 0.1, 0.3))
    _graph(form)
    form.colors = mw.Type()
    _graph(form)
    assert form.selected_box == (0.15, 0.35, 0.1, 0.3)
    form.x_gene = "C"
    graph = _graph(form)
    assert form.selected_box is None
    assert graph.data.selection.box is None


def test_selecting_in_the_figure() -> None:
    """
    A box or a lasso selected in the shown figure is stored in data units, rounded; deselecting clears it.
    """
    form = _form()
    graph = _graph(form)
    x_scale = graph.configuration.x_axis.scale
    y_scale = graph.configuration.y_axis.scale
    x_range = [_plotted(x_scale, 0.15), _plotted(x_scale, 0.35)]
    y_range = [_plotted(y_scale, 0.1), _plotted(y_scale, 0.3)]
    form._on_selection(BoxSelector(xrange=x_range, yrange=y_range))  # pylint: disable=protected-access
    assert form.selected_box == (0.15, 0.35, 0.1, 0.3)
    assert form.selected_names() == ["M2", "M3"]

    xs = [x_range[0], x_range[1], x_range[1], x_range[0]]
    ys = [y_range[0], y_range[0], y_range[1], y_range[1]]
    form._on_selection(LassoSelector(xs=xs, ys=ys))  # pylint: disable=protected-access
    assert form.selected_box is None
    assert form.selected_lasso == [(0.15, 0.1), (0.35, 0.1), (0.35, 0.3), (0.15, 0.3)]

    form._on_deselect()  # pylint: disable=protected-access
    assert form.selected_lasso is None
