"""
Test the widgets for editing the arguments of properties and tweaks.
"""

from typing import Any
from typing import List
from typing import Tuple

from dafpy.julia_import import DEFAULT

import metacellswidgets as mw
from metacellswidgets.common import Arguments
from metacellswidgets.editors import ArgumentsEditor
from metacellswidgets.editors import AxisPicker
from metacellswidgets.editors import GenePicker
from metacellswidgets.editors import ListEditor
from metacellswidgets.editors import NamePicker
from metacellswidgets.editors import PickerEditor
from metacellswidgets.editors import PropertyPicker
from metacellswidgets.properties import Slot

from .test_daf_widgets import _full_daf


class _Row(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    """
    A row of a list, whose value is picked directly.
    """

    def __init__(self, current: Arguments | None) -> None:
        super().__init__()
        self.pick(current)

    def pick(self, value: Arguments | None) -> None:
        """
        Pick the ``value``, as a user would.
        """
        self.value = value
        self.is_blank = value is None


def _parts(editor: ListEditor) -> Tuple[Any, Any]:
    """
    The reset button and the box of the rows of a list editor.
    """
    reset, rows_box = editor.children[0].children[0].children
    return reset, rows_box


def test_list_editor() -> None:
    """
    A list editor starts with a row per object, and ends with a blank row. Picking in the blank row adds it to the list,
    and adds a new blank row. Rows move up and down (but not past either end), and are removed; removing all of them
    gives an empty list, not ``None``. Without a default, there is no reset button.
    """
    first, second, third = mw.Title(text="A"), mw.Title(text="B"), mw.Title(text="C")
    editor = ListEditor(_Row, [first, second], title="Titles")
    assert editor.value == [first, second]
    assert editor.children[0].titles == ("Titles",)
    assert editor.children[0].selected_index is None
    reset, rows_box = _parts(editor)
    assert len(rows_box.children) == 3

    rows_box.children[2].pick(third)
    assert editor.value == [first, second, third]
    assert len(rows_box.children) == 4

    rows_box.children[2].children[1].click()
    assert editor.value == [first, third, second]
    rows_box.children[0].children[1].click()
    rows_box.children[2].children[2].click()
    assert editor.value == [first, third, second]

    for _ in range(3):
        rows_box.children[0].children[3].click()
    assert editor.value == []
    assert reset.layout.display == "none"


def test_list_editor_hidden_rows() -> None:
    """
    A row which isn't valid is hidden and left out of the value, until it is valid again. Moving a row swaps it with the
    adjacent shown row, each with the hidden rows after it. A removed row is closed.
    """
    first, hidden, second = mw.Title(text="A"), mw.Title(text="X"), mw.Title(text="B")
    rows: List[_Row] = []

    def make_row(current: Arguments | None) -> _Row:
        row = _Row(current)
        rows.append(row)
        return row

    editor = ListEditor(make_row, [first, hidden, second], title="Titles")
    rows[1].value = None
    rows[1].is_valid = False
    _reset, rows_box = _parts(editor)
    assert editor.value == [first, second]
    assert len(rows_box.children) == 3

    rows_box.children[1].children[1].click()
    assert editor.value == [second, first]
    rows[1].value = hidden
    rows[1].is_valid = True
    assert editor.value == [second, first, hidden]

    assert rows[2].comm is not None
    rows_box.children[0].children[3].click()
    assert editor.value == [first, hidden]
    assert rows[2].comm is None


def test_list_editor_default() -> None:
    """
    Given ``DEFAULT``, a list editor shows the default, and its value stays ``DEFAULT`` until the first change. The reset
    button returns to the default. Given ``None``, it starts empty.
    """
    first, second = mw.Title(text="A"), mw.Title(text="B")
    editor = ListEditor(_Row, DEFAULT, default=[first], title="Titles")
    reset, rows_box = _parts(editor)
    assert editor.value is DEFAULT
    assert editor.intended() is DEFAULT
    assert reset.layout.display == "none"
    assert rows_box.children[0].children[0].value == first

    rows_box.children[0].children[0].pick(second)
    assert editor.value == [second]
    assert reset.layout.display is None

    reset.click()
    _reset, rows_box = _parts(editor)
    assert editor.value is DEFAULT
    assert rows_box.children[0].children[0].value == first

    assert ListEditor(_Row, None, default=[first], title="Titles").value == []


def test_list_editor_axis_default() -> None:
    """
    A list editor following an axis shows the default of the new axis when the axis changes. A changed list keeps its
    rows, and the reset button returns to the default of the current axis.
    """
    title_per_axis = {"metacell": mw.Title(text="M"), "block": mw.Title(text="B")}
    axis = AxisPicker(mw.DafWidgets(_full_daf()), ["metacell", "block"])
    editor = ListEditor(_Row, DEFAULT, axis=axis, default=lambda axis_name: [title_per_axis[axis_name]], title="Titles")
    _reset, rows_box = _parts(editor)
    assert rows_box.children[0].children[0].value == title_per_axis["metacell"]

    axis.children[0].value = "block"
    reset, rows_box = _parts(editor)
    assert editor.value is DEFAULT
    assert rows_box.children[0].children[0].value == title_per_axis["block"]

    changed = mw.Title(text="X")
    rows_box.children[0].children[0].pick(changed)
    axis.children[0].value = "metacell"
    assert editor.value == [changed]

    reset.click()
    _reset, rows_box = _parts(editor)
    assert editor.value is DEFAULT
    assert rows_box.children[0].children[0].value == title_per_axis["metacell"]


def test_property_picker_axis_default() -> None:
    """
    A property picker following an axis shows the default of the new axis when the axis changes.
    """
    axis = AxisPicker(mw.DafWidgets(_full_daf()), ["metacell", "block"])
    picker = PropertyPicker(
        mw.DafWidgets(_full_daf()),
        Slot.COLORS,
        axis,
        DEFAULT,
        default=lambda axis_name: mw.Type() if axis_name == "metacell" else None,
    )
    assert picker.value is DEFAULT
    assert picker.children[0].value is mw.Type

    axis.children[0].value = "block"
    assert picker.value is None
    assert picker.children[0].value is None

    axis.children[0].value = "metacell"
    assert picker.children[0].value is mw.Type


class _Genes:
    """
    A source of three genes, two of them markers.
    """

    def gene_choices(self, *, markers_only: bool = False) -> List[Tuple[str, str]]:
        """
        The genes, with their flags.
        """
        choices = [("A M", "A"), ("B", "B"), ("C M T", "C")]
        return [choice for choice in choices if not markers_only or " M" in choice[0]]


def test_gene_picker() -> None:
    """
    Picking a gene by its label gives its name. The choices start restricted to the markers, since the source has some.
    """
    picker = GenePicker(_Genes())
    assert picker.value is None
    assert picker._markers_only.value
    assert list(picker._combobox.options) == ["A M", "C M T"]

    picker._markers_only.value = False
    assert list(picker._combobox.options) == ["A M", "B", "C M T"]

    picker._combobox.value = "C M T"
    assert picker.value == "C"

    picker._combobox.value = ""
    assert picker.value is None


def test_gene_picker_current() -> None:
    """
    The picker starts with the current gene, which is one of the choices even if it isn't a marker.
    """
    picker = GenePicker(_Genes(), "B")
    assert picker.value == "B"
    assert picker._combobox.value == "B"
    assert list(picker._combobox.options) == ["A M", "B", "C M T"]


def test_gene_picker_markers_only() -> None:
    """
    Restricting to markers keeps the picked gene, marker or not, and drops the other genes which aren't markers.
    """
    picker = GenePicker(_Genes(), "C")
    picker._markers_only.value = False
    picker._markers_only.value = True
    assert list(picker._combobox.options) == ["A M", "C M T"]
    assert picker.value == "C"

    picker = GenePicker(_Genes(), "B")
    picker._markers_only.value = False
    picker._markers_only.value = True
    assert picker.value == "B"
    assert picker._combobox.value == "B"


def test_gene_picker_without_markers() -> None:
    """
    With no marker genes, the choices start unrestricted.
    """

    class NoMarkers:  # pylint: disable=too-few-public-methods
        """
        A source of genes, none of them a marker.
        """

        def gene_choices(self, *, markers_only: bool = False) -> List[Tuple[str, str]]:
            """
            The genes, if not restricted to the markers.
            """
            return [] if markers_only else [("A", "A"), ("B", "B")]

    picker = GenePicker(NoMarkers())
    assert not picker._markers_only.value
    assert list(picker._combobox.options) == ["A", "B"]


def test_name_picker() -> None:
    """
    Picking a name gives it; a current name which isn't one of the names is ignored.
    """
    picker = NamePicker(["is_doublet", "is_outlier"], "is_outlier")
    assert picker.value == "is_outlier"
    picker._dropdown.value = "is_doublet"
    assert picker.value == "is_doublet"

    assert NamePicker(["is_doublet"], "is_missing").value is None


def test_argument_editor() -> None:
    """
    The editor's value is the property built from the picked argument.
    """
    picker = GenePicker(_Genes())
    editor = PickerEditor(picker, mw.GeneExpression)
    assert editor.value is None

    picker._combobox.value = "A M"
    assert editor.value == mw.GeneExpression("A")

    picker._combobox.value = ""
    assert editor.value is None

    assert PickerEditor(GenePicker(_Genes(), "B"), mw.GeneExpression).value == mw.GeneExpression("B")
