"""
Forms: the graphs a notebook cell shows, holding the arguments they were created with.

A form is created by a method of a kind of data source, e.g. ``mw.DafWidgets(daf).gene_gene(x_gene="Foxa1", ...)``.
Displaying it shows its graph.

A form's editor is made of widgets, each tied to one of its arguments (see :py:meth:`GraphForm.bind`). Changing a
widget changes the argument and asks for the graph to be redrawn. Requests only mark the form; the graph is redrawn
once for all the requests pending, when the interactive display polls the form.
"""

import functools
import typing
from contextlib import contextmanager
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Dict
from typing import FrozenSet
from typing import Iterator
from typing import List
from typing import Optional

from IPython.display import display as display_in_cell
from ipywidgets import Widget  # type: ignore
from somegraphspy import Graph

from .arguments import Arguments
from .properties import _give_own_dispatchers
from .rewrite import _CallSite
from .sources import SourceWidgets

__all__: List[str] = [
    "GraphForm",
]


class GraphForm(Arguments):
    """
    The base class of the forms of graphs. It holds the data ``source`` the graph is drawn from, and the values of the
    graph's arguments (see :py:class:`~metacellswidgets.arguments.Arguments`).
    """

    # The data source is written into the code of the cell as the receiver of the call (e.g. ``source.gene_gene(...)``),
    # not as an argument.
    _not_arguments: ClassVar[FrozenSet[str]] = frozenset(["source"])

    # Where in its cell the form was created, if it was created by a method of a kind of data source from the top level
    # of the running cell. Set by ``graph_constructor``.
    _call_site: Optional[_CallSite] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, GraphForm, ("exists", "base_graph"))

    def __init__(self, source: SourceWidgets) -> None:
        self.source = source
        self._bound: Dict[str, Widget] = {}
        self._is_dirty = False
        self._held_redraws = 0

    @classmethod
    def exists(cls, source: SourceWidgets) -> bool:  # pylint: disable=unused-argument
        """
        Whether the ``source`` has the data for this graph. Each kind of data source implements this for the graphs it
        offers; for any other, the graph does not exist.
        """
        return False

    def base_graph(self, source: SourceWidgets) -> Graph:
        """
        The graph built from the data of the ``source``, before its slots (e.g. its colors) are filled. Each kind of
        data source implements this for the graphs it offers; for any other, this is an error.
        """
        raise TypeError(f"{type(self).__name__}.base_graph is not implemented for: {type(source).__name__}")

    def graph(self) -> Graph:
        """
        The graph, built from the data source and the arguments: the base graph, with its slots filled. Each graph
        implements this, according to its slots.
        """
        raise NotImplementedError(f"{type(self).__name__}.graph")

    def is_complete(self) -> bool:
        """
        Whether the arguments are complete enough to draw the graph: no argument whose type doesn't allow ``None`` is
        ``None``. While editing, such an argument may be missing (e.g. a gene not yet picked). A graph with another
        rule overrides this.
        """
        hints = typing.get_type_hints(type(self).__init__)
        return all(
            getattr(self, name) is not None
            for name in self.arguments()
            if type(None) not in typing.get_args(hints.get(name))
        )

    def editor(self) -> Widget:
        """
        The widgets for editing the arguments, each tied to its argument by
        :py:meth:`~metacellswidgets.forms.GraphForm.bind`. Each graph implements this.
        """
        raise NotImplementedError(f"{type(self).__name__}.editor")

    def bind(self, **widgets: Widget) -> None:
        """
        Tie each of the arguments to the ``widgets`` with its name. When the ``value`` of a widget changes, so does the
        argument, and the graph is redrawn.
        """
        for name, widget in widgets.items():
            self._bound[name] = widget
            widget.observe(functools.partial(self._on_bound_change, name), names="value")

    def _on_bound_change(self, name: str, change: Dict) -> None:
        setattr(self, name, change["new"])
        self.request_redraw()

    def request_redraw(self) -> None:
        """
        Ask for the graph to be redrawn. Any number of requests made before the graph is redrawn give one redraw.
        """
        self._is_dirty = True

    @contextmanager
    def hold_redraw(self) -> Iterator[None]:
        """
        Hold the redrawing of the graph, e.g. while changing several arguments together, until the end of this context.
        """
        self._held_redraws += 1
        try:
            yield
        finally:
            self._held_redraws -= 1

    def _poll_redraw(self, redraw: Callable[[Graph], None]) -> None:
        # If a redraw was requested, it isn't held, and the arguments are complete, give the graph to ``redraw``. This
        # runs on the main thread (which runs Julia), polled by the interactive display.
        if self._is_dirty and self._held_redraws == 0 and self.is_complete():
            self._is_dirty = False
            redraw(self.graph())

    def display(self) -> "GraphForm":
        """
        Show the graph in the notebook cell. Returns the form, so it can be chained to its creation.
        """
        display_in_cell(self.graph().figure)
        return self
