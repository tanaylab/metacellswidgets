"""
Test the pickers of axes and properties.
"""

from typing import Optional

from dafpy.julia_import import DEFAULT

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
        "MeanTotalUMIsPerCell",
        "NCells",
        "TotalUMIs",
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
    When the axis changes, a property the new axis has is kept, with its arguments. Any other isn't valid, and the
    picker's value is ``None``, until the axis changes back. A change while it isn't valid replaces it.
    """
    source = mw.DafWidgets(_full_daf())

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.GeneExpression("A"))
    axis._dropdown.value = "block"
    assert picker.value == mw.GeneExpression("A")
    assert ("NMetacells", mw.NMetacells) in picker._dropdown.options

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.Block())
    assert picker.is_valid
    axis._dropdown.value = "block"
    assert picker.value is None
    assert not picker.is_valid
    axis._dropdown.value = "metacell"
    assert picker.value == mw.Block()
    assert picker.is_valid

    axis._dropdown.value = "block"
    picker._dropdown.value = mw.NMetacells
    assert picker.value == mw.NMetacells()
    assert picker.is_valid
    axis._dropdown.value = "metacell"
    assert picker.value is None
    axis._dropdown.value = "block"
    assert picker.value == mw.NMetacells()

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.BooleanMask("is_doublet"))
    assert picker.value == mw.BooleanMask("is_doublet")
    axis._dropdown.value = "block"
    assert picker.value is None


def test_property_picker_on_axis_change() -> None:
    """
    A function may decide which property the slot holds when the axis changes. When the axis changes back, the slot
    holds its property again.
    """
    source = mw.DafWidgets(_full_daf())

    def _to_type(old_axis: str, new_axis: str, current: Optional[mw.Property]) -> Optional[mw.Property]:
        assert (old_axis, new_axis, current) == ("metacell", "block", mw.Block())
        return mw.Type()

    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.Block(), on_axis_change=_to_type)
    axis._dropdown.value = "block"
    assert picker.value == mw.Type()
    axis._dropdown.value = "metacell"
    assert picker.value == mw.Block()


def test_property_picker_close() -> None:
    """
    A closed picker no longer follows its axis.
    """
    source = mw.DafWidgets(_full_daf())
    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, mw.Block())
    picker.close()
    axis._dropdown.value = "block"
    assert picker.value == mw.Block()


def test_property_picker_default() -> None:
    """
    Given ``DEFAULT``, a picker shows its default while its value stays ``DEFAULT``. A change makes the value explicit,
    and the reset button returns to the default. A property which no longer fits the axis gives way to the default,
    until the axis changes back. So does a given property which doesn't fit the axis. Given ``None``, a picker with a
    default shows nothing.
    """
    source = mw.DafWidgets(_full_daf())
    axis = AxisPicker(source, ["metacell", "block"])
    picker = PropertyPicker(source, Slot.COLORS, axis, DEFAULT, default=mw.Type())
    assert picker.value is DEFAULT
    assert picker._dropdown.value is mw.Type
    assert picker._reset.layout.display == "none"

    picker._dropdown.value = mw.Block
    assert picker.value == mw.Block()
    assert picker._reset.layout.display is None

    picker._reset.click()
    assert picker.value is DEFAULT
    assert picker._dropdown.value is mw.Type

    picker._dropdown.value = mw.Block
    axis._dropdown.value = "block"
    assert picker.value is DEFAULT
    assert picker._dropdown.value is mw.Type
    axis._dropdown.value = "metacell"
    assert picker.value == mw.Block()
    assert picker._dropdown.value is mw.Block

    given = PropertyPicker(source, Slot.COLORS, "block", mw.Block(), default=mw.Type())
    assert given.value is DEFAULT
    assert given._dropdown.value is mw.Type
    assert not given.is_valid

    nothing = PropertyPicker(source, Slot.COLORS, "metacell", None, default=mw.Type())
    assert nothing.value is None
    assert nothing._dropdown.value is None
