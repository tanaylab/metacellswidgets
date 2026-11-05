"""
Test that every editor follows the rules of showing values and their defaults.

Every value field (a dropdown, a combo box, a number or a text) has a dotted border while it shows its default, and a
solid one otherwise. Its label is a widget of its own, so the field has no ``description``. A Boolean is a dropdown, so
there is no checkbox, other than the one of each number of a ``Size`` or a ``TicksAngles`` tweak, whose default isn't a
number. There are no "Reset to default" buttons, since changing a value back to its default is how to return to it. A
dropdown is as wide as its options, a combobox as its labels need (in ``ch``), and a text or number field has a fixed
width, so none takes the default width.
"""

from pathlib import Path
from typing import Iterator
from typing import List

import somegraphspy as sg
from ipywidgets import BoundedIntText  # type: ignore
from ipywidgets import Button  # type: ignore
from ipywidgets import Checkbox  # type: ignore
from ipywidgets import Combobox  # type: ignore
from ipywidgets import Dropdown  # type: ignore
from ipywidgets import IntText  # type: ignore
from ipywidgets import Text  # type: ignore
from ipywidgets import Widget  # type: ignore

import metacellswidgets as mw
from metacellswidgets.editors import ClassPicker
from metacellswidgets.editors import PropertyPicker
from metacellswidgets.properties import Slot
from metacellswidgets.tweaks import _SizeEditor
from metacellswidgets.tweaks import _TicksAnglesEditor

from .test_anndata_widgets import _source
from .test_entries import _daf

# The borders of a field showing its default, and of a field showing another value.
_BORDERS = ("1px dotted black", "1px solid black")


def _check(widget: Widget, *, is_in_optional_numbers: bool = False) -> None:
    """
    Check the rules in the ``widget`` and in all the widgets inside it.
    """
    is_in_optional_numbers = is_in_optional_numbers or isinstance(widget, (_SizeEditor, _TicksAnglesEditor))
    if isinstance(widget, Button):
        assert widget.description != "Reset to default"
    if isinstance(widget, Checkbox):
        assert is_in_optional_numbers, f"a checkbox outside a Size or TicksAngles tweak: {widget}"
    if isinstance(widget, (Dropdown, Text, IntText, BoundedIntText)):
        assert widget.layout.border in _BORDERS, f"a value field without the default's border: {widget}"
        assert not widget.description, f"a value field with its own label: {widget.description}"
    if isinstance(widget, Dropdown):
        assert widget.layout.width == "max-content", f"a dropdown not as wide as its options: {widget}"
    elif isinstance(widget, Combobox):
        assert widget.layout.width.endswith("ch"), f"a combobox not as wide as its options: {widget}"
    elif isinstance(widget, (Text, IntText, BoundedIntText)):
        assert widget.layout.width, f"a text or number field of the default width: {widget}"
    for child in getattr(widget, "children", ()):
        _check(child, is_in_optional_numbers=is_in_optional_numbers)


def _with_each_choice(picker: ClassPicker) -> Iterator[ClassPicker]:
    """
    The ``picker``, with each of its choices of the package picked in turn (other tests register classes of their own).
    """
    for _label, choice in picker._dropdown.options:
        if choice is None or choice.__module__.startswith("metacellswidgets."):
            picker._dropdown.value = choice
            yield picker


def _sources(tmp_path: Path) -> List[mw.DafWidgets | mw.AnnDataWidgets]:
    """
    A source of each kind.
    """
    return [mw.DafWidgets(_daf()), _source(tmp_path)]


def test_forms_editors(tmp_path: Path) -> None:
    """
    The editors of the forms, and of their tweaks, follow the rules.
    """
    for source in _sources(tmp_path):
        for form in (source.gene_gene(x_gene="A", y_gene="B"), source.genes_heatmap()):
            _check(form.editor())
            _check(form._tweaks_editor())


def test_properties_editors(tmp_path: Path) -> None:
    """
    The editor of each property, in each slot of each axis, with its look arguments, follows the rules.
    """
    for source in _sources(tmp_path):
        for axis in ("gene", "metacell", "block"):
            if source.has_axis(axis):
                for slot in Slot:
                    for picker in _with_each_choice(PropertyPicker(source, slot, axis)):
                        _check(picker)


def test_tweaks_editors(tmp_path: Path) -> None:
    """
    The editor of each tweak follows the rules, with each dimension of a size given or left to its default.
    """
    for source in _sources(tmp_path):
        for picker in _with_each_choice(mw.TweakPicker(source, sg.PointsGraph, None)):
            _check(picker)
    size = mw.Size.editor(mw.DafWidgets(_daf()), None, mw.Size(width=640))
    _check(size)


def test_entries_editors(tmp_path: Path) -> None:
    """
    The editor of each selection of genes, and of each filter of entries on each axis, follows the rules.
    """
    for source in _sources(tmp_path):
        for picker in _with_each_choice(mw.GeneSelectionPicker(source)):
            _check(picker)
        for axis in ("metacell", "block"):
            if source.has_axis(axis):
                for picker in _with_each_choice(mw.EntryFilterPicker(source, axis)):
                    _check(picker)
