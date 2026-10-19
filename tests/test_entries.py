"""
Test the selections of genes and the filters of entries.
"""

from pathlib import Path

import dafpy as dp
import numpy as np
import pandas as pd
from anndata import AnnData  # type: ignore

import metacellswidgets as mw
from metacellswidgets.editors import AxisPicker

from .test_daf_widgets import _full_daf


def _daf() -> dp.DafWriter:
    """
    The full data set, with marker ranks, skeleton genes, and neighborhoods and environments of the blocks.
    """
    daf = _full_daf()
    daf.set_vector("gene", "marker_rank", np.array([1, 3, 2, np.iinfo(np.uint32).max], dtype="uint32"))
    daf.set_vector("gene", "is_skeleton", np.array([True, False, False, True]))
    # The neighborhood of ``B1`` is itself, and that of ``B2`` is both blocks.
    daf.set_matrix("block", "block", "is_in_neighborhood", np.array([[True, True], [False, True]], order="F"))
    # The environment of ``B1`` is ``M1`` and ``M2``, and that of ``B2`` is ``M2`` and ``M3``.
    daf.set_matrix(
        "metacell", "block", "is_in_environment", np.array([[True, False], [True, True], [False, True]], order="F")
    )
    return daf


def test_gene_selections() -> None:
    """
    Each selection of genes gives the genes its data source does, and the picker shows the default while its value
    stays ``None``.
    """
    source = mw.DafWidgets(_daf())
    assert list(mw.TopMarkers(count=2).genes(source)) == [1, 3]
    assert list(mw.SkeletonGenes().genes(source)) == [1, 4]
    assert mw.GeneList(names=["B", "A"]).genes(source) == ["B", "A"]
    assert mw.TopMarkers().count == 100

    picker = mw.GeneSelectionPicker(source)
    assert picker.value is None
    assert picker._dropdown.value is mw.TopMarkers
    assert [label for label, _choice in picker._dropdown.options] == ["", "GeneList", "SkeletonGenes", "TopMarkers"]


def test_gene_selection_editors() -> None:
    """
    The editors of the selections with arguments start from the current selection.
    """
    source = mw.DafWidgets(_daf())
    editor = mw.TopMarkers.editor(source, mw.TopMarkers(count=7))
    assert editor.value == mw.TopMarkers(count=7)
    editor._count.value = 0
    assert editor.value is None

    editor = mw.GeneList.editor(source, mw.GeneList(names=["B"]))
    assert editor.value == mw.GeneList(names=["B"])


def test_entry_filters() -> None:
    """
    Each filter gives the mask its data source does, and exists only where its data does.
    """
    source = mw.DafWidgets(_daf())
    assert list(mw.OfTypes(types=["T1"]).mask(source, "metacell")) == [True, False, True]
    assert list(mw.InNeighborhood(block="B1").mask(source, "metacell")) == [True, True, False]
    assert list(mw.InNeighborhood(block="B2").mask(source, "block")) == [True, True]
    assert list(mw.InEnvironment(block="B2").mask(source, "metacell")) == [False, True, True]
    assert mw.InEnvironment.exists(source, "metacell")
    assert not mw.InEnvironment.exists(source, "block")
    assert not mw.InNeighborhood.exists(mw.DafWidgets(_full_daf()), "metacell")


def test_entry_filter_on_axis() -> None:
    """
    On the block axis, an environment becomes the neighborhood of the same block, also in a picker following the axis.
    Back on the metacell axis, the picker shows the environment again.
    """
    source = mw.DafWidgets(_daf())
    assert mw.InEnvironment(block="B1").on_axis(source, "block") == mw.InNeighborhood(block="B1")
    assert mw.OfTypes(types=["T1"]).on_axis(source, "block") == mw.OfTypes(types=["T1"])

    axis = AxisPicker(source, ["metacell", "block"])
    picker = mw.EntryFilterPicker(source, axis, mw.InEnvironment(block="B1"))
    assert picker.value == mw.InEnvironment(block="B1")
    axis._dropdown.value = "block"
    assert picker.value == mw.InNeighborhood(block="B1")
    axis._dropdown.value = "metacell"
    assert picker.value == mw.InEnvironment(block="B1")


def test_entry_filter_editors() -> None:
    """
    The editors of the filters pick from the names the data source has, starting from the current filter.
    """
    source = mw.DafWidgets(_daf())
    assert source.type_names() == ["T1", "T2"]
    assert source.block_names() == ["B1", "B2"]
    assert mw.OfTypes.editor(source, mw.OfTypes(types=["T2"])).value == mw.OfTypes(types=["T2"])
    assert mw.InNeighborhood.editor(source, mw.InNeighborhood(block="B2")).value == mw.InNeighborhood(block="B2")
    assert mw.InEnvironment.editor(source, None).value is None


def test_anndata_entries(tmp_path: Path) -> None:
    """
    An ``AnnData`` has the top markers, explicit genes, and types to filter by; nothing about blocks.
    """
    adata = AnnData(
        X=np.array([[0.1, 0.3], [0.2, 0.2], [0.3, 0.1]], dtype="float32"),
        obs=pd.DataFrame({"cell_type": ["T1", "T2", "T1"]}, index=["M1", "M2", "M3"]),
        var=pd.DataFrame({"marker_gene": [True, True]}, index=["A", "B"]),
    )
    type_colors_csv = tmp_path / "type_colors.csv"
    type_colors_csv.write_text("type,color\nT1,red\nT2,blue\n")
    source = mw.AnnDataWidgets(adata, type_property="cell_type", type_colors_csv=str(type_colors_csv))
    assert source.type_names() == ["T1", "T2"]
    assert list(mw.OfTypes(types=["T2"]).mask(source, "metacell")) == [False, True, False]
    assert list(mw.TopMarkers(count=1).genes(source)) == [2]
    assert not mw.InNeighborhood.exists(source, "metacell")
    assert not mw.SkeletonGenes.exists(source)
