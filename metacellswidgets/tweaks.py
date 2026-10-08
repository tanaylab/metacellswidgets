"""
Tweaks: changes to a graph after a form builds it, such as its size or its title.

A tweak is a class. Its instance holds the values of its arguments, e.g. ``Size(width=800)``. A form applies its tweaks
in order, every time it builds its graph. Registering a tweak with :py:func:`tweak` lets the editor offer it.

A tweak which changes every graph the same way defines ``apply`` in its class:

.. code-block:: python

    @mw.tweak
    class FontSize(mw.Tweak):
        def __init__(self, size: int = 14) -> None:
            self.size = size

        def apply(self, graph: sg.Graph, source: mw.SourceWidgets) -> None:
            ...

A tweak which changes only some types of graphs, or changes each type differently, implements ``apply`` for each graph
type with :py:func:`~metacellswidgets.common.implements`. Each implementation applies to its graph type and to its
subtypes. The editor offers the tweak only for graphs of these types:

.. code-block:: python

    @mw.tweak
    class Highlight(mw.Tweak):
        def __init__(self, type_name: str) -> None:
            self.type_name = type_name


    @mw.implements(Highlight.apply, sg.PointsGraph)
    def _highlight_points(self: Highlight, graph: sg.PointsGraph, source: mw.SourceWidgets) -> None:
        ...


    @mw.implements(Highlight.apply, sg.HeatmapGraph)
    def _highlight_heatmap(self: Highlight, graph: sg.HeatmapGraph, source: mw.SourceWidgets) -> None:
        ...

A tweak without arguments, such as a template which makes graphs fit a lab's style, can be a single function.
:py:func:`tweak` turns it into a tweak class with the same name. It applies to the graph type of its first parameter:

.. code-block:: python

    @mw.tweak
    def paper_figure(graph: sg.Graph, source: mw.SourceWidgets) -> None:
        graph.configuration.figure.width = 600
        graph.configuration.figure.height = 400


    form = mw.DafWidgets(daf).gene_gene(x_gene="Foxa1", y_gene="Sox2", tweaks=[paper_figure()])

A tweak with arguments also needs an editor (see :py:meth:`Tweak.editor`).
"""

import functools
import inspect
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import Union
from typing import cast
from typing import get_type_hints
from typing import overload

from ipywidgets import Checkbox  # type: ignore
from ipywidgets import IntText  # type: ignore
from ipywidgets import Layout  # type: ignore
from ipywidgets import Text  # type: ignore
from ipywidgets import Widget  # type: ignore
from somegraphspy import Graph
from somegraphspy import visit_graph_parts

from .common import Arguments
from .common import _give_own_dispatchers
from .common import implements
from .editors import ArgumentsEditor

if TYPE_CHECKING:
    from .sources import SourceWidgets

__all__: List[str] = [
    "Legends",
    "Size",
    "Title",
    "Tweak",
    "registered_tweaks",
    "tweak",
]


