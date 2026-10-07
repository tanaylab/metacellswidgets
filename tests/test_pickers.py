"""
Test the pickers of axes and properties.
"""

from typing import Optional

import metacellswidgets as mw
from metacellswidgets.editors import AxisPicker
from metacellswidgets.editors import PropertyPicker
from metacellswidgets.properties import Slot

from .test_daf_widgets import _full_daf
from .test_daf_widgets import _sparse_daf


def test_axis_picker() -> None:
    """
    The choices are the allowed axes the data source has, starting with the current one, or the first one.
    """
    source = mw.DafWidgets(_full_daf())
    assert AxisPicker(source, ["metacell", "block"]).value == "metacell"
    assert AxisPicker(source, ["metacell", "block"], "block").value == "block"

    picker = AxisPicker(mw.DafWidgets(_sparse_daf()), ["metacell", "block"], "block")
    assert picker.value == "metacell"
    assert list(picker._dropdown.options) == ["metacell"]


def test_property_picker_choices() -> None:
    """
    The choices are the properties of the slot for the axis, or none.
    """
    picker = PropertyPicker(mw.DafWidgets(_full_daf()), Slot.SIZES, "metacell")
    assert [label for label, _choice in picker._dropdown.options] == [
        "",
        "GeneExpression",
        "TotalUMIs",
        "NCells",
        "MeanTotalUMIsPerCell",
    ]
    assert picker.value is None


def test_property_picker_pick() -> None:
    """
    Picking a property without arguments gives it; picking one with arguments shows its editor, which gives it.
    """
    picker = PropertyPicker(mw.DafWidgets(_full_daf()), Slot.COLORS, "metacell")

    picker._dropdown.value = mw.Type
    assert picker.value == mw.Type()
    assert not picker._editor_box.children

    picker._dropdown.value = mw.GeneExpression
    assert picker.value is None
    assert picker._editor is not None
    picker._editor.children[0]._combobox.value = "D M"
    assert picker.value == mw.GeneExpression("D")

    picker._dropdown.value = None
    assert picker.value is None
    assert not picker._editor_box.children


def test_property_picker_current() -> None:
    """
    The picker starts with the current property, and its arguments.
    """
    picker = PropertyPicker(mw.DafWidgets(_full_daf()), Slot.COLORS, "metacell", mw.GeneExpression("A"))
    assert picker._dropdown.value is mw.GeneExpression
    assert picker.value == mw.GeneExpression("A")


def test_property_picker_follows_axis() -> None:
    """
    When the axis changes, a property the new axis has is kept, with its arguments; any other is dropped.
    """
    source = mw.DafWidgets(_full_daf())

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.GeneExpression("A"))
    axis._dropdown.value = "block"
    assert picker.value == mw.GeneExpression("A")
    assert ("NMetacells", mw.NMetacells) in picker._dropdown.options

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.Block())
    axis._dropdown.value = "block"
    assert picker.value is None

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.BooleanMask("is_doublet"))
    assert picker.value == mw.BooleanMask("is_doublet")
    axis._dropdown.value = "block"
    assert picker.value is None


def test_property_picker_on_axis_change() -> None:
    """
    A function may decide which property the slot holds when the axis changes.
    """
    source = mw.DafWidgets(_full_daf())

    def _to_type(old_axis: str, new_axis: str, current: Optional[mw.Property]) -> Optional[mw.Property]:
        assert (old_axis, new_axis, current) == ("metacell", "block", mw.Block())
        return mw.Type()

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.Block(), on_axis_change=_to_type)
    axis._dropdown.value = "block"
    assert picker.value == mw.Type()
