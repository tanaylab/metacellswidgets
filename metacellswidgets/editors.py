"""
Widgets for editing the arguments of properties and tweaks, shared by all kinds of data sources.

A kind of data source supplies the data these widgets show (e.g., its genes); the widgets don't depend on the kind.
Each widget has an observable ``value``: the editors' is the property or the tweak (or ``None`` while its arguments are
incomplete), and the pickers' is the chosen string (or ``None`` while nothing is chosen).
"""

import functools
import inspect
from typing import Any
from typing import Callable
from typing import Dict
from typing import FrozenSet
from typing import Generic
from typing import List
from typing import Optional
from typing import Protocol
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import TypeVar
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
from ipywidgets import Widget  # type: ignore
from somegraphspy import LogBase

from .common import Arguments
from .kernel import _on_main_thread
from .properties import Property
from .properties import Slot
from .sources import SourceWidgets

__all__: List[str] = [
    "ArgumentsEditor",
    "AxisPicker",
    "ClassPicker",
    "ComboPicker",
    "GeneChoices",
    "GenePicker",
    "ListEditor",
    "NamePicker",
    "OnAxisChange",
    "Picker",
    "PickerEditor",
    "PickerRow",
    "PropertyPicker",
    "ShownProperties",
]

# The slots in which a property picker edits the look arguments of the picked property (e.g. its legend).
_LOOK_SLOTS = frozenset([Slot.COLORS, Slot.SIZES])


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
    class picked whose arguments are still missing is not blank). It isn't ``is_valid`` while it keeps an object which
    isn't valid in its context (e.g., a property the current axis doesn't have); its ``value`` is then ``None``.
    """

    value = traitlets.Any(None, allow_none=True)

    is_blank = traitlets.Bool(True)

    is_valid = traitlets.Bool(True)

    def shown(self) -> Any:
        """
        What the editor shows: its ``value``, or its default while it shows the default (and its ``value`` is
        ``None``).
        """
        return self.value

    def update_graph(self, graph: Any) -> None:  # pylint: disable=unused-argument
        """
        Called with the ``graph`` the form shows, each time it is drawn, so an editor whose starting values come from
        the graph (e.g. a tweak's size) can follow it. A value the user set is kept. By default, nothing changes.
        """


class Picker(HBox):  # pylint: disable=too-many-ancestors,abstract-method
    """
    The base class of the widgets picking one of some choices. Its ``value`` is the chosen string, or ``None`` while
    nothing is chosen.
    """

    value = traitlets.Any(None, allow_none=True)


class GenePicker(Picker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick a gene of a ``source``, by typing (part of) its label, starting with the ``current`` gene (if any). A toggle
    restricts the choices to the marker genes. It starts on if the source has any marker genes. The picked gene is always
    one of the choices, so the toggle never drops it.
    """

    def __init__(self, source: GeneChoices, current: Optional[str] = None) -> None:
        super().__init__()
        self._source = source
        self._name_per_label: Dict[str, str] = {}
        self._combobox = Combobox(placeholder="Gene", ensure_option=True)
        has_markers = bool(source.gene_choices(markers_only=True))
        self._markers_only = Checkbox(value=has_markers, description="Markers only", indent=False)
        self.children = [self._combobox, self._markers_only]
        self.value = current
        self._reset_choices()
        label = None if current is None else self._label_of(current)
        self._combobox.value = "" if label is None else label
        self.value = None if label is None else current
        self._combobox.observe(self._on_combobox_change, names="value")
        self._markers_only.observe(self._on_markers_only_change, names="value")

    def _reset_choices(self) -> None:
        # Fill the choices of the combobox, according to the markers only toggle, keeping the picked gene among them.
        choices = self._source.gene_choices(markers_only=self._markers_only.value)
        picked = self.value
        if picked is not None and all(name != picked for _label, name in choices):
            names = {name for _label, name in choices}
            choices = [choice for choice in self._source.gene_choices() if choice[1] in names or choice[1] == picked]
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


class ComboPicker(Picker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick one of some ``names`` by typing (part of) it, starting with the ``current`` one (if any, and if it is one of
    them). This suits many names (e.g., the blocks), where a dropdown would be too long. The ``placeholder`` says what
    is picked.
    """

    def __init__(self, names: Sequence[str], current: Optional[str] = None, *, placeholder: str) -> None:
        super().__init__()
        is_current = current is not None and current in names
        self._combobox = Combobox(
            options=list(names), value=current if is_current else "", placeholder=placeholder, ensure_option=True
        )
        self.children = [self._combobox]
        self.value = current if is_current else None
        self._combobox.observe(self._on_combobox_change, names="value")

    def _on_combobox_change(self, change: Dict) -> None:
        self.value = change["new"] or None


class PickerRow(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    """
    A row of a :py:class:`ListEditor` of names, picked by a ``picker``. Its ``value`` is the picked name.
    """

    def __init__(self, picker: Picker) -> None:
        super().__init__()
        self.children = [picker]
        self.value = picker.value
        self.is_blank = picker.value is None
        picker.observe(self._on_picker_change, names="value")

    def _on_picker_change(self, change: Dict) -> None:
        self.value = change["new"]
        self.is_blank = change["new"] is None


class PickerEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Edit an object with a single argument (e.g., a property or an entry filter), picked by a ``picker``. The ``build``
    function makes the object from the picked string.
    """

    def __init__(self, picker: Picker, build: Callable[[str], Arguments]) -> None:
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


# Whether the objects of the ``choice`` class take arguments other than look arguments (see ``Property``).
def _has_content_arguments(choice: Type[Arguments]) -> bool:
    if choice.__init__ is object.__init__:
        return False
    look_arguments: FrozenSet[str] = getattr(choice, "_look_arguments", frozenset())
    parameters = list(inspect.signature(choice.__init__).parameters)[1:]
    return any(name not in look_arguments for name in parameters)


class ClassPicker(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method,too-many-instance-attributes
    """
    The base class of the widgets picking one of some classes of properties or of tweaks, and editing the arguments of
    the picked one. The choices start with none. Picking a class whose objects have arguments shows its editor to the
    right of the choice. The ``value`` is the object, or ``None`` while nothing is picked or its arguments are
    incomplete.

    A picker may have a ``default`` object. While nothing was given or changed, the picker shows the ``default`` (picked,
    with its arguments), and its ``value`` stays ``None`` until the first change. A "Reset to default" button, shown
    while the ``value`` isn't ``None``, goes back to showing the ``default``.

    The picker keeps the object it was given or changed to. An object isn't valid if it isn't one of the choices (e.g.,
    after the axis changed), or if its arguments aren't valid. While the kept object isn't valid, the picker isn't
    ``is_valid``: it shows the ``default`` (or nothing), and its ``value`` is ``None``. Any change replaces the kept
    object.

    A picker may be for the entries of an ``axis``, which may be an :py:class:`AxisPicker` to follow. The ``default``
    may then be a function giving the default object for an axis. When the followed axis changes, the choices change
    with it. A picker showing its default shows the default of the new axis. A changed picker shows what its kept object
    becomes on the new axis, if that is valid. When the axis changes back, it shows the kept object again.

    A subclass makes its widget, then calls ``_show`` with its choices and the object it starts with. It implements
    ``_editor_of``, which makes the editor of a choice. A subclass which follows an axis also implements ``_choices``,
    which gives the choices for the current axis, and may implement ``_on_axis``, which says what the object becomes on
    the new axis.
    """

    def __init__(
        self,
        *,
        axis: Union[None, str, AxisPicker] = None,
        default: Union[None, Arguments, Callable[[str], Optional[Arguments]]] = None,
    ) -> None:
        super().__init__(layout=Layout(align_items="flex-start"))
        self._axis: Optional[str] = axis.value if isinstance(axis, AxisPicker) else axis
        self._given_default = default
        self._shown_choices: Sequence[Type[Arguments]] = ()
        self._kept: Optional[Arguments] = None
        self._kept_axis: Optional[str] = None
        self._is_default = False
        self._is_updating = False
        self._editor: Optional[ArgumentsEditor] = None
        self._dropdown = Dropdown()
        self._editor_box = HBox(layout=Layout(flex="1 1 auto"))
        self._reset = Button(description="Reset to default")
        self._reset.on_click(self._on_reset)
        self.children = [self._dropdown, self._editor_box, self._reset]
        self._dropdown.observe(self._on_dropdown_change, names="value")
        self._axis_picker = axis if isinstance(axis, AxisPicker) else None
        if self._axis_picker is not None:
            self._axis_picker.observe(self._on_axis_picker_change, names="value")

    def close(self) -> None:
        if self._axis_picker is not None:
            self._axis_picker.unobserve(self._on_axis_picker_change, names="value")
        super().close()

    def _editor_of(self, choice: Type[Arguments], current: Optional[Arguments]) -> Optional[ArgumentsEditor]:
        # The editor of the arguments of the ``choice``, starting with the ``current`` object (if any); or ``None`` if
        # the choice has no arguments. Each subclass implements this.
        raise NotImplementedError(f"{type(self).__name__}._editor_of")

    def _choices(self) -> Sequence[Type[Arguments]]:
        # The choices for the current axis. Each subclass which follows an axis implements this.
        raise NotImplementedError(f"{type(self).__name__}._choices")

    def _on_axis(  # pylint: disable=unused-argument
        self, old_axis: str, new_axis: str, current: Optional[Arguments]
    ) -> Optional[Arguments]:
        # What the ``current`` object becomes when the axis changes from the ``old_axis`` to the ``new_axis``. By
        # default, it stays as it is.
        return current

    def _default(self) -> Optional[Arguments]:
        # The default object for the current axis.
        if callable(self._given_default):
            assert self._axis is not None
            return self._given_default(self._axis)
        return self._given_default

    def shown(self) -> Optional[Arguments]:
        if self._is_default:
            return self._default()
        return self.value

    def _set_options(self, choices: Sequence[Type[Arguments]], choice: Optional[Type[Arguments]]) -> None:
        # Offer the ``choices`` (after the empty one), with the ``choice`` picked, without touching its editor.
        assert choice is None or choice in choices
        self._shown_choices = choices
        self._is_updating = True
        try:
            self._dropdown.options = [("", None)] + [(each_choice.__name__, each_choice) for each_choice in choices]
            self._dropdown.value = choice
        finally:
            self._is_updating = False

    def _show(self, choices: Sequence[Type[Arguments]], current: Optional[Arguments]) -> None:
        # Show the ``choices``, keeping the ``current`` object (if any).
        self._kept = current
        self._kept_axis = self._axis
        self._show_kept(choices)

    def _show_kept(self, choices: Sequence[Type[Arguments]]) -> None:
        # Show the ``choices``, with what the kept object becomes on the current axis picked, if it is valid.
        shown = self._kept
        if shown is not None and self._kept_axis != self._axis:
            assert self._kept_axis is not None and self._axis is not None
            shown = self._on_axis(self._kept_axis, self._axis, shown)
        self._display(choices, shown)
        self.is_valid = self._kept is None or self.value is not None

    def _keep_value(self) -> None:
        # Keep the ``value`` the picker was changed to.
        self._kept = self.value
        self._kept_axis = self._axis
        self.is_valid = True

    def _display(self, choices: Sequence[Type[Arguments]], current: Optional[Arguments]) -> None:
        # Show the ``choices``, with the ``current`` object picked if it is one of them and its arguments are valid.
        # Otherwise, show the default (if it is one of them), or nothing.
        choice = None if current is None else type(current)
        if choice not in choices:
            current = None
            choice = None
        default = self._default()
        self._is_default = current is None and default is not None and type(default) in choices
        if self._is_default:
            assert default is not None
            current = default
            choice = type(default)
        self._set_options(choices, choice)
        self._pick(choice, current)
        if not self._is_default and current is not None and self.value is None:
            self._display(choices, None)

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
        self._reset.layout.display = None if self.value is not None and self._given_default is not None else "none"

    def _on_dropdown_change(self, change: Dict) -> None:
        if not self._is_updating:
            self._is_default = False

            def pick() -> None:
                self._pick(change["new"], None)
                self._keep_value()

            _on_main_thread(pick)

    def _on_editor_change(self, change: Dict) -> None:
        self._is_default = False
        self._set_value(change["new"])
        self._keep_value()

    def _on_reset(self, _button: Button) -> None:
        _on_main_thread(lambda: self._show(self._shown_choices, None))

    def _on_axis_picker_change(self, change: Dict) -> None:
        self._axis = change["new"]
        _on_main_thread(lambda: self._show_kept(self._choices()))


class PropertyPicker(ClassPicker):  # pylint: disable=too-many-ancestors,abstract-method,too-many-instance-attributes
    """
    Pick a property of the ``source`` for a ``slot``, for the entries of the ``axis``, starting with the ``current``
    property (if any). The choices are the properties registered for the source's kind and the axis, which suit the
    slot, and which the source has; or none, leaving the slot empty. Picking a property with arguments shows its editor
    to the right of the choice.

    The ``axis`` may be an :py:class:`AxisPicker` to follow (see :py:class:`ClassPicker`), and the ``default`` may then
    be a function of the axis. An ``on_axis_change`` function may decide which property the slot holds when the axis
    changes.

    A picker of a hover may be given the ``shown`` properties of its side (see :py:class:`ShownProperties`). Its choices
    then leave out the properties without arguments which the side already shows, other than its own pick. They follow
    the ``shown`` properties as these change. A pick which another editor of the side comes to show isn't valid (see
    :py:class:`ClassPicker`), until that editor no longer shows it.

    In a colors or a sizes slot, the picker also edits the look arguments of the picked property: a "Show legend" toggle,
    and for a property shown on a log scale, a choice of log2 or log10. While a look argument is ``None``, its widget
    shows the default of the property's data source (see :py:meth:`Property.look_default`). Changing a widget sets the
    argument.
    """

    def __init__(
        self,
        source: SourceWidgets,
        slot: Slot,
        axis: Union[str, AxisPicker],
        current: Optional[Property] = None,
        *,
        default: Union[None, Property, Callable[[str], Optional[Property]]] = None,
        on_axis_change: Optional[OnAxisChange] = None,
        shown: Optional["ShownProperties"] = None,
    ) -> None:
        super().__init__(axis=axis, default=default)
        self._source = source
        self._slot = slot
        self._on_axis_change = on_axis_change
        self._shown_properties = shown
        self._look: Dict[str, Any] = {} if current is None else current.look_arguments()
        self._look_box = HBox()
        self.children = [*self.children, self._look_box]
        self._show(self._choices(), current)
        if shown is not None:
            shown.observe(self._on_shown_change, names="version")

    def _pick(self, choice: Optional[Type[Arguments]], current: Optional[Arguments]) -> None:
        super()._pick(choice, current)
        widgets: List[Widget] = []
        if choice is not None and self._slot in _LOOK_SLOTS:
            assert issubclass(choice, Property)
            look_arguments = choice._look_arguments  # pylint: disable=protected-access
            if "show_legend" in look_arguments:
                checkbox = Checkbox(
                    value=self._look_value(choice, "show_legend"), description="Show legend", indent=False
                )
                checkbox.observe(functools.partial(self._on_look_change, "show_legend"), names="value")
                widgets.append(checkbox)
            if "log_base" in look_arguments:
                dropdown = Dropdown(
                    options=[("log2", LogBase.Log2Base), ("log10", LogBase.Log10Base)],
                    value=self._look_value(choice, "log_base"),
                )
                dropdown.observe(functools.partial(self._on_look_change, "log_base"), names="value")
                widgets.append(dropdown)
        self._look_box.children = widgets

    def _look_value(self, choice: Type[Property], name: str) -> Any:
        # The value of the look argument with the ``name`` to show for the ``choice``: the picker's, or else the default.
        value = self._look.get(name)
        return choice.look_default(name) if value is None else value

    def _on_look_change(self, name: str, change: Dict) -> None:
        _on_main_thread(lambda: self._set_look(name, change["new"]))

    def _set_look(self, name: str, value: Any) -> None:
        # Set the look argument with the ``name`` to the ``value``, in a copy of the shown property, which becomes the
        # picker's value (so changing the look of a shown default makes it the value).
        self._look[name] = value
        shown = self.shown()
        if isinstance(shown, Property):
            self._is_default = False
            self._set_value(type(shown)(**shown.arguments()))
            self._keep_value()

    def _set_value(self, picked: Optional[Arguments]) -> None:
        # The picked property takes the picker's values of the look arguments its class has, since the editors of the
        # properties make them without any.
        if isinstance(picked, Property):
            for name, value in self._look.items():
                if name in picked._look_arguments:  # pylint: disable=protected-access
                    setattr(picked, name, value)
        super()._set_value(picked)

    def _choices(self) -> List[Type[Property]]:
        # The properties which may be picked for the current axis, other than the ones the side already shows.
        assert self._axis is not None
        choices = self._source.properties(axis=self._axis, slot=self._slot)
        if self._shown_properties is None:
            return choices
        # The picker's own value is one of the shown properties. Only this object is left out, so an equal property
        # which another editor shows still covers it.
        covered = [shown for shown in self._shown_properties.properties() if shown is not self.value]
        return [
            choice
            for choice in choices
            if _has_content_arguments(choice) or not any(shown.has_same_content(choice()) for shown in covered)
        ]

    def _on_shown_change(self, _change: Dict) -> None:
        choices = self._choices()
        if self._kept is not None and (type(self._kept) in choices) != self.is_valid:
            _on_main_thread(lambda: self._show_kept(self._choices()))
        elif choices != list(self._shown_choices):
            self._set_options(choices, self._dropdown.value)

    def close(self) -> None:
        if self._shown_properties is not None:
            self._shown_properties.unobserve(self._on_shown_change, names="version")
        super().close()

    def _editor_of(self, choice: Type[Arguments], current: Optional[Arguments]) -> Optional[ArgumentsEditor]:
        assert issubclass(choice, Property)
        assert current is None or isinstance(current, Property)
        assert self._axis is not None
        return choice.editor(self._source, self._axis, current)

    def _on_axis(self, old_axis: str, new_axis: str, current: Optional[Arguments]) -> Optional[Arguments]:
        assert current is None or isinstance(current, Property)
        if self._on_axis_change is None:
            return current
        return self._on_axis_change(old_axis, new_axis, current)


# The layout of the small buttons of each row of a list editor.
_ROW_BUTTON_LAYOUT = Layout(width="2.5em")


# The type of the objects of the list of a ``ListEditor``: the same for its rows, its ``current`` and its ``default``.
_Item = TypeVar("_Item", bound=Union[Arguments, str])


class ListEditor(  # pylint: disable=too-many-ancestors,abstract-method,too-many-instance-attributes
    ArgumentsEditor, Generic[_Item]
):
    """
    Edit a list of objects (e.g., properties, tweaks, or names), a row per object, in a collapsible section named
    ``title`` (collapsed at first). Each row is a picker made by ``make_row``, which gets the object the row starts with, or ``None`` for a
    blank row. The list always ends with a blank row; picking something in it makes it a row of the list, and appends a
    new blank row. Each row of the list has buttons to move it up or down, or to remove it.

    A row which isn't ``is_valid`` (see :py:class:`ArgumentsEditor`) is hidden, and its object is left out of the
    ``value``. It is shown again in its place once it is valid. Moving a row up or down swaps it with the adjacent shown
    row. The hidden rows after each of the two move with it. A removed row is closed.

    The list starts with a row per object of the ``current`` list. If there is no ``current`` list, it shows the
    ``default`` list (if any), and its ``value`` stays ``None`` until the first change. Otherwise, the ``value`` is the
    list of the values of the rows, leaving out the rows without one (so it may be empty). A "Reset to default" button,
    shown while the ``value`` isn't ``None`` (if there is a ``default``), sets it back to ``None`` and shows the
    ``default`` again.

    The list may be of the entries of an ``axis``, which may be an :py:class:`AxisPicker` to follow. The ``default`` may
    then be a function giving the default list for an axis. When the followed axis changes, a list showing its default
    shows the default of the new axis. A changed list keeps its rows, each following the axis by itself (if its
    ``make_row`` gives it the axis picker).
    """

    def __init__(
        self,
        make_row: Callable[[Optional[_Item]], ArgumentsEditor],
        current: Optional[Sequence[_Item]] = None,
        *,
        axis: Union[None, str, AxisPicker] = None,
        default: Union[None, Sequence[_Item], Callable[[str], Sequence[_Item]]] = None,
        title: str,
    ) -> None:
        super().__init__()
        self._make_row = make_row
        self._axis: Optional[str] = axis.value if isinstance(axis, AxisPicker) else axis
        self._given_default = default
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
        # The list observes the axis before its rows do, so it replaces the rows of a shown default before they follow
        # the new axis (which would count as a change).
        if isinstance(axis, AxisPicker):
            axis.observe(self._on_axis_picker_change, names="value")
        self._fill(self._default() if current is None else current)

    def _default(self) -> Optional[Sequence[_Item]]:
        # The default list for the current axis.
        if callable(self._given_default):
            assert self._axis is not None
            return self._given_default(self._axis)
        return self._given_default

    def shown(self) -> List[_Item]:
        return self._values()

    def _values(self) -> List[_Item]:
        # The objects of the shown rows which have one.
        return [row.value for row in self._rows if row.is_valid and row.value is not None]

    def update_graph(self, graph: Any) -> None:
        for row in self._rows:
            row.update_graph(graph)
        if self._blank_row is not None:
            self._blank_row.update_graph(graph)

    def _fill(self, items: Optional[Sequence[_Item]]) -> None:
        # Show a row per object of the ``items``, and then a blank row, closing the rows they replace.
        replaced_rows = list(self._rows)
        for row in replaced_rows:
            self._unobserve_row(row)
        if self._blank_row is not None:
            self._blank_row.unobserve(self._on_blank_row_change, names="is_blank")
            replaced_rows.append(self._blank_row)
        self._rows = []
        self._row_boxes = []
        for item in items or []:
            self._append(self._make_row(item))
        self._new_blank_row()
        self._update()
        for row in replaced_rows:
            row.close()

    def _new_blank_row(self) -> None:
        # Make the blank row at the end of the list, which becomes a row of the list once something is picked in it.
        self._blank_row = self._make_row(None)
        self._blank_row.observe(self._on_blank_row_change, names="is_blank")

    def _append(self, row: ArgumentsEditor) -> None:
        # Append the ``row``, with its buttons.
        move_up = Button(description="\N{UPWARDS ARROW}", layout=_ROW_BUTTON_LAYOUT)  # NOT F-STRING
        move_down = Button(description="\N{DOWNWARDS ARROW}", layout=_ROW_BUTTON_LAYOUT)  # NOT F-STRING
        remove = Button(description="\N{MULTIPLICATION X}", layout=_ROW_BUTTON_LAYOUT)  # NOT F-STRING
        move_up.on_click(lambda _button: self._move(row, -1))
        move_down.on_click(lambda _button: self._move(row, 1))
        remove.on_click(lambda _button: self._remove(row))
        row.observe(self._on_row_change, names="value")
        row.observe(self._on_row_is_valid_change, names="is_valid")
        self._rows.append(row)
        self._row_boxes.append(HBox([row, move_up, move_down, remove], layout=Layout(align_items="flex-start")))

    def _unobserve_row(self, row: ArgumentsEditor) -> None:
        row.unobserve(self._on_row_change, names="value")
        row.unobserve(self._on_row_is_valid_change, names="is_valid")

    def _move(self, row: ArgumentsEditor, offset: int) -> None:
        # Swap the ``row`` with the adjacent shown row before it (an ``offset`` of -1) or after it (1), unless there is
        # none. Each of the two moves with the hidden rows after it.
        shown_indices = [index for index, each_row in enumerate(self._rows) if each_row.is_valid]
        position = shown_indices.index(self._rows.index(row))
        first_position = min(position, position + offset)
        if 0 <= first_position and first_position + 1 < len(shown_indices):
            first_start, second_start = shown_indices[first_position], shown_indices[first_position + 1]
            second_end = len(self._rows)
            if first_position + 2 < len(shown_indices):
                second_end = shown_indices[first_position + 2]
            order = [
                *range(first_start),
                *range(second_start, second_end),
                *range(first_start, second_start),
                *range(second_end, len(self._rows)),
            ]
            self._rows = [self._rows[index] for index in order]
            self._row_boxes = [self._row_boxes[index] for index in order]
            self._is_default = False
            self._update()

    def _remove(self, row: ArgumentsEditor) -> None:
        index = self._rows.index(row)
        self._unobserve_row(row)
        del self._rows[index]
        del self._row_boxes[index]
        self._is_default = False
        self._update()
        row.close()

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

    def _on_row_is_valid_change(self, _change: Dict) -> None:
        self._update()

    def _on_reset(self, _button: Button) -> None:
        def reset() -> None:
            self._is_default = True
            self._fill(self._default())

        _on_main_thread(reset)

    def _on_axis_picker_change(self, change: Dict) -> None:
        self._axis = change["new"]
        if self._is_default:
            _on_main_thread(lambda: self._fill(self._default()))

    def _update(self) -> None:
        # Show the valid rows in their order, then the blank row, and set the value from them.
        self._rows_box.children = [
            *[row_box for row, row_box in zip(self._rows, self._row_boxes) if row.is_valid],
            self._blank_row,
        ]
        if self._is_default:
            self.value = None
        else:
            self.value = self._values()
        self._reset.layout.display = "none" if self.value is None or self._given_default is None else None


class ShownProperties(traitlets.HasTraits):
    """
    The properties a side of a graph already shows: those of its editors (e.g., its annotations, or the colors and the
    sizes of its points), and those of its ``hovers`` list. Each editor counts with what it shows, its default
    included. The pickers of the hovers are given this, so they don't offer what the side already shows.

    No shown hover duplicates the properties of the editors. When an editor comes to show a property which is also a
    hover, the hover is hidden (see :py:class:`PropertyPicker`), until the editor no longer shows it.

    It is made before the hovers list (whose pickers are given it), and then told to ``watch`` the editors, the list,
    and the axis they follow.
    """

    #: Bumped whenever the shown properties may have changed.
    version = traitlets.Int(0)

    def __init__(self) -> None:
        super().__init__()
        self._editors: List[ArgumentsEditor] = []
        self._hovers: Optional[ListEditor[Property]] = None

    def watch(
        self, editors: Sequence[ArgumentsEditor], hovers: ListEditor[Property], axis: Optional[AxisPicker] = None
    ) -> None:
        """
        Observe the ``editors``, the ``hovers`` list, and the ``axis`` (if any).
        """
        self._editors = list(editors)
        self._hovers = hovers
        for editor in [*self._editors, hovers]:
            editor.observe(self._on_change, names="value")
        if axis is not None:
            axis.observe(self._on_change, names="value")
        self._on_change({})

    def properties(self) -> List[Property]:
        """
        The properties shown by the editors and the hovers.
        """
        hovers: List[Property] = [] if self._hovers is None else self._hovers.shown()
        return [*self._editors_properties(), *hovers]

    def _editors_properties(self) -> List[Property]:
        # The properties shown by the editors (each shows a property, a list of them, or nothing).
        properties: List[Property] = []
        for editor in self._editors:
            shown = editor.shown()
            if isinstance(shown, Property):
                properties.append(shown)
            elif shown is not None:
                properties.extend(shown)
        return properties

    def _on_change(self, _change: Dict) -> None:
        self.version += 1
