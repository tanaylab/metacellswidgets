"""
Test the ``AnnData`` kind of data source.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import somegraphspy as sg
from anndata import AnnData  # type: ignore

import metacellswidgets as mw
from metacellswidgets.properties import Slot


def _source(tmp_path: Path, *, type_property: str = "cell_type") -> mw.AnnDataWidgets:
    """
    Three metacells of three genes, with their types and the colors of the types.
    """
    adata = AnnData(
        X=np.array([[0.1, 0.3, 0.6], [0.2, 0.2, 0.6], [0.3, 0.1, 0.6]], dtype="float32"),
        obs=pd.DataFrame({"cell_type": ["T1", "T2", "T1"]}, index=["M1", "M2", "M3"]),
        var=pd.DataFrame(
            {"excluded_gene": [False, False, True], "marker_gene": [True, False, False]}, index=["A", "B", "C"]
        ),
    )
    type_colors_csv = tmp_path / "type_colors.csv"
    type_colors_csv.write_text("type,color\nT1,red\nT2,blue\n")
    return mw.AnnDataWidgets(adata, type_property=type_property, type_colors_csv=str(type_colors_csv))


def test_properties(tmp_path: Path) -> None:
    """
    The metacells have their types and the expression of genes.
    """
    source = _source(tmp_path)
    assert source.properties(axis="metacell", slot=Slot.COLORS) == [mw.Type, mw.GeneExpression]
    assert source.properties(axis="metacell", slot=Slot.SIZES) == [mw.GeneExpression]
    assert not source.properties(axis="block", slot=Slot.COLORS)


def test_properties_without_types(tmp_path: Path) -> None:
    """
    Without the type property, the metacells have no types.
    """
    source = _source(tmp_path, type_property="missing")
    assert source.properties(axis="metacell", slot=Slot.COLORS) == [mw.GeneExpression]


def test_fill(tmp_path: Path) -> None:
    """
    The types and the expression of a gene fill the colors of a points graph.
    """
    source = _source(tmp_path)
    for prop in (mw.Type(), mw.GeneExpression("B")):
        graph = sg.points_graph()
        sinks: Any = graph.points_colors_vector_fields()
        prop.fill(source, sinks, "metacell")
        assert graph.data.points.colors.vector is not None
        assert len(graph.data.points.colors.vector) == 3


def test_gene_choices(tmp_path: Path) -> None:
    """
    Excluded genes are never offered, and markers are those of the marker column.
    """
    source = _source(tmp_path)
    assert source.gene_choices() == [("A", "A"), ("B", "B")]
    assert source.gene_choices(markers_only=True) == [("A", "A")]


def test_editor(tmp_path: Path) -> None:
    """
    The gene expression has an editor, starting with the current gene.
    """
    editor = mw.GeneExpression.editor(_source(tmp_path), "metacell", mw.GeneExpression("B"))
    assert editor is not None
    assert editor.value == mw.GeneExpression("B")
