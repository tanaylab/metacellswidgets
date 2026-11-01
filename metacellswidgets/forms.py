"""
Forms: the graphs a notebook cell shows, holding the arguments they were created with.

A form is created by a method of a kind of data source, e.g. ``mw.DafWidgets(daf).gene_gene(x_gene="Foxa1", ...)``.
Its graph is shown by naming a format, e.g. ``.fig`` or ``.svg``. Its ``edit`` method shows an editor of its arguments.
A kind's ``menu`` method (e.g. ``mw.DafWidgets(daf).menu()``) shows a menu of its graphs, and an editor of the chosen
one.

A form's editor is made of widgets, each tied to one of its arguments (see :py:meth:`GraphForm.bind`). Changing a
widget changes the argument and asks for the graph to be redrawn. Requests only mark the form; the graph is redrawn
once for all the requests pending, when the editor polls the form.
"""

import copy
import functools
import inspect
import sys
import threading
import time
import traceback
import typing
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Dict
from typing import FrozenSet
from typing import Iterator
from typing import List
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import overload

import anywidget  # type: ignore
import traitlets  # type: ignore
from IPython import get_ipython
from IPython.display import display as display_in_cell
from ipywidgets import HTML  # type: ignore
from ipywidgets import Button  # type: ignore
from ipywidgets import Dropdown  # type: ignore
from ipywidgets import HBox  # type: ignore
from ipywidgets import Layout  # type: ignore
from ipywidgets import Output  # type: ignore
from ipywidgets import ToggleButton  # type: ignore
from ipywidgets import VBox  # type: ignore
from ipywidgets import Widget  # type: ignore
from plotly.graph_objects import Figure  # type: ignore
from plotly.graph_objects import FigureWidget  # type: ignore
from somegraphspy import Graph
from somegraphspy import HtmlText
from somegraphspy import PngImage
from somegraphspy import SvgImage

from .common import Arguments
from .common import _give_own_dispatchers
from .editors import ArgumentsEditor
from .editors import ListEditor
from .kernel import _MainThreadJobs
from .kernel import _on_main_thread
from .kernel import _owned_subshell_id
from .kernel import _reporting_callback_errors
from .kernel import _route_to_subshell
from .kernel import _routing_new_widgets
from .rewrite import _CallSite
from .rewrite import _cell_site
from .rewrite import _check_cell_rewrite
from .rewrite import _claim_cell_rewrite
from .rewrite import _current_cell_source
from .rewrite import _rewritten_cell
from .rewrite import _rewritten_menu_cell
from .selections import _points_key
from .selections import _without_selection
from .sources import SourceWidgets
from .tweaks import Tweak
from .tweaks import TweakPicker

__all__: List[str] = [
    "Branch",
    "Cancelled",
    "GraphForm",
    "GraphMenu",
    "graph_menu",
]


