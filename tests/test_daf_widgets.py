"""
Test the ``Daf`` kind of data source.
"""

from typing import Any

import dafpy as dp
import numpy as np
import pytest
import somegraphspy as sg

import metacellswidgets as mw
from metacellswidgets.properties import Slot


def _full_daf() -> dp.DafWriter:
    """
    Metacells and blocks with all the data the built-in properties use.
    """
    daf = dp.memory_daf(name="full")
    daf.add_axis("gene", ["A", "B", "C", "D"])
    daf.add_axis("metacell", ["M1", "M2", "M3"])
    daf.add_axis("block", ["B1", "B2"])
    daf.add_axis("type", ["T1", "T2"])

    daf.set_vector("gene", "is_excluded", np.array([False, False, True, False]))
    daf.set_vector("gene", "is_lateral", np.array([False, True, False, False]))
    daf.set_vector("gene", "is_marker", np.array([True, False, True, True]))
    daf.set_vector("gene", "is_regulator", np.array([True, False, False, False]))

    daf.set_vector("type", "color", np.array(["red", "blue"]))
    daf.set_vector("type", "global_flow_order", np.array([2, 1], dtype="uint32"))

    daf.set_vector("metacell", "type", np.array(["T1", "T2", "T1"]))
    daf.set_vector("metacell", "block", np.array(["B1", "B1", "B2"]))
    daf.set_vector("metacell", "n_cells", np.array([10, 20, 30], dtype="uint32"))
    daf.set_vector("metacell", "total_UMIs", np.array([100, 200, 300], dtype="uint32"))
    daf.set_vector("metacell", "is_doublet", np.array([False, True, False]))

    daf.set_vector("block", "type", np.array(["T1", "T2"]))
    daf.set_vector("block", "n_cells", np.array([30, 30], dtype="uint32"))
    daf.set_vector("block", "n_metacells", np.array([2, 1], dtype="uint32"))
    daf.set_vector("block", "total_UMIs", np.array([300, 300], dtype="uint32"))

    daf.set_matrix(
        "gene",
        "metacell",
        "linear_fraction",
        np.array([[0.1, 0.2, 0.3], [0.2, 0.2, 0.2], [0.3, 0.2, 0.1], [0.4, 0.4, 0.4]], dtype="float32", order="F"),
    )
    daf.set_matrix(
        "gene",
        "block",
        "linear_fraction",
        np.array([[0.1, 0.3], [0.2, 0.2], [0.3, 0.1], [0.4, 0.4]], dtype="float32", order="F"),
    )
    return daf


def _sparse_daf() -> dp.DafWriter:
    """
    Metacells with only their cell counts.
    """
    daf = dp.memory_daf(name="sparse")
    daf.add_axis("gene", ["A", "B"])
    daf.add_axis("metacell", ["M1", "M2"])
    daf.set_vector("metacell", "n_cells", np.array([10, 20], dtype="uint32"))
    return daf


def test_registered_properties() -> None:
    """
    The properties offered for each axis.
    """
    assert mw.DafWidgets.registered_properties("metacell") == [
        mw.Type,
        mw.Block,
        mw.GeneExpression,
        mw.TotalUMIs,
        mw.NCells,
        mw.MeanTotalUMIsPerCell,
        mw.BooleanMask,
        mw.GlobalFlowOrder,
    ]
    assert mw.NMetacells in mw.DafWidgets.registered_properties("block")
    assert mw.Block not in mw.DafWidgets.registered_properties("block")


def test_properties_of_full_daf() -> None:
    """
    All the registered properties exist in the full data set, offered per slot.
    """
    source = mw.DafWidgets(_full_daf())
    assert source.properties(axis="metacell", slot=Slot.COLORS) == mw.DafWidgets.registered_properties("metacell")[:-1]
    assert source.properties(axis="metacell", slot=Slot.SIZES) == [
        mw.GeneExpression,
        mw.TotalUMIs,
        mw.NCells,
        mw.MeanTotalUMIsPerCell,
    ]
    assert source.properties(axis="metacell", slot=Slot.GROUPS) == [mw.Type, mw.Block, mw.GlobalFlowOrder]
    assert source.properties(axis="metacell", slot=Slot.MASK) == [mw.BooleanMask]
    assert source.properties(axis="block", slot=Slot.SIZES) == [
        mw.GeneExpression,
        mw.TotalUMIs,
        mw.NCells,
        mw.NMetacells,
        mw.MeanCellsPerMetacell,
        mw.MeanTotalUMIsPerMetacell,
        mw.MeanTotalUMIsPerCell,
    ]


def test_properties_of_sparse_daf() -> None:
    """
    Only the properties the data set has are offered.
    """
    source = mw.DafWidgets(_sparse_daf())
    assert source.properties(axis="metacell", slot=Slot.COLORS) == [mw.NCells]
    assert not source.properties(axis="block", slot=Slot.COLORS)


@pytest.mark.parametrize(
    "prop, axis",
    [
        (mw.Type(), "metacell"),
        (mw.Block(), "metacell"),
        (mw.GeneExpression("A"), "metacell"),
        (mw.TotalUMIs(), "metacell"),
        (mw.NCells(), "metacell"),
        (mw.MeanTotalUMIsPerCell(), "metacell"),
        (mw.BooleanMask("is_doublet"), "metacell"),
        (mw.GlobalFlowOrder(), "metacell"),
        (mw.Type(), "block"),
        (mw.GeneExpression("A"), "block"),
        (mw.NMetacells(), "block"),
        (mw.MeanCellsPerMetacell(), "block"),
        (mw.MeanTotalUMIsPerMetacell(), "block"),
    ],
)
def test_fill(prop: mw.Property, axis: str) -> None:
    """
    Each property fills the colors of a points graph with a value per entry of the axis.
    """
    daf = _full_daf()
    graph = sg.points_graph()
    sinks: Any = graph.points_colors_vector_fields()
    prop.fill(mw.DafWidgets(daf), sinks, axis)
    assert graph.data.points.colors.vector is not None
    assert len(graph.data.points.colors.vector) == len(daf.axis_np_vector(axis))
    assert graph.data.points.entities.names is not None
    assert list(graph.data.points.entities.names) == list(daf.axis_np_vector(axis))


def test_gene_choices() -> None:
    """
    Excluded genes are never offered, and the flags follow each name.
    """
    source = mw.DafWidgets(_full_daf())
    assert source.gene_choices() == [("A M R", "A"), ("B L", "B"), ("D M", "D")]
    assert source.gene_choices(markers_only=True) == [("A M R", "A"), ("D M", "D")]
    assert mw.DafWidgets(_sparse_daf()).gene_choices() == [("A", "A"), ("B", "B")]


def test_editors() -> None:
    """
    The properties with arguments have editors, starting with the current property; the others have none.
    """
    source = mw.DafWidgets(_full_daf())

    editor = mw.GeneExpression.editor(source, "metacell", mw.GeneExpression("D"))
    assert editor is not None
    assert editor.value == mw.GeneExpression("D")

    editor = mw.BooleanMask.editor(source, "metacell", None)
    assert editor is not None
    assert editor.value is None
    editor = mw.BooleanMask.editor(source, "metacell", mw.BooleanMask("is_doublet"))
    assert editor is not None
    assert editor.value == mw.BooleanMask("is_doublet")

    assert mw.Type.editor(source, "metacell", None) is None


def test_boolean_vectors() -> None:
    """
    The Boolean vectors of an axis are found by their element type.
    """
    source = mw.DafWidgets(_full_daf())
    assert source.boolean_vectors("metacell") == ["is_doublet"]
    assert not source.boolean_vectors("block")