class Tweak(Arguments):
    """
    The base class of all tweaks. Its instance holds the values of its arguments (see
    :py:class:`~metacellswidgets.common.Arguments`). A tweak class must derive directly from this class.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, Tweak, ("apply", "editor"))

    def apply(self, graph: Graph, source: "SourceWidgets") -> None:  # pylint: disable=unused-argument
        """
        Change the ``graph``, which a form built from the ``source``. A tweak defines this in its class, or implements
        it for each graph type it applies to; for any other graph type, this is an error.
        """
        raise TypeError(f"{type(self).__name__}.apply is not implemented for: {type(graph).__name__}")

    @classmethod
    def applies_to(cls, graph_type: Type[Graph]) -> bool:
        """
        Whether the tweak can change graphs of the ``graph_type``.
        """
        apply = cls.__dict__.get("apply")
        if not isinstance(apply, functools.singledispatchmethod):
            return cls is not Tweak
        return apply.dispatcher.dispatch(graph_type) is not Tweak.__dict__["apply"]

    @classmethod
    def editor(
        cls,
        source: "SourceWidgets",  # pylint: disable=unused-argument
        graph: Graph,  # pylint: disable=unused-argument
        current: Optional["Tweak"],  # pylint: disable=unused-argument
    ) -> Optional[Widget]:
        """
        A widget for editing the tweak's arguments for the ``source``, starting from the ``current`` tweak (if any). The
        ``graph`` is the form's graph without its tweaks, e.g. for starting from its title. The widget's ``value`` is
        the tweak, or ``None`` while the arguments are incomplete. A tweak without arguments has no editor. A tweak
        whose editor doesn't depend on the data defines this in its class. Otherwise, it implements this for each kind
        of data source with :py:func:`~metacellswidgets.common.implements`.
        """
        return None


# The registered tweaks, by their module and qualified name, in the order they were first registered. Registering a
# tweak with the same name again (e.g. running its notebook cell again) replaces it.
_REGISTERED_TWEAKS: Dict[str, Type[Tweak]] = {}

_Tweak = TypeVar("_Tweak", bound=Type[Tweak])


@overload
def tweak(target: _Tweak) -> _Tweak: ...


@overload
def tweak(target: Callable[[Any, "SourceWidgets"], None]) -> Type[Tweak]: ...


def tweak(target: Union[Type[Tweak], Callable[[Any, "SourceWidgets"], None]]) -> Type[Tweak]:
    """
    Register a tweak, so the editor offers it for the graphs it applies to. On a tweak class, return the class. On a
    function, return a new tweak class without arguments, with the function's name and documentation, whose ``apply``
    calls the function with the graph and the data source. It applies to the graph type the function's first parameter
    is annotated with.
    """
    if isinstance(target, type):
        tweak_class = target
    else:
        tweak_class = _function_tweak(target)
    _REGISTERED_TWEAKS[f"{tweak_class.__module__}.{tweak_class.__qualname__}"] = tweak_class
    return tweak_class


def _function_tweak(function: Callable[[Any, "SourceWidgets"], None]) -> Type[Tweak]:
    # A tweak class without arguments, which applies the function to the graph type its first parameter is annotated
    # with.
    graph_name = next(iter(inspect.signature(function).parameters))
    graph_type = get_type_hints(function).get(graph_name)
    if not isinstance(graph_type, type) or not issubclass(graph_type, Graph):
        raise TypeError(
            f"the first parameter: {graph_name} of the tweak function: {function.__qualname__} "
            "must be annotated with a graph type"
        )
    tweak_class = cast(
        Type[Tweak],
        type(
            function.__name__,
            (Tweak,),
            {"__doc__": function.__doc__, "__module__": function.__module__, "__qualname__": function.__qualname__},
        ),
    )

    @implements(tweak_class.apply, graph_type)
    def apply(_self: Tweak, graph: Graph, source: "SourceWidgets") -> None:
        function(graph, source)

    return tweak_class


def registered_tweaks(graph_type: Type[Graph]) -> List[Type[Tweak]]:
    """
    The registered tweaks which apply to the ``graph_type``, in the order they were registered.
    """
    return [tweak_class for tweak_class in _REGISTERED_TWEAKS.values() if tweak_class.applies_to(graph_type)]


# Plotly's own default size of a figure, which a new ``Size`` starts from when the graph gives no size of its own.
_DEFAULT_WIDTH = 700
_DEFAULT_HEIGHT = 450


@tweak
class Size(Tweak):
    """
    Set the ``width`` and the ``height`` of the figure, in pixels. A dimension which is ``None`` is left as the graph
    has it.
    """

    def __init__(self, width: Optional[int] = None, height: Optional[int] = None) -> None:
        self.width = width
        self.height = height

    def apply(self, graph: Graph, source: "SourceWidgets") -> None:  # pylint: disable=unused-argument
        figure = graph.configuration.figure
        if self.width is not None:
            figure.width = self.width
        if self.height is not None:
            figure.height = self.height

    @classmethod
    def editor(
        cls,
        source: "SourceWidgets",  # pylint: disable=unused-argument
        graph: Graph,
        current: Optional[Tweak],
    ) -> ArgumentsEditor:
        assert current is None or isinstance(current, Size)
        return _SizeEditor(graph, current)


class _Dimension:
    # The checkbox and the number of one dimension of a ``Size``. The dimension is given while the checkbox is checked,
    # and the number is disabled while it isn't.

    def __init__(self, description: str, value: Optional[int], start: int) -> None:
        self.checkbox = Checkbox(value=value is not None, indent=False, layout=Layout(width="auto"))
        self.number = IntText(
            value=start if value is None else value,
            description=description,
            disabled=value is None,
            style={"description_width": "initial"},
            layout=Layout(width="10em"),
        )
        self.checkbox.observe(self._on_checkbox_change, names="value")

    def _on_checkbox_change(self, change: Dict) -> None:
        self.number.disabled = not change["new"]

    @property
    def value(self) -> Optional[int]:  # pylint: disable=missing-function-docstring
        # The dimension, or ``None`` if it isn't given.
        return int(self.number.value) if self.checkbox.value else None


class _SizeEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    # The editor of a ``Size``: a checkbox and a number for each of the width and the height. A new ``Size`` gives both,
    # at the size of the graph (or Plotly's default size).

    def __init__(self, graph: Graph, current: Optional[Size]) -> None:
        super().__init__()
        figure = graph.configuration.figure
        start_width = _DEFAULT_WIDTH if figure.width is None else figure.width
        start_height = _DEFAULT_HEIGHT if figure.height is None else figure.height
        self._width = _Dimension("Width", start_width if current is None else current.width, start_width)
        self._height = _Dimension("Height", start_height if current is None else current.height, start_height)
        self.children = [self._width.checkbox, self._width.number, self._height.checkbox, self._height.number]
        self._update_value()
        for widget in self.children:
            widget.observe(self._on_change, names="value")

    def _on_change(self, _change: Dict) -> None:
        self._update_value()

    def _update_value(self) -> None:
        self.value = Size(width=self._width.value, height=self._height.value)


@tweak
class Title(Tweak):
    """
    Set the title of the figure to the ``text``, or remove the title if it is ``None``.
    """

    def __init__(self, text: Optional[str]) -> None:
        self.text = text

    def apply(self, graph: Graph, source: "SourceWidgets") -> None:  # pylint: disable=unused-argument
        graph.data.figure_title = self.text

    @classmethod
    def editor(
        cls,
        source: "SourceWidgets",  # pylint: disable=unused-argument
        graph: Graph,
        current: Optional[Tweak],
    ) -> ArgumentsEditor:
        assert current is None or isinstance(current, Title)
        return _TitleEditor(graph.data.figure_title if current is None else current.text)


class _TitleEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    # The editor of a ``Title``: a text box, which starts with the ``text``. An empty box removes the title.

    def __init__(self, text: Optional[str]) -> None:
        super().__init__()
        self._text = Text(value="" if text is None else text, placeholder="Title")
        self.children = [self._text]
        self.value = Title(text=text or None)
        self._text.observe(self._on_text_change, names="value")

    def _on_text_change(self, change: Dict) -> None:
        self.value = Title(text=change["new"] or None)


@tweak
class Legends(Tweak):
    """
    Show the legends of the graph as they are (if ``is_shown``), or hide them all.
    """

    def __init__(self, is_shown: bool) -> None:
        self.is_shown = is_shown

    def apply(self, graph: Graph, source: "SourceWidgets") -> None:  # pylint: disable=unused-argument
        if not self.is_shown:
            visit_graph_parts(_hide_legend, graph)

    @classmethod
    def editor(
        cls,
        source: "SourceWidgets",  # pylint: disable=unused-argument
        graph: Graph,  # pylint: disable=unused-argument
        current: Optional[Tweak],
    ) -> ArgumentsEditor:
        assert current is None or isinstance(current, Legends)
        return _LegendsEditor(True if current is None else current.is_shown)


def _hide_legend(part: Any) -> None:
    # Hide the legend of a part of a graph, if it has one.
    if hasattr(part, "show_legend"):
        part.show_legend = False


class _LegendsEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    # The editor of a ``Legends``: a "Show legends" checkbox.

    def __init__(self, is_shown: bool) -> None:
        super().__init__()
        self._checkbox = Checkbox(value=is_shown, description="Show legends", indent=False)
        self.children = [self._checkbox]
        self.value = Legends(is_shown=is_shown)
        self._checkbox.observe(self._on_checkbox_change, names="value")

    def _on_checkbox_change(self, change: Dict) -> None:
        self.value = Legends(is_shown=change["new"])