class GraphForm(Arguments):  # pylint: disable=too-many-instance-attributes
    """
    The base class of the forms of graphs. It holds the data ``source`` the graph is drawn from, and the values of the
    graph's arguments (see :py:class:`~metacellswidgets.common.Arguments`). A graph class must derive directly from this
    class.

    Every graph takes ``tweaks`` as its last argument: the tweaks which change it after it is built, in order (see
    :py:class:`~metacellswidgets.tweaks.Tweak`), or ``None`` for none.
    """

    #: The type of the graph the form builds (e.g. ``PointsGraph``), which decides which tweaks apply to it. Each graph
    #: sets this.
    graph_type: ClassVar[Type[Graph]]

    # The data source is written into the code of the cell as the receiver of the call (e.g. ``source.gene_gene(...)``),
    # not as an argument.
    _not_arguments: ClassVar[FrozenSet[str]] = frozenset(["source"])

    # The arguments which hold the selection of a graph which has one (e.g. ``selected_box``). A graph shown with other
    # points than those the selection was made on clears them.
    _selection_arguments: ClassVar[FrozenSet[str]] = frozenset()

    # Where in its cell the form was created, if it was created by a method of a kind of data source from the top level
    # of the running cell. Set by ``graph_constructor``.
    _call_site: _CallSite | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, GraphForm, ("exists", "base_graph"))

    def __init__(self, source: SourceWidgets, tweaks: Sequence[Tweak] | None = None) -> None:
        self.source = source
        self.tweaks = None if tweaks is None else list(tweaks)
        self._bound: Dict[str, Widget] = {}
        self._is_dirty = False
        self._held_redraws = 0
        self._kept_graph: Graph | None = None
        self._kept_arguments: Dict[str, Any] | None = None
        # The points the selection was made on (see ``_points_key``), or ``None`` if it wasn't made in a shown graph
        # (e.g. it was given in the code of the cell).
        self._selection_points: Any | None = None

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
        The graph, built from the data source and the arguments: the base graph, with its slots filled, then changed by
        each of the ``tweaks``, in order.
        """
        graph = self.base_graph(self.source)
        self.fill_slots(graph)
        for tweak in self.tweaks or []:
            tweak.apply(graph, self.source)
        return graph

    @property
    def json(self) -> str:
        """
        The graph (see :py:meth:`graph`) as the JSON text of its Plotly figure.
        """
        return self._shown_graph().json

    @property
    def fig(self) -> Figure:
        """
        The graph (see :py:meth:`graph`) as a Plotly figure. A notebook shows it as an interactive figure.
        """
        return self._shown_graph().fig

    @property
    def html(self) -> HtmlText:
        """
        The graph (see :py:meth:`graph`) as a standalone HTML page, which shows the interactive Plotly figure. It is the
        HTML text, which a notebook shows as the page.
        """
        return self._shown_graph().html

    @property
    def svg(self) -> SvgImage:
        """
        The graph (see :py:meth:`graph`) as a static SVG image, which obeys the graph's size. It is the SVG text, which a
        notebook shows as the image.
        """
        return self._shown_graph().svg

    @property
    def png(self) -> PngImage:
        """
        The graph (see :py:meth:`graph`) as a static PNG image, which obeys the graph's size. It is the PNG bytes, which
        a notebook shows as the image.
        """
        return self._shown_graph().png

    def _shown_graph(self) -> Graph:
        # The graph, to show. If its points differ from those the selection was made on, the selection is cleared (only
        # a change of the look keeps it). The graph is kept, with the arguments it was built from (not counting the
        # selection), so what is selected in it can be computed without building it again.
        graph = self.graph()
        points = _points_key(graph)
        has_selection = any(getattr(self, name) is not None for name in self._selection_arguments)
        if has_selection and self._selection_points is not None and points != self._selection_points:
            for name in self._selection_arguments:
                setattr(self, name, None)
            _without_selection(graph)
        self._selection_points = points
        self._kept_graph = graph
        self._kept_arguments = self._unselected_arguments()
        return graph

    def _selection_graph(self) -> Graph:
        # The graph to compute the selected points in: the kept graph, unless an argument other than the selection
        # changed since it was built (or there is none), and then a new one.
        if self._kept_graph is None or self._kept_arguments != self._unselected_arguments():
            return self._shown_graph()
        return self._kept_graph

    def _unselected_arguments(self) -> Dict[str, Any]:
        # The arguments, other than the selection.
        return {name: value for name, value in self.arguments().items() if name not in self._selection_arguments}

    def _on_selection(self, selector: Any) -> None:  # pylint: disable=unused-argument
        # Store the selection plotly reports by the ``selector`` (a box or a lasso) in the shown graph. A graph with a
        # selection implements this.
        return

    def _on_deselect(self) -> None:
        # Clear the selection, when it is cleared in the shown graph. A graph with a selection implements this.
        return

    def fill_slots(self, graph: Graph) -> None:
        """
        Fill the slots of the base ``graph`` (e.g. its colors) from the data source, according to the arguments. Each
        graph implements this, according to its slots.
        """
        raise NotImplementedError(f"{type(self).__name__}.fill_slots")

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
        Tie each of the arguments to the ``widgets`` with its name. The argument takes the ``value`` of its widget at
        once, which leaves out what isn't valid in the editor's context (e.g. a property the axis doesn't have). When the
        ``value`` of a widget changes, so does the argument, and the graph is redrawn.
        """
        for name, widget in widgets.items():
            self._bound[name] = widget
            setattr(self, name, widget.value)
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

    def _is_redraw_due(self) -> bool:
        # Whether a redraw was requested, it isn't held, and the arguments are complete.
        return self._is_dirty and self._held_redraws == 0 and self.is_complete()

    def _poll_redraw(self, redraw: Callable[[Graph], None]) -> None:
        # If a redraw is due, give the graph to ``redraw``. This runs on the main thread (which runs Julia), polled by
        # the editor.
        if self._is_redraw_due():
            self._is_dirty = False
            redraw(self._shown_graph())

    def edit(self) -> "GraphForm":
        """
        Show an editor of the arguments and the graph, and block the cell until "Done" is clicked ("Done" is disabled
        while the arguments are incomplete). Then rewrite the code of the cell so that it creates the form with the
        edited arguments, without this call (e.g. ``source.gene_gene(...).edit().svg`` becomes
        ``source.gene_gene(...).svg``). Returns the edited form, which is a form of another graph if the graph was
        switched in the editor. Clicking "Cancel" instead leaves the cell as it is, and returns the form with its
        arguments as they were.

        This shows nothing after the editor closes. Follow it by a format to show the graph (e.g. ``.edit().fig``). It
        requires the form to be created in the same cell, at its top level, by a method of a kind of data source (e.g.
        ``source.gene_gene(...)``).
        """
        edited = self._edit(_cell_site(sys._getframe(1)))  # pylint: disable=protected-access
        return self if edited is None else edited

    def _tweaks_editor(self) -> ListEditor[Tweak]:
        # The editor of the tweaks: a list of them, under a "Tweaks" header, collapsed. The choices of each row are the
        # tweaks of the form's graph type, and a new tweak's editor starts from the graph last shown (if any).
        def make_row(current: Tweak | None) -> TweakPicker:
            return TweakPicker(self.source, type(self).graph_type, self._kept_graph, current)

        tweaks = ListEditor(make_row, self.tweaks, title="Tweaks")
        self.bind(tweaks=tweaks)
        return tweaks

    def _edit(self, edit_site: _CallSite | None) -> "GraphForm | None":
        # Show the editor until "Done" is clicked, then rewrite the cell. Returns the form the editor ended with. If
        # "Cancel" is clicked instead, leave the cell as it is, restore the arguments (the editor changes them in place),
        # and return ``None``.
        call_site = self._call_site
        _check_cell_rewrite(call_site, edit_site)
        if call_site is None or edit_site is None or edit_site.cell_token != call_site.cell_token:
            raise RuntimeError(
                "an edited form must be created and edited in the same cell, at its top level, "
                "by a method of a kind of data source (e.g. source.gene_gene(...))"
            )
        _claim_cell_rewrite()
        original_arguments = copy.deepcopy(self.arguments())
        form = _EditSession(self.source, self, _kind_tree(self.source)).run()
        if form is None:
            for name, value in original_arguments.items():
                setattr(self, name, value)
            return None
        shell = get_ipython()
        shell.set_next_input(
            _rewritten_cell(
                _current_cell_source(),
                form_position=call_site.position,
                form_keywords=_written_arguments(form),
                edit_position=edit_site.position,
                form_method=None if type(form) is type(self) else _method_name(self.source, type(form)),
                namespace=shell.user_ns,
            ),
            replace=True,
        )
        return form


