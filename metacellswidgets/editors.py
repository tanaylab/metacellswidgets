"""
Widgets for editing the arguments of properties, shared by all kinds of data sources.

A kind of data source supplies the data these widgets show (e.g., its genes); the widgets don't depend on the kind.
Each widget has an observable ``value``: the editors' is the property (or ``None`` while its arguments are
incomplete), and the pickers' is the chosen string (or ``None`` while nothing is chosen).
"""

from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Protocol
from typing import Sequence
from typing import Tuple

import traitlets  # type: ignore
from ipywidgets import Checkbox  # type: ignore
from ipywidgets import Combobox  # type: ignore
from ipywidgets import Dropdown  # type: ignore
from ipywidgets import HBox  # type: ignore

from .properties import Property

__all__: List[str] = [
    "ArgumentEditor",
    "GeneChoices",
    "GenePicker",
    "NamePicker",
    "Picker",
    "PropertyEditor",
]


class GeneChoices(Protocol):  # pylint: disable=too-few-public-methods
    """
    A data source which can list its genes for picking one.
    """

    def gene_choices(self, *, markers_only: bool = False) -> List[Tuple[str, str]]:
        """
        The (label, name) of each gene which may be picked, or only of the marker genes.
        """


class PropertyEditor(HBox):  # pylint: disable=too-many-ancestors,abstract-method
    """
    The base class of the widgets editing the arguments of a property. Its ``value`` is the property, or ``None`` while
    its arguments are incomplete.
    """

    value = traitlets.Any(None, allow_none=True)


class Picker(HBox):  # pylint: disable=too-many-ancestors,abstract-method
    """
    The base class of the widgets picking one of some choices. Its ``value`` is the chosen string, or ``None`` while
    nothing is chosen.
    """

    value = traitlets.Any(None, allow_none=True)


class GenePicker(Picker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick a gene of a ``source``, by typing (part of) its label, starting with the ``current`` gene (if any). A toggle
    restricts the choices to the marker genes.
    """

    def __init__(self, source: GeneChoices, current: Optional[str] = None) -> None:
        super().__init__()
        self._source = source
        self._name_per_label: Dict[str, str] = {}
        self._combobox = Combobox(placeholder="Gene", ensure_option=True)
        self._markers_only = Checkbox(value=False, description="Markers only", indent=False)
        self.children = [self._combobox, self._markers_only]
        self._reset_choices()
        if current is not None:
            label = self._label_of(current)
            if label is not None:
                self._combobox.value = label
                self.value = current
        self._combobox.observe(self._on_combobox_change, names="value")
        self._markers_only.observe(self._on_markers_only_change, names="value")

    def _reset_choices(self) -> None:
        # Fill the choices of the combobox, according to the markers only toggle.
        choices = self._source.gene_choices(markers_only=self._markers_only.value)
        self._name_per_label = dict(choices)
        self._combobox.options = [label for label, _name in choices]

    def _label_of(self, name: str) -> Optional[str]:
        # The label of the gene with the ``name``, if it is one of the choices.
        for label, label_name in self._name_per_label.items():
            if label_name == name:
                return label
        return None

    def _on_combobox_change(self, change: Dict) -> None:
        self.value = self._name_per_label.get(change["new"])

    def _on_markers_only_change(self, _change: Dict) -> None:
        current = self.value
        self._reset_choices()
        label = None if current is None else self._label_of(current)
        self._combobox.value = "" if label is None else label
        self.value = None if label is None else current


class NamePicker(Picker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick one of some ``names``, starting with the ``current`` one (if any, and if it is one of them).
    """

    def __init__(self, names: Sequence[str], current: Optional[str] = None) -> None:
        super().__init__()
        is_current = current is not None and current in names
        self._dropdown = Dropdown(options=list(names), value=current if is_current else None)
        self.children = [self._dropdown]
        self.value = current if is_current else None
        self._dropdown.observe(self._on_dropdown_change, names="value")

    def _on_dropdown_change(self, change: Dict) -> None:
        self.value = change["new"]


class ArgumentEditor(PropertyEditor):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Edit a property with a single argument, picked by a ``picker``. The ``build`` function makes the property from the
    picked string.
    """

    def __init__(self, picker: Picker, build: Callable[[str], Property]) -> None:
        super().__init__()
        self._build = build
        self.children = [picker]
        self.value = None if picker.value is None else build(picker.value)
        picker.observe(self._on_picker_change, names="value")

    def _on_picker_change(self, change: Dict) -> None:
        self.value = None if change["new"] is None else self._build(change["new"])
