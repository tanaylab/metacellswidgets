"""
Test the widgets for editing the arguments of properties.
"""

from typing import List
from typing import Tuple

import metacellswidgets as mw
from metacellswidgets.editors import ArgumentEditor
from metacellswidgets.editors import GenePicker
from metacellswidgets.editors import NamePicker


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
    editor = ArgumentEditor(picker, mw.GeneExpression)
    assert editor.value is None

    picker._combobox.value = "A M"
    assert editor.value == mw.GeneExpression("A")

    picker._combobox.value = ""
    assert editor.value is None

    assert ArgumentEditor(GenePicker(_Genes(), "B"), mw.GeneExpression).value == mw.GeneExpression("B")