# How long the figure may be shown without a width from its ``_WidthWatcher`` before the editor reports that the watcher
# failed (e.g. its JavaScript didn't load).
_WIDTH_TIMEOUT_SECONDS = 10.0


class _WidthWatcher(anywidget.AnyWidget):  # pylint: disable=too-many-ancestors,abstract-method
    # An invisible element as wide as the figure's box, which reports its ``width`` (in pixels) whenever it changes, and
    # 0 while it is hidden. The interactive figure is drawn before its cell has a width, so it starts narrower than the
    # cell, and it measures the cell again only when its layout changes. So the editor changes the figure's layout each
    # time this reports a new width: when the cell gets its width, and whenever it is resized.

    _esm = Path(__file__).parent / "width_watcher.js"

    width = traitlets.Int(0).tag(sync=True)


@dataclass(frozen=True)
class Branch:
    """
    A node of the tree of the graphs a kind of data source offers: a ``name``, and its ``children`` in the order they
    are shown. Each child is a graph class (a leaf, named by its class name) or another branch. The root of the tree is
    a branch too; its name titles the tree.
    """

    name: str
    children: "Sequence[Type[GraphForm] | Branch]"

    def leaves(self) -> List[Type[GraphForm]]:
        """
        The graph classes in the tree, in the order they are shown.
        """
        leaves: List[Type[GraphForm]] = []
        for child in self.children:
            if isinstance(child, Branch):
                leaves += child.leaves()
            else:
                leaves.append(child)
        return leaves

    def visible(self, source: SourceWidgets) -> "Branch | None":
        """
        The tree as shown for the ``source``: without the graphs which don't exist for it, nor the branches left empty.
        If nothing is left, ``None``.
        """
        children: List[Type[GraphForm] | Branch] = []
        for child in self.children:
            if isinstance(child, Branch):
                visible_child = child.visible(source)
                if visible_child is not None:
                    children.append(visible_child)
            elif child.exists(source):
                children.append(child)
        return Branch(self.name, children) if children else None


