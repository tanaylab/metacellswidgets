"""
Forms: the graphs a notebook cell shows, holding the arguments they were created with.

A form is created by a method of a kind of data source, e.g. ``mw.DafWidgets(daf).gene_gene(x_gene="Foxa1", ...)``.
Displaying it shows its graph.

A form's editor is made of widgets, each tied to one of its arguments (see :py:meth:`GraphForm.bind`). Changing a
widget changes the argument and asks for the graph to be redrawn. Requests only mark the form; the graph is redrawn
once for all the requests pending, when the interactive display polls the form.
"""

import functools
import sys
import threading
import time
import traceback
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

from IPython import get_ipython
from IPython.display import display as display_in_cell
from ipywidgets import Button  # type: ignore
from ipywidgets import HBox  # type: ignore
from ipywidgets import Output  # type: ignore
from ipywidgets import VBox  # type: ignore
from ipywidgets import Widget  # type: ignore
from plotly.graph_objects import Figure  # type: ignore
from plotly.graph_objects import FigureWidget  # type: ignore
from somegraphspy import Graph

from .arguments import Arguments
from .kernel import _MainThreadJobs
from .kernel import _owned_subshell_id
from .kernel import _route_to_subshell
from .properties import _give_own_dispatchers
from .rewrite import _CallSite
from .rewrite import _cell_site
from .rewrite import _claim_cell_rewrite
from .rewrite import _current_cell_source
from .rewrite import _rewritten_cell
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

    def display(self, *, interactive: bool = False) -> "GraphForm":
        """
        Show the graph in the notebook cell. Returns the form, so it can be chained to its creation.

        If ``interactive``, show an editor of the arguments and the graph instead, and block the cell until "Done" is
        clicked. Then rewrite the code of the cell so that it creates the form with the edited arguments, and displays
        it with ``interactive=False``, and show the graph. This requires the form to be created in the same cell, at its
        top level, by a method of a kind of data source (e.g. ``source.gene_gene(...)``).
        """
        if interactive:
            self._edit(_cell_site(sys._getframe(1)))  # pylint: disable=protected-access
        display_in_cell(self.graph().figure)
        return self

    def _edit(self, display_site: Optional[_CallSite]) -> None:
        # Show the editor until "Done" is clicked, then rewrite the cell.
        call_site = self._call_site
        if call_site is None or display_site is None or display_site.cell_token != call_site.cell_token:
            raise RuntimeError(
                "an interactive form must be created and displayed in the same cell, at its top level, "
                "by a method of a kind of data source (e.g. source.gene_gene(...))"
            )
        _claim_cell_rewrite()

        figure = FigureWidget(self.graph().figure)
        done = Button(description="Done", button_style="primary")
        errors = Output()
        editor = VBox([HBox([done]), self.editor(), figure, errors])
        _route_to_subshell(editor, _owned_subshell_id())
        display_in_cell(editor)

        jobs = _MainThreadJobs()
        is_done = threading.Event()

        def on_done(_button: Button) -> None:
            is_done.set()
            jobs.wake()

        done.on_click(on_done)
        shown_at = time.monotonic()
        is_resized = False

        def on_poll() -> None:
            nonlocal is_resized
            if not is_resized and time.monotonic() - shown_at >= _FIGURE_RESIZE_DELAY_SECONDS:
                figure.layout.autosize = False
                figure.layout.autosize = True
                is_resized = True
            try:
                self._poll_redraw(lambda graph: _replace_figure(figure, graph.figure))
            except Exception:  # pylint: disable=broad-except
                with errors:
                    traceback.print_exc()

        jobs.serve(is_done, on_poll)

        shell = get_ipython()
        shell.set_next_input(
            _rewritten_cell(
                _current_cell_source(),
                form_position=call_site.position,
                form_keywords=self.arguments(),
                display_position=display_site.position,
                is_interactive=False,
                namespace=shell.user_ns,
            ),
            replace=True,
        )
        editor.close()


# The interactive figure is drawn before its cell has a width, so it starts narrower than the cell. It measures the cell
# again only when its layout changes. So this long after the editor is shown, its layout is changed by toggling
# ``autosize``, and it measures the cell again. The delay is a guess at how long the browser takes to give the cell its
# width. A slower browser may still show a narrow figure until its first relayout (e.g. picking the lasso tool).
_FIGURE_RESIZE_DELAY_SECONDS = 0.5


def _replace_figure(widget: FigureWidget, figure: Figure) -> None:
    # Show the ``figure`` in the interactive figure ``widget``, replacing its traces and its layout.
    with widget.batch_update():
        widget.data = []
        widget.add_traces(list(figure.data))
        widget.layout = figure.layout
