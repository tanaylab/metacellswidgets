"""
Test the widgets for editing the arguments of properties and tweaks.
"""

from typing import Any
from typing import List
from typing import Optional
from typing import Tuple

import metacellswidgets as mw
from metacellswidgets.common import Arguments
from metacellswidgets.editors import ArgumentsEditor
from metacellswidgets.editors import GenePicker
from metacellswidgets.editors import ListEditor
from metacellswidgets.editors import NamePicker
from metacellswidgets.editors import PickerEditor


class _Row(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    """
    A row of a list, whose value is picked directly.
    """

    def __init__(self, current: Optional[Arguments]) -> None:
        super().__init__()
        self.pick(current)

    def pick(self, value: Optional[Arguments]) -> None:
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
    gives an empty list, not ``None``.
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
    assert reset.layout.display is None


def test_list_editor_default() -> None:
    """
    Without a current list, a list editor shows the default, and its value stays ``None`` until the first change. The
    reset button returns to the default.
    """
    first, second = mw.Title(text="A"), mw.Title(text="B")
    editor = ListEditor(_Row, None, default=[first], title="Titles")
    reset, rows_box = _parts(editor)
    assert editor.value is None
    assert reset.layout.display == "none"
    assert rows_box.children[0].children[0].value == first

    rows_box.children[0].children[0].pick(second)
    assert editor.value == [second]
    assert reset.layout.display is None

    reset.click()
    _reset, rows_box = _parts(editor)
    assert editor.value is None
    assert rows_box.children[0].children[0].value == first


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
    Picking a gene by its label gives its name.
    """
    picker = GenePicker(_Genes())
    assert picker.value is None
    assert list(picker._combobox.options) == ["A M", "B", "C M T"]

    picker._combobox.value = "C M T"
    assert picker.value == "C"

    picker._combobox.value = ""
    assert picker.value is None


def test_gene_picker_current() -> None:
    """
    The picker starts with the current gene.
    """
    picker = GenePicker(_Genes(), "B")
    assert picker.value == "B"
    assert picker._combobox.value == "B"


def test_gene_picker_markers_only() -> None:
    """
    Restricting to markers keeps a marker gene and drops any other.
    """
    picker = GenePicker(_Genes(), "C")
    picker._markers_only.value = True
    assert list(picker._combobox.options) == ["A M", "C M T"]
    assert picker.value == "C"

    picker = GenePicker(_Genes(), "B")
    picker._markers_only.value = True
    assert picker.value is None
    assert picker._combobox.value == ""


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
