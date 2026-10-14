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
from ipywidgets import Accordion  # type: ignore
from ipywidgets import Button  # type: ignore
from ipywidgets import Checkbox  # type: ignore
from ipywidgets import Combobox  # type: ignore
from ipywidgets import Dropdown  # type: ignore
from ipywidgets import HBox  # type: ignore
from ipywidgets import Layout  # type: ignore
from ipywidgets import VBox  # type: ignore

from .common import Arguments
from .kernel import _on_main_thread
from .properties import Property
from .properties import Slot
from .sources import SourceWidgets

__all__: List[str] = [
    "ArgumentsEditor",
    "AxisPicker",
    "ClassPicker",
    "GeneChoices",
    "GenePicker",
    "ListEditor",
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
    tweak, or ``None`` while its arguments are incomplete. It is ``is_blank`` while nothing is picked at all (e.g., a
    class picked whose arguments are still missing is not blank).
    """

    value = traitlets.Any(None, allow_none=True)

    is_blank = traitlets.Bool(True)


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
        self.is_blank = picker.value is None
        picker.observe(self._on_picker_change, names="value")

    def _on_picker_change(self, change: Dict) -> None:
        self.value = None if change["new"] is None else self._build(change["new"])
        self.is_blank = change["new"] is None


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


class ClassPicker(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method,too-many-instance-attributes
    """
    The base class of the widgets picking one of some classes of properties or of tweaks, and editing the arguments of
    the picked one. The choices start with none. Picking a class whose objects have arguments shows its editor to the
    right of the choice. The ``value`` is the object, or ``None`` while nothing is picked or its arguments are
    incomplete.

    A picker may have a ``default`` object. While nothing was given or changed, the picker shows the ``default`` (picked,
    with its arguments), and its ``value`` stays ``None`` until the first change. A "Reset to default" button, shown
    while the ``value`` isn't ``None``, goes back to showing the ``default``. A given object which isn't one of the
    choices (e.g., after the axis changed), or whose arguments aren't valid, gives way to the ``default``.

    A subclass makes its widget, then calls ``_show`` with its choices and the object it starts with. It implements
    ``_editor_of``, which makes the editor of a choice.
    """

    def __init__(self, *, default: Optional[Arguments] = None) -> None:
        super().__init__(layout=Layout(align_items="flex-start"))
        self._default = default
        self._shown_choices: Sequence[Type[Arguments]] = ()
        self._is_default = False
        self._is_updating = False
        self._editor: Optional[ArgumentsEditor] = None
        self._dropdown = Dropdown()
        self._editor_box = HBox(layout=Layout(flex="1 1 auto"))
        self._reset = Button(description="Reset to default")
        self._reset.on_click(self._on_reset)
        self.children = [self._dropdown, self._editor_box, self._reset]
        self._dropdown.observe(self._on_dropdown_change, names="value")

    def _editor_of(self, choice: Type[Arguments], current: Optional[Arguments]) -> Optional[ArgumentsEditor]:
        # The editor of the arguments of the ``choice``, starting with the ``current`` object (if any); or ``None`` if
        # the choice has no arguments. Each subclass implements this.
        raise NotImplementedError(f"{type(self).__name__}._editor_of")

    def _show(self, choices: Sequence[Type[Arguments]], current: Optional[Arguments]) -> None:
        # Show the ``choices``, with the ``current`` object picked if it is one of them and its arguments are valid.
        # Otherwise, show the default (if it is one of them), or nothing.
        self._shown_choices = choices
        choice = None if current is None else type(current)
        if choice not in choices:
            current = None
            choice = None
        default = self._default
        self._is_default = current is None and default is not None and type(default) in choices
        if self._is_default:
            assert default is not None
            current = default
            choice = type(default)
        self._is_updating = True
        try:
            self._dropdown.options = [("", None)] + [(each_choice.__name__, each_choice) for each_choice in choices]
            self._dropdown.value = choice
        finally:
            self._is_updating = False
        self._pick(choice, current)
        if not self._is_default and current is not None and self.value is None:
            self._show(choices, None)

    def _pick(self, choice: Optional[Type[Arguments]], current: Optional[Arguments]) -> None:
        # Pick the ``choice``, starting its editor (if it has one) with the ``current`` object.
        if self._editor is not None:
            self._editor.unobserve(self._on_editor_change, names="value")
            self._editor = None
        self.is_blank = choice is None
        if choice is None:
            self._editor_box.children = []
            self._set_value(None)
            return
        editor = self._editor_of(choice, current)
        if editor is None:
            self._editor_box.children = []
            self._set_value(choice())
        else:
            self._editor = editor
            self._editor_box.children = [editor]
            self._set_value(editor.value)
            editor.observe(self._on_editor_change, names="value")

    def _set_value(self, picked: Optional[Arguments]) -> None:
        # The ``value`` is the ``picked`` object, unless the default is shown and wasn't changed.
        self.value = None if self._is_default else picked
        self._reset.layout.display = None if self.value is not None and self._default is not None else "none"

    def _on_dropdown_change(self, change: Dict) -> None:
        if not self._is_updating:
            self._is_default = False
            _on_main_thread(lambda: self._pick(change["new"], None))

    def _on_editor_change(self, change: Dict) -> None:
        self._is_default = False
        self._set_value(change["new"])

    def _on_reset(self, _button: Button) -> None:
        _on_main_thread(lambda: self._show(self._shown_choices, None))


class PropertyPicker(ClassPicker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick a property of the ``source`` for a ``slot``, for the entries of the ``axis``, starting with the ``current``
    property (if any). The choices are the properties registered for the source's kind and the axis, which suit the
    slot, and which the source has; or none, leaving the slot empty. Picking a property with arguments shows its editor
    to the right of the choice.

    The ``axis`` may be an :py:class:`AxisPicker` to follow. When its axis changes, the choices change with it. A
    property which is still one of them is kept, with its arguments, if they are valid for the new axis. Otherwise, the
    slot gets its ``default`` (see :py:class:`ClassPicker`), or is emptied. An ``on_axis_change`` function may decide
    this instead.
    """

    def __init__(
        self,
        source: SourceWidgets,
        slot: Slot,
        axis: Union[str, AxisPicker],
        current: Optional[Property] = None,
        *,
        default: Optional[Property] = None,
        on_axis_change: Optional[OnAxisChange] = None,
    ) -> None:
        super().__init__(default=default)
        self._source = source
        self._slot = slot
        self._axis = axis if isinstance(axis, str) else axis.value
        self._on_axis_change = on_axis_change
        self._show(self._choices(), current)
        if isinstance(axis, AxisPicker):
            axis.observe(self._on_axis_picker_change, names="value")

    def _choices(self) -> List[Type[Property]]:
        # The properties which may be picked for the current axis.
        return self._source.properties(axis=self._axis, slot=self._slot)

    def _editor_of(self, choice: Type[Arguments], current: Optional[Arguments]) -> Optional[ArgumentsEditor]:
        assert issubclass(choice, Property)
        assert current is None or isinstance(current, Property)
        return choice.editor(self._source, self._axis, current)

    def _on_axis_picker_change(self, change: Dict) -> None:
        old_axis = self._axis
        self._axis = change["new"]
        current = self.value
        if self._on_axis_change is not None:
            current = self._on_axis_change(old_axis, self._axis, current)
        _on_main_thread(lambda: self._show(self._choices(), current))


# The layout of the small buttons of each row of a list editor.
_ROW_BUTTON_LAYOUT = Layout(width="2.5em")


class ListEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method,too-many-instance-attributes
    """
    Edit a list of properties or tweaks, a row per object, in a collapsible section named ``title`` (collapsed at
    first). Each row is a picker made by ``make_row``, which gets the object the row starts with, or ``None`` for a
    blank row. The list always ends with a blank row; picking something in it makes it a row of the list, and appends a
    new blank row. Each row of the list has buttons to move it up or down, or to remove it.

    The list starts with a row per object of the ``current`` list. If there is no ``current`` list, it shows the
    ``default`` list (if any), and its ``value`` stays ``None`` until the first change. Otherwise, the ``value`` is the
    list of the values of the rows, leaving out the rows without one (so it may be empty). A "Reset to default" button,
    shown while the ``value`` isn't ``None``, sets it back to ``None`` and shows the ``default`` again.
    """

    def __init__(
        self,
        make_row: Callable[[Optional[Arguments]], ArgumentsEditor],
        current: Optional[Sequence[Arguments]] = None,
        *,
        default: Optional[Sequence[Arguments]] = None,
        title: str,
    ) -> None:
        super().__init__()
        self._make_row = make_row
        self._default = default
        self._is_default = current is None
        self._rows: List[ArgumentsEditor] = []
        self._row_boxes: List[HBox] = []
        self._blank_row: Optional[ArgumentsEditor] = None
        self._rows_box = VBox()
        self._reset = Button(description="Reset to default")
        self._reset.on_click(self._on_reset)
        self.children = [
            Accordion(children=[VBox([self._reset, self._rows_box])], titles=(title,), selected_index=None)
        ]
        self._fill(default if current is None else current)

    def _fill(self, items: Optional[Sequence[Arguments]]) -> None:
        # Show a row per object of the ``items``, and then a blank row.
        for row in self._rows:
            row.unobserve(self._on_row_change, names="value")
        if self._blank_row is not None:
            self._blank_row.unobserve(self._on_blank_row_change, names="is_blank")
        self._rows = []
        self._row_boxes = []
        for item in items or []:
            self._append(self._make_row(item))
        self._new_blank_row()
        self._update()

    def _new_blank_row(self) -> None:
        # Make the blank row at the end of the list, which becomes a row of the list once something is picked in it.
        self._blank_row = self._make_row(None)
        self._blank_row.observe(self._on_blank_row_change, names="is_blank")

    def _append(self, row: ArgumentsEditor) -> None:
        # Append the ``row``, with its buttons.
        move_up = Button(description="↑", layout=_ROW_BUTTON_LAYOUT)
        move_down = Button(description="↓", layout=_ROW_BUTTON_LAYOUT)
        remove = Button(description="✕", layout=_ROW_BUTTON_LAYOUT)
        move_up.on_click(lambda _button: self._move(row, -1))
        move_down.on_click(lambda _button: self._move(row, 1))
        remove.on_click(lambda _button: self._remove(row))
        row.observe(self._on_row_change, names="value")
        self._rows.append(row)
        self._row_boxes.append(HBox([row, move_up, move_down, remove], layout=Layout(align_items="flex-start")))

    def _move(self, row: ArgumentsEditor, offset: int) -> None:
        # Move the ``row`` by the ``offset``, unless that would move it past either end.
        index = self._rows.index(row)
        other_index = index + offset
        if 0 <= other_index < len(self._rows):
            rows, row_boxes = self._rows, self._row_boxes
            rows[index], rows[other_index] = rows[other_index], rows[index]
            row_boxes[index], row_boxes[other_index] = row_boxes[other_index], row_boxes[index]
            self._is_default = False
            self._update()

    def _remove(self, row: ArgumentsEditor) -> None:
        index = self._rows.index(row)
        row.unobserve(self._on_row_change, names="value")
        del self._rows[index]
        del self._row_boxes[index]
        self._is_default = False
        self._update()

    def _on_blank_row_change(self, change: Dict) -> None:
        if not change["new"]:
            _on_main_thread(self._adopt_blank_row)

    def _adopt_blank_row(self) -> None:
        # Make the blank row, in which something was picked, a row of the list, and add a new blank row.
        row = self._blank_row
        assert row is not None
        row.unobserve(self._on_blank_row_change, names="is_blank")
        self._append(row)
        self._new_blank_row()
        self._is_default = False
        self._update()

    def _on_row_change(self, _change: Dict) -> None:
        self._is_default = False
        self._update()

    def _on_reset(self, _button: Button) -> None:
        def reset() -> None:
            self._is_default = True
            self._fill(self._default)

        _on_main_thread(reset)

    def _update(self) -> None:
        # Show the rows in their order, then the blank row, and set the value from them.
        self._rows_box.children = [*self._row_boxes, self._blank_row]
        if self._is_default:
            self.value = None
        else:
            self.value = [row.value for row in self._rows if row.value is not None]
        self._reset.layout.display = "none" if self.value is None else None
