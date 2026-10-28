"""
Test the genes heatmap form.
"""

from pathlib import Path
from typing import Any
from typing import List

import dafpy as dp
import numpy as np
import pandas as pd
import pytest
from anndata import AnnData  # type: ignore
from dafpy.julia_import import DEFAULT
from somegraphspy import HeatmapGraph

import metacellswidgets as mw

from .test_daf_widgets import _full_daf


def _list(values: Any) -> List[Any]:
    """
    A graph field as a list, once it is known to be filled.
    """
    assert values is not None
    return list(values)


def _daf() -> dp.DafWriter:
    """
    The full data set, with the log fractions the folds are computed from, and marker ranks.
    """
    daf = _full_daf()
    daf.set_vector("gene", "marker_rank", np.array([1, 2, 3, np.iinfo(np.uint32).max], dtype="uint32"))
    daf.set_matrix(
        "gene",
        "metacell",
        "log_linear_fraction",
        np.array([[1.0, 2.0, 3.0], [2.0, 2.0, 2.0], [3.0, 2.0, 1.0], [0.0, 0.0, 0.0]], dtype="float32", order="F"),
    )
    return daf


def test_defaults() -> None:
    """
    Left out, the genes are the strongest markers, all the entries are shown, and each side has its default annotations.
    """
    form = mw.DafWidgets(_daf()).genes_heatmap()
    assert form.default_row_annotations() == [mw.IsLateral()]
    assert form.default_column_annotations() == [mw.Type()]
    graph = form.graph()
    assert isinstance(graph, HeatmapGraph)
    assert mw.GenesHeatmap.graph_type is HeatmapGraph
    assert _list(graph.data.rows.entities.names) == ["A", "B", "C"]
    assert _list(graph.data.columns.entities.names) == ["M1", "M2", "M3"]
    assert [annotation.colors.title for annotation in graph.data.rows.annotations] == ["lateral"]
    assert [annotation.colors.title for annotation in graph.data.columns.annotations] == ["type"]


def test_explicit() -> None:
    """
    Explicit genes, filters and annotations are used exactly, an empty list of annotations included.
    """
    form = mw.DafWidgets(_daf()).genes_heatmap(
        genes=mw.GeneList(names=["C", "A"]),
        entries=[mw.OfTypes(types=["T1"])],
        row_annotations=[],
        column_annotations=[mw.Block()],
    )
    graph = form.graph()
    assert _list(graph.data.rows.entities.names) == ["C", "A"]
    assert _list(graph.data.columns.entities.names) == ["M1", "M3"]
    assert not graph.data.rows.annotations
    assert [annotation.colors.title for annotation in graph.data.columns.annotations] == ["block"]


def test_hovers() -> None:
    """
    Hover properties add lines to the hovers of their side, without annotating it.
    """
    form = mw.DafWidgets(_daf()).genes_heatmap(
        row_annotations=[], column_annotations=[], row_hovers=[mw.IsMarker()], column_hovers=[mw.Block()]
    )
    graph = form.graph()
    assert not graph.data.rows.annotations
    assert not graph.data.columns.annotations
    assert all("marker: " in hover for hover in _list(graph.data.rows.entities.hovers))
    assert all("block: " in hover for hover in _list(graph.data.columns.entities.hovers))


def test_hovers_are_new() -> None:
    """
    A hover which the annotations of its side already show, the default ones included, is an error.
    """
    source = mw.DafWidgets(_daf())
    with pytest.raises(ValueError):
        source.genes_heatmap(column_hovers=[mw.Type()])
    with pytest.raises(ValueError):
        source.genes_heatmap(row_annotations=[mw.IsMarker()], row_hovers=[mw.IsMarker()])
    assert source.genes_heatmap(column_annotations=[], column_hovers=[mw.Type()]).column_hovers == [mw.Type()]


def test_editor() -> None:
    """
    The editor builds, and an untouched default leaves its argument ``DEFAULT``.
    """
    form = mw.DafWidgets(_daf()).genes_heatmap()
    assert form.editor() is not None
    assert form.genes is DEFAULT
    assert form.row_annotations is DEFAULT
    assert form.column_annotations is DEFAULT
    assert mw.GenesHeatmap in mw.DafWidgets.tree.leaves()


def test_anndata(tmp_path: Path) -> None:
    """
    An ``AnnData`` shows the heatmap of its metacells, with its default annotations.
    """
    adata = AnnData(
        X=np.array([[0.1, 0.3], [0.2, 0.2], [0.3, 0.1]], dtype="float32"),
        obs=pd.DataFrame({"cell_type": ["T1", "T2", "T1"]}, index=["M1", "M2", "M3"]),
        var=pd.DataFrame({"marker_gene": [True, True], "lateral_gene": [False, True]}, index=["A", "B"]),
    )
    type_colors_csv = tmp_path / "type_colors.csv"
    type_colors_csv.write_text("type,color\nT1,red\nT2,blue\n")
    source = mw.AnnDataWidgets(adata, type_property="cell_type", type_colors_csv=str(type_colors_csv))
    graph = source.genes_heatmap(entries=[mw.OfTypes(types=["T1"])]).graph()
    assert _list(graph.data.columns.entities.names) == ["M1", "M3"]
    assert [annotation.colors.title for annotation in graph.data.rows.annotations] == ["lateral"]
    assert [annotation.colors.title for annotation in graph.data.columns.annotations] == ["type"]
