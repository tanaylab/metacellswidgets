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

from ipywidgets import Widget  # type: ignore
from somegraphspy import Graph

from .common import Arguments
from .common import _give_own_dispatchers
from .common import implements

if TYPE_CHECKING:
    from .sources import SourceWidgets

__all__: List[str] = [
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
        cls, source: "SourceWidgets", current: Optional["Tweak"]  # pylint: disable=unused-argument
    ) -> Optional[Widget]:
        """
        A widget for editing the tweak's arguments for the ``source``, starting from the ``current`` tweak (if any). Its
        ``value`` is the tweak, or ``None`` while the arguments are incomplete. A tweak without arguments has no editor.
        A tweak whose editor doesn't depend on the data defines this in its class. Otherwise, it implements this for
        each kind of data source with :py:func:`~metacellswidgets.common.implements`.
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