# A node of the tree of the graphs: a graph class (a leaf), or a branch.
_Node = Type[GraphForm] | Branch


class GraphMenu(HBox):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Choose a graph from the ``tree`` of the graphs of a kind of data source, as shown for the ``source`` (see
    :py:meth:`Branch.visible`). This is a row of dropdowns, one per level of the tree, each starting with nothing
    chosen. Choosing a sub-menu (a branch) adds a dropdown of its children. Choosing a graph ends the row. The row starts
    with the path to the ``current`` graph class, if it is in the tree.

    The ``value`` is the chosen graph class, or ``None`` while no graph is chosen.
    """

    value = traitlets.Any(None, allow_none=True)

    def __init__(self, source: SourceWidgets, tree: Branch, current: Type[GraphForm] | None = None) -> None:
        super().__init__()
        visible = tree.visible(source)
        if visible is None:
            raise ValueError(f"no graph of: {tree.name} exists for this: {type(source).__name__}")
        self._root = visible
        self._path: List[_Node] = []
        self._dropdowns: List[Dropdown] = []
        self._set_path([] if current is None else _path_to(visible, current))

    def show(self, graph_class: Type[GraphForm] | None) -> None:
        """
        Show the path to the ``graph_class`` (if it is in the tree), or nothing chosen.
        """
        self._set_path([] if graph_class is None else _path_to(self._root, graph_class))

    def _set_path(self, path: Sequence[_Node]) -> None:
        # Show a dropdown of the root and of each branch on the ``path`` of chosen nodes, with the next node chosen.
        self._path = list(path)
        branches = [self._root, *[node for node in path if isinstance(node, Branch)]]
        for dropdown in self._dropdowns:
            dropdown.close()
        self._dropdowns = []
        for level, branch in enumerate(branches):
            options = [("Choose...", None)] + [(_node_name(child), child) for child in branch.children]
            # A dropdown given a ``value`` of ``None`` shows nothing, so the placeholder is picked by its index.
            index = 1 + branch.children.index(path[level]) if level < len(path) else 0
            dropdown = Dropdown(options=options, index=index)
            dropdown.observe(functools.partial(self._on_dropdown_change, level), names="value")
            self._dropdowns.append(dropdown)
        self.children = self._dropdowns
        last = path[-1] if path else None
        self.value = None if last is None or isinstance(last, Branch) else last

    def _on_dropdown_change(self, level: int, change: Dict) -> None:
        path = self._path[:level] + ([] if change["new"] is None else [change["new"]])
        _on_main_thread(lambda: self._set_path(path))


def _node_name(node: _Node) -> str:
    # How a node is named in a menu: a branch by its name, a graph by its class name.
    return node.name if isinstance(node, Branch) else node.__name__


def _path_to(branch: Branch, graph_class: Type[GraphForm]) -> List[_Node]:
    # The nodes from the children of the ``branch`` down to the ``graph_class``, or an empty list if it isn't there.
    for child in branch.children:
        if child is graph_class:
            return [child]
        if isinstance(child, Branch):
            path = _path_to(child, graph_class)
            if path:
                return [child, *path]
    return []


class _GraphMenu:
    # Shows a menu of the graphs of the ``tree`` for the data source it is read through.

    def __init__(self, tree: Branch) -> None:
        self.tree = tree

    @overload
    def __get__(self, source: None, owner: type) -> "_GraphMenu": ...

    @overload
    def __get__(self, source: SourceWidgets, owner: type) -> Callable[[], GraphForm]: ...

    def __get__(self, source: SourceWidgets | None, owner: type) -> "_GraphMenu | Callable[[], GraphForm]":
        if source is None:
            return self
        tree = self.tree

        def menu() -> GraphForm:
            """
            Show a menu of the graphs, with an editor of the chosen graph's arguments and the graph, and block the cell
            until "Done" is clicked ("Done" is disabled until a graph is chosen and its arguments are complete). Then
            rewrite this call in the code of the cell so that it creates the chosen graph's form with the edited
            arguments (e.g. ``source.menu().svg`` becomes ``source.gene_gene(...).svg``). Returns the form. Clicking
            "Cancel" instead leaves the cell as it is, and raises :py:class:`Cancelled`.

            This shows nothing after the menu closes. Follow it by a format to show the graph (e.g. ``.menu().fig``). It
            must be called at the top level of the cell.
            """
            return _show_menu(source, tree, _cell_site(sys._getframe(1)))  # pylint: disable=protected-access

        return menu


def graph_menu(tree: Branch) -> _GraphMenu:
    """
    Offer a menu of the graphs of the ``tree`` as a method of a kind of data source, e.g. ``menu = graph_menu(tree)``.
    Then ``source.menu()`` shows the menu, with an editor of the chosen graph (see :py:class:`GraphMenu`), and rewrites
    its call into the chosen graph's when "Done" is clicked.
    """
    return _GraphMenu(tree)


class Cancelled(Exception):
    """
    Raised by a kind's ``menu`` method when "Cancel" is clicked, since there is no form to return. A notebook shows only
    its message, without a traceback.
    """

    def _render_traceback_(self) -> List[str]:
        # IPython shows the lines this returns instead of the traceback.
        return [str(self)]


def _show_menu(source: SourceWidgets, tree: Branch, call_site: _CallSite | None) -> GraphForm:
    # Show the menu of the graphs of the ``tree`` until "Done" is clicked, then rewrite the menu call (at the
    # ``call_site``) into the chosen form's. If "Cancel" is clicked instead, leave the cell as it is, and raise
    # ``Cancelled``.
    _check_cell_rewrite(call_site)
    if call_site is None:
        raise RuntimeError("a menu must be shown at the top level of a cell (e.g. source.menu())")
    _claim_cell_rewrite()
    form = _EditSession(source, None, tree).run()
    if form is None:
        raise Cancelled("The menu was cancelled.")
    shell = get_ipython()
    shell.set_next_input(
        _rewritten_menu_cell(
            _current_cell_source(),
            menu_position=call_site.position,
            method=_method_name(source, type(form)),
            form_keywords=_written_arguments(form),
            namespace=shell.user_ns,
        ),
        replace=True,
    )
    return form


def _kind_tree(source: SourceWidgets) -> Branch | None:
    # The tree of the menu the kind of the ``source`` offers (see ``graph_menu``), if it offers one.
    for kind in type(source).__mro__:
        for value in kind.__dict__.values():
            if isinstance(value, _GraphMenu):
                return value.tree
    return None


def _written_arguments(form: GraphForm) -> Dict[str, Any]:
    # The arguments of the ``form`` to write into the code of the cell. A ``None`` is left out where it is the default
    # of its parameter (e.g. no ``colors``), but written where it means something else (e.g. a linear ``log_base``).
    parameters = inspect.signature(type(form).__init__).parameters
    return {
        name: value
        for name, value in form.arguments().items()
        if value is not None or parameters[name].default is not None
    }


def _method_name(source: SourceWidgets, graph_class: Type[GraphForm]) -> str:
    # The name of the method by which the kind of the ``source`` offers the ``graph_class``.
    return next(name for name, offered in type(source).offered_graphs().items() if offered is graph_class)


# The values of the arguments of the forms left during an editing session: per name, the last value and its type
# annotation.
_Pool = Dict[str, Tuple[Any, Any]]


def _intended_arguments(form: GraphForm) -> Dict[str, Any]:
    # The arguments of the ``form``, where an argument edited by an ``ArgumentsEditor`` is what the editor intends,
    # including what isn't valid for this form (e.g. a hidden tweak which applies to another graph type).
    arguments: Dict[str, Any] = {}
    for name, value in form.arguments().items():
        widget = form._bound.get(name)  # pylint: disable=protected-access
        arguments[name] = widget.intended() if isinstance(widget, ArgumentsEditor) else value
    return arguments


def _pooled(pool: _Pool, form: GraphForm) -> None:
    # Put the intended arguments of the ``form`` (see ``_intended_arguments``) into the ``pool``, replacing the earlier
    # values of the same names.
    hints = typing.get_type_hints(type(form).__init__)
    for name, value in _intended_arguments(form).items():
        pool[name] = (value, hints.get(name))


def _switched_form(
    graph_class: Type[GraphForm], source: SourceWidgets, pool: _Pool, selection_points: Any | None
) -> GraphForm:
    # A form of the ``graph_class`` for the ``source``, with the values of the ``pool`` whose name and type annotation fit
    # its arguments, and ``None`` for each of its other required arguments. A selection it takes from the ``pool`` was
    # made on the ``selection_points``, so it is kept only if the form's graph has the same points.
    #
    # The pooled values are intended values, which the checks of the constructor may reject (e.g. a hidden hover which
    # the colors show). So they are set after the form is constructed, and its editors leave out what isn't valid (see
    # ``GraphForm.bind``).
    hints = typing.get_type_hints(graph_class.__init__)
    required: Dict[str, Any] = {}
    pooled: Dict[str, Any] = {}
    for parameter in list(inspect.signature(graph_class).parameters.values())[1:]:
        if parameter.name in pool and pool[parameter.name][1] == hints.get(parameter.name):
            pooled[parameter.name] = pool[parameter.name][0]
        if parameter.default is inspect.Parameter.empty:
            required[parameter.name] = None
    form = graph_class(source, **required)
    for name, value in pooled.items():
        setattr(form, name, value)
    form._selection_points = selection_points  # pylint: disable=protected-access
    return form


def _disclosure_icon(is_shown: bool) -> str:
    # The icon of a toggle which shows or hides a panel: pointing down while it is shown, and right while it is hidden,
    # as the triangles of the headers of collapsible sections do.
    return "caret-down" if is_shown else "caret-right"


class _EditSession:  # pylint: disable=too-many-instance-attributes
    # The editor of a form (or, with no form, of a graph to choose), shown until "Done" is clicked, or "Cancel", which
    # discards the editing. With a ``tree``, it
    # also has a menu of its graphs, and a "Graphs" toggle which shows or hides it. The menu is shown at first only if
    # there is no form. The figure is hidden while there is no graph to show. Choosing a graph in the menu replaces the edited form with one of the chosen graph (see
    # ``_switched_form``). The session pools the values of the arguments of the forms it leaves, so values set in one
    # graph reach any later graph which has them, and going back to a graph restores them. A "Revert" button goes back
    # to the graph and the arguments the session started with (or to no graph), and clears the pool.

    def __init__(self, source: SourceWidgets, form: GraphForm | None, tree: Branch | None = None) -> None:
        self._source = source
        self._form = form
        self._original = None if form is None else (type(form), copy.deepcopy(form.arguments()))
        self._pool: _Pool = {}
        self._pooled_selection_points: Any | None = None
        self._is_reverting = False
        self._done = Button(description="Done")
        self._revert_button = Button(description="Revert")
        self._revert_button.on_click(self._on_revert)
        self._cancel = Button(description="Cancel")
        # Shown while work which may take a while is in progress (see ``_showing_spinner``), and while the figure waits for
        # its width. Hidden (keeping its place) otherwise. It shows at once if there is a form, whose editors the first
        # poll makes.
        self._spinner = HTML(
            '<i class="fa fa-spinner fa-spin"></i>', layout=Layout(visibility=None if form is not None else "hidden")
        )
        self._busy = 0
        self._is_waiting_for_width = False
        self._errors = Output()
        self._tweaks: ListEditor[Tweak] | None = None
        # The editors of the form, which may take a while to make, are made by the first poll (see ``_show_form``), so
        # the editor shows at once, with its spinner.
        self._body = VBox()
        self._is_form_due = form is not None
        # Made when there is first a graph to show, after the editor is shown (see ``_draw``), since the browser takes a
        # while to load the code of a figure widget, and shows nothing of the editor until it does.
        self._figure: FigureWidget | None = None
        self._width_watcher = _WidthWatcher()
        self._width_watcher.observe(self._on_width_change, names="width")
        # Whether a new width was reported, so the figure should measure its box again.
        self._is_resize_due = False
        # Since when the figure is shown without a width from its watcher (while it is).
        self._unmeasured_since: float | None = None
        self._has_width_failed = False
        # A figure widget's ``layout`` is the figure's, so it is hidden through a box around it. The box is a column, which
        # stretches the figure (and its width watcher) to its full width.
        self._figure_box = VBox([self._width_watcher], layout=Layout(display="none"))
        toolbar: List[Widget] = []
        rows: List[Widget] = []
        self._menu: GraphMenu | None = None
        self._graphs: ToggleButton | None = None
        visible = None if tree is None else tree.visible(source)
        if tree is not None and visible is not None and (form is None or _path_to(visible, type(form))):
            self._menu = GraphMenu(source, tree, None if form is None else type(form))
            self._menu.observe(self._on_menu_change, names="value")
            self._menu.layout.display = None if form is None else "none"
            self._graphs = ToggleButton(description="Graphs", value=form is None, icon=_disclosure_icon(form is None))
            self._graphs.observe(self._on_graphs_change, names="value")
            toolbar.append(self._graphs)
            rows.append(self._menu)
        toolbar += [self._revert_button, self._cancel, self._done, self._spinner]
        self._editor = VBox([HBox(toolbar), *rows, self._body, self._figure_box, self._errors])
        self._watch_selection()
        self._update_buttons()

    def run(self) -> GraphForm | None:
        """
        Show the editor and block until "Done" or "Cancel" is clicked, while serving its jobs. Returns the edited form,
        or ``None`` if "Cancel" was clicked.
        """
        _route_to_subshell(self._editor, _owned_subshell_id())
        display_in_cell(self._editor)
        jobs = _MainThreadJobs()
        is_done = threading.Event()
        is_cancelled = False

        def on_done(_button: Button) -> None:
            if self._is_complete():
                is_done.set()
                jobs.wake()

        def on_cancel(_button: Button) -> None:
            nonlocal is_cancelled
            is_cancelled = True
            is_done.set()
            jobs.wake()

        self._done.on_click(on_done)
        self._cancel.on_click(on_cancel)

        def on_poll() -> None:
            self._is_waiting_for_width = self._poll_width()
            self._update_spinner()
            if self._is_form_due:
                self._is_form_due = False
                self._show_form()
            self._update_buttons()
            form = self._form
            if form is not None and form._is_redraw_due():  # pylint: disable=protected-access
                with self._showing_spinner():
                    try:
                        form._poll_redraw(self._redraw)  # pylint: disable=protected-access
                    except Exception:  # pylint: disable=broad-except
                        with self._errors:
                            traceback.print_exc()

        with _routing_new_widgets(_owned_subshell_id()), _reporting_callback_errors(self._errors):
            jobs.serve(is_done, on_poll)
        self._editor.close()
        if is_cancelled:
            return None
        assert self._form is not None
        return self._form

    def _form_widgets(self, form: GraphForm) -> List[Widget]:
        # The widgets editing the arguments of the ``form``, and its tweaks.
        editor = form.editor()
        self._tweaks = form._tweaks_editor()  # pylint: disable=protected-access
        return [editor, self._tweaks]

    def _on_width_change(self, change: Dict) -> None:
        # The figure's box got a width (or a new one); the poll makes the figure measure it again.
        if change["new"] > 0:
            self._is_resize_due = True

    def _poll_width(self) -> bool:
        # Make the figure measure its box again if it got a new width. If the figure is shown too long without any width,
        # report that its width watcher failed. Returns whether the figure is shown and still waits for its width.
        if self._is_resize_due and self._figure is not None:
            self._is_resize_due = False
            self._figure.layout.autosize = False
            self._figure.layout.autosize = True
        is_waiting = (
            self._figure_box.layout.display != "none" and self._width_watcher.width == 0 and not self._has_width_failed
        )
        if not is_waiting:
            self._unmeasured_since = None
            return False
        now = time.monotonic()
        if self._unmeasured_since is None:
            self._unmeasured_since = now
        elif now - self._unmeasured_since > _WIDTH_TIMEOUT_SECONDS:
            self._has_width_failed = True
            with self._errors:
                print(
                    "The figure's width watcher reported no width, so its JavaScript didn't load in this frontend "
                    "(metacellswidgets needs an update for it). The figure may be narrower than the cell."
                )
            return False
        return True

    def _redraw(self, graph: Graph) -> None:
        # Show the redrawn ``graph``, and let the editors of the tweaks follow it.
        self._draw(graph.fig)
        if self._tweaks is not None:
            self._tweaks.update_graph(graph)

    def _is_complete(self) -> bool:
        # Whether there is a form to rewrite the cell with: one is chosen, and its arguments are complete.
        return self._form is not None and self._form.is_complete()

    def _is_original(self) -> bool:
        # Whether the session is as it started: the same graph with the same intended arguments (or no graph), and
        # nothing pooled.
        if self._pool:
            return False
        if self._original is None or self._form is None:
            return self._original is None and self._form is None
        graph_class, arguments = self._original
        return (
            type(self._form) is graph_class  # pylint: disable=unidiomatic-typecheck
            and _intended_arguments(self._form) == arguments
        )

    def _update_buttons(self) -> None:
        # "Done" needs a complete form, and "Revert" a change. Without a form, the menu is the only thing to use, so it
        # is shown, and "Graphs" can't hide it.
        self._done.disabled = not self._is_complete()
        self._revert_button.disabled = self._is_original()
        if self._graphs is not None:
            if self._form is None:
                self._graphs.value = True
            self._graphs.disabled = self._form is None

    def _on_graphs_change(self, change: Dict) -> None:
        assert self._graphs is not None and self._menu is not None
        self._graphs.icon = _disclosure_icon(change["new"])
        self._menu.layout.display = None if change["new"] else "none"

    def _on_menu_change(self, change: Dict) -> None:
        if not self._is_reverting:
            _on_main_thread(lambda: self._switch(change["new"]))

    def _on_revert(self, _button: Button) -> None:
        _on_main_thread(self._revert)

    def _revert(self) -> None:
        # Edit a form of the graph and the arguments the session started with (or no form), with an empty pool.
        try:
            self._pool = {}
            self._pooled_selection_points = None
            if self._original is None:
                self._form = None
            else:
                graph_class, arguments = self._original
                self._form = graph_class(self._source, **copy.deepcopy(arguments))
            if self._menu is not None:
                self._is_reverting = True
                try:
                    self._menu.show(None if self._form is None else type(self._form))
                finally:
                    self._is_reverting = False
            self._show_form()
        except Exception:  # pylint: disable=broad-except
            with self._errors:
                traceback.print_exc()

    def _switch(self, graph_class: Type[GraphForm] | None) -> None:
        # Edit a form of the ``graph_class`` (if any) instead of the current one, whose values are pooled.
        try:
            current = self._form
            if current is not None:
                _pooled(self._pool, current)
                if current._selection_arguments:  # pylint: disable=protected-access
                    self._pooled_selection_points = current._selection_points  # pylint: disable=protected-access
            if graph_class is None:
                self._form = None
            else:
                self._form = _switched_form(graph_class, self._source, self._pool, self._pooled_selection_points)
            self._show_form()
        except Exception:  # pylint: disable=broad-except
            with self._errors:
                traceback.print_exc()

    def _show_form(self) -> None:
        # Show the widgets of the edited form (if any), and no figure until its graph is drawn. Making the widgets may
        # take a while, so the spinner shows first, and the old figure is hidden.
        with self._showing_spinner():
            self._draw(None)
            self._tweaks = None
            self._body.children = [] if self._form is None else self._form_widgets(self._form)
            if self._form is not None:
                self._form.request_redraw()
            self._update_buttons()

    @contextmanager
    def _showing_spinner(self) -> Iterator[None]:
        # Show the spinner during the work in this context, which may take a while. The change reaches the browser at
        # once, so the spinner shows before the work starts.
        self._busy += 1
        self._update_spinner()
        try:
            yield
        finally:
            self._busy -= 1
            self._update_spinner()

    def _update_spinner(self) -> None:
        # Show the spinner while some work is in progress, or while the figure waits for its width.
        is_shown = self._busy > 0 or self._is_waiting_for_width
        self._spinner.layout.visibility = None if is_shown else "hidden"

    def _draw(self, figure: Figure | None) -> None:
        # Show the ``figure`` (or hide the figure, if there is none), and report its selections to the edited form. The
        # figure widget is made when there is first a figure to show.
        if figure is not None and self._figure is None:
            self._figure = FigureWidget()
            self._figure_box.children = [self._width_watcher, self._figure]
        if self._figure is not None:
            _replace_figure(self._figure, Figure() if figure is None else figure)
        self._figure_box.layout.display = "none" if figure is None else None
        self._watch_selection()

    def _watch_selection(self) -> None:
        # Report the selections of the points of the shown figure (if any) to the edited form.
        for trace in [] if self._figure is None else self._figure.data:
            trace.on_selection(self._on_selection)
            trace.on_deselect(self._on_deselect)

    def _on_selection(self, _trace: Any, _points: Any, selector: Any) -> None:
        # Widget callbacks run on another thread than the one which runs Julia, which reading the graph does.
        form = self._form
        if form is not None:
            _on_main_thread(lambda: form._on_selection(selector))  # pylint: disable=protected-access

    def _on_deselect(self, _trace: Any, _points: Any) -> None:
        form = self._form
        if form is not None:
            form._on_deselect()  # pylint: disable=protected-access


def _replace_figure(widget: FigureWidget, figure: Figure) -> None:
    # Show the ``figure`` in the interactive figure ``widget``, replacing its traces and its layout. Replacing the layout
    # drops its ``autosize``, without which the figure takes Plotly's fixed default width instead of the cell's, so it is
    # set again. It only applies to a width or a height the figure doesn't set (e.g. by a ``Size`` tweak).
    with widget.batch_update():
        widget.data = []
        widget.add_traces(list(figure.data))
        widget.layout = figure.layout
        widget.layout.autosize = True
