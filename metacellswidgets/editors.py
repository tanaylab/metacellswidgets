"""
Widgets for editing the arguments of properties and tweaks, shared by all kinds of data sources.

A kind of data source supplies the data these widgets show (e.g., its genes); the widgets don't depend on the kind.
Each widget has an observable ``value``: the editors' is the property or the tweak (or ``None`` while its arguments are
incomplete), and the pickers' is the chosen string (or ``None`` while nothing is chosen).
"""

from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Protocol
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import Union

import traitlets  # type: ignore
from ipywidgets import Checkbox  # type: ignore
from ipywidgets import Combobox  # type: ignore
from ipywidgets import Dropdown  # type: ignore
from ipywidgets import HBox  # type: ignore
from ipywidgets import Layout  # type: ignore

from .kernel import _on_main_thread
from .properties import Property
from .properties import Slot
from .sources import SourceWidgets

__all__: List[str] = [
    "ArgumentsEditor",
    "AxisPicker",
    "GeneChoices",
    "GenePicker",
    "NamePicker",
    "OnAxisChange",
    "Picker",
    "PickerEditor",
    "PropertyPicker",
]


class GeneChoices(Protocol):  # pylint: disable=too-few-public-methods
    """
    A data source which can list its genes for picking one.
    """

    def gene_choices(self, *, markers_only: bool = False) -> List[Tuple[str, str]]:
        """
        The (label, name) of each gene which may be picked, or only of the marker genes.
        """


class ArgumentsEditor(HBox):  # pylint: disable=too-many-ancestors,abstract-method
    """
    The base class of the widgets editing the arguments of a property or a tweak. Its ``value`` is the property or the
    tweak, or ``None`` while its arguments are incomplete.
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
        _on_main_thread(self._reset_markers_only)

    def _reset_markers_only(self) -> None:
        # Show the choices according to the markers only toggle, keeping the gene if it is one of them.
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


class PickerEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
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


class AxisPicker(Picker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick one of the ``allowed`` axes which the ``source`` has. The picker starts with the ``current`` axis if it is
    one of them, and with the first of them otherwise.
    """

    def __init__(self, source: SourceWidgets, allowed: Sequence[str], current: Optional[str] = None) -> None:
        super().__init__()
        axes = [axis for axis in allowed if source.has_axis(axis)]
        value = current if current in axes else (axes[0] if axes else None)
        self._dropdown = Dropdown(options=axes, value=value)
        self.children = [self._dropdown]
        self.value = value
        self._dropdown.observe(self._on_dropdown_change, names="value")

    def _on_dropdown_change(self, change: Dict) -> None:
        self.value = change["new"]


#: Decides which property a slot holds when the axis it follows changes, given the old axis, the new axis and the
#: current property. Returning a property which doesn't exist for the new axis empties the slot.
OnAxisChange = Callable[[str, str, Optional[Property]], Optional[Property]]


class PropertyPicker(  # pylint: disable=too-many-ancestors,abstract-method,too-many-instance-attributes
    ArgumentsEditor
):
    """
    Pick a property of the ``source`` for a ``slot``, for the entries of the ``axis``, starting with the ``current``
    property (if any). The choices are the properties registered for the source's kind and the axis, which suit the
    slot, and which the source has; or none, leaving the slot empty. Picking a property with arguments shows its editor
    to the right of the choice.

    The ``axis`` may be an :py:class:`AxisPicker` to follow. When its axis changes, the choices change with it. A
    property which is still one of them is kept, with its arguments, if they are valid for the new axis. Otherwise, the
    slot is emptied. An ``on_axis_change`` function may decide this instead.
    """

    def __init__(
        self,
        source: SourceWidgets,
        slot: Slot,
        axis: Union[str, AxisPicker],
        current: Optional[Property] = None,
        *,
        on_axis_change: Optional[OnAxisChange] = None,
    ) -> None:
        super().__init__(layout=Layout(align_items="flex-start"))
        self._source = source
        self._slot = slot
        self._axis = axis if isinstance(axis, str) else axis.value
        self._on_axis_change = on_axis_change
        self._is_updating = False
        self._editor: Optional[ArgumentsEditor] = None
        self._dropdown = Dropdown()
        self._editor_box = HBox(layout=Layout(flex="1 1 auto"))
        self.children = [self._dropdown, self._editor_box]
        self._show(current)
        self._dropdown.observe(self._on_dropdown_change, names="value")
        if isinstance(axis, AxisPicker):
            axis.observe(self._on_axis_picker_change, names="value")

    def _show(self, current: Optional[Property]) -> None:
        # Show the choices for the current axis, with the ``current`` property picked, if it is one of them and its
        # arguments are valid for the axis; otherwise, with nothing picked.
        choices = self._source.properties(axis=self._axis, slot=self._slot)
        property_class = None if current is None else type(current)
        if property_class not in choices:
            current = None
            property_class = None
        self._is_updating = True
        try:
            self._dropdown.options = [("", None)] + [(choice.__name__, choice) for choice in choices]
            self._dropdown.value = property_class
        finally:
            self._is_updating = False
        self._pick(property_class, current)
        if current is not None and self.value is None:
            self._show(None)

    def _pick(self, property_class: Optional[Type[Property]], current: Optional[Property]) -> None:
        # Pick the ``property_class``, starting its editor (if it has one) with the ``current`` property.
        if self._editor is not None:
            self._editor.unobserve(self._on_editor_change, names="value")
            self._editor = None
        if property_class is None:
            self._editor_box.children = []
            self.value = None
            return
        editor = property_class.editor(self._source, self._axis, current)
        if editor is None:
            self._editor_box.children = []
            self.value = property_class()
        else:
            self._editor = editor
            self._editor_box.children = [editor]
            self.value = editor.value
            editor.observe(self._on_editor_change, names="value")

    def _on_dropdown_change(self, change: Dict) -> None:
        if not self._is_updating:
            _on_main_thread(lambda: self._pick(change["new"], None))

    def _on_editor_change(self, change: Dict) -> None:
        self.value = change["new"]

    def _on_axis_picker_change(self, change: Dict) -> None:
        old_axis = self._axis
        self._axis = change["new"]
        current = self.value
        if self._on_axis_change is not None:
            current = self._on_axis_change(old_axis, self._axis, current)
        _on_main_thread(lambda: self._show(current))
