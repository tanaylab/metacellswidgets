"""
Forms: the graphs a notebook cell shows, holding the arguments they were created with.

A form is created by a method of a kind of data source, e.g. ``mw.DafWidgets(daf).gene_gene(x_gene="Foxa1", ...)``.
Displaying it shows its graph. A kind's ``menu`` method (e.g. ``mw.DafWidgets(daf).menu()``) shows a menu of its graphs,
and an editor of the chosen one.

A form's editor is made of widgets, each tied to one of its arguments (see :py:meth:`GraphForm.bind`). Changing a
widget changes the argument and asks for the graph to be redrawn. Requests only mark the form; the graph is redrawn
once for all the requests pending, when the interactive display polls the form.
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
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Dict
from typing import FrozenSet
from typing import Iterator
from typing import List
from typing import Literal
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import Union
from typing import overload

import traitlets  # type: ignore
from IPython import get_ipython
from IPython.display import SVG
from IPython.display import Image
from IPython.display import display as display_in_cell
from ipywidgets import Button  # type: ignore
from ipywidgets import Dropdown  # type: ignore
from ipywidgets import HBox  # type: ignore
from ipywidgets import Output  # type: ignore
from ipywidgets import VBox  # type: ignore
from ipywidgets import Widget  # type: ignore
from plotly.graph_objects import Figure  # type: ignore
from plotly.graph_objects import FigureWidget  # type: ignore
from somegraphspy import Graph

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
    "GraphForm",
    "GraphMenu",
    "graph_menu",
]

# The formats of showing a graph: an interactive figure, or a static image.
_Format = Literal["plotly", "svg", "png"]


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
    _call_site: Optional[_CallSite] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, GraphForm, ("exists", "base_graph"))

    def __init__(self, source: SourceWidgets, tweaks: Optional[Sequence[Tweak]] = None) -> None:
        self.source = source
        self.tweaks = None if tweaks is None else list(tweaks)
        self._bound: Dict[str, Widget] = {}
        self._is_dirty = False
        self._held_redraws = 0
        self._kept_graph: Optional[Graph] = None
        self._kept_arguments: Optional[Dict[str, Any]] = None
        # The points the selection was made on (see ``_points_key``), or ``None`` if it wasn't made in a shown graph
        # (e.g. it was given in the code of the cell).
        self._selection_points: Optional[Any] = None

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
        graph = self._untweaked_graph()
        for tweak in self.tweaks or []:
            tweak.apply(graph, self.source)
        return graph

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

    def _untweaked_graph(self) -> Graph:
        # The base graph, with its slots filled, before the tweaks change it. This is what the editors of the tweaks start
        # from.
        graph = self.base_graph(self.source)
        self.fill_slots(graph)
        return graph

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

    def _poll_redraw(self, redraw: Callable[[Graph], None]) -> None:
        # If a redraw was requested, it isn't held, and the arguments are complete, give the graph to ``redraw``. This
        # runs on the main thread (which runs Julia), polled by the interactive display.
        if self._is_dirty and self._held_redraws == 0 and self.is_complete():
            self._is_dirty = False
            redraw(self._shown_graph())

    def display(
        self,
        *,
        interactive: bool = False,
        format: _Format = "plotly",  # pylint: disable=redefined-builtin
    ) -> "GraphForm":
        """
        Show the graph in the notebook cell. Returns the form, so it can be chained to its creation. The ``format`` is
        ``"plotly"`` for an interactive figure, or ``"svg"`` or ``"png"`` for a static image, which obeys the size of the
        graph.

        If ``interactive``, show an editor of the arguments and the graph instead, and block the cell until "Done" is
        clicked ("Done" is disabled while the arguments are incomplete). Then rewrite the code of the cell so that it
        creates the form with the edited arguments, and displays it with ``interactive=False``, and show the graph. This
        requires the form to be created in the same cell, at its top level, by a method of a kind of data source (e.g.
        ``source.gene_gene(...)``). The editor always shows an interactive figure. The ``format`` applies to the graph
        shown after "Done".
        """
        _check_format(format)
        form: GraphForm = self
        if interactive:
            form = self._edit(_cell_site(sys._getframe(1)))  # pylint: disable=protected-access
        _show_graph(form._shown_graph(), format)  # pylint: disable=protected-access
        return form

    def _tweaks_editor(self) -> ListEditor[Tweak]:
        # The editor of the tweaks: a list of them, under a "Tweaks" header, collapsed. The choices of each row are the
        # tweaks of the form's graph type, and a new tweak's editor starts from the graph last shown (if any).
        def make_row(current: Optional[Tweak]) -> TweakPicker:
            return TweakPicker(self.source, type(self).graph_type, self._kept_graph, current)

        tweaks = ListEditor(make_row, self.tweaks, title="Tweaks")
        self.bind(tweaks=tweaks)
        return tweaks

    def _edit(self, display_site: Optional[_CallSite]) -> "GraphForm":
        # Show the editor until "Done" is clicked, then rewrite the cell. Returns the form the editor ended with.
        call_site = self._call_site
        if call_site is None or display_site is None or display_site.cell_token != call_site.cell_token:
            raise RuntimeError(
                "an interactive form must be created and displayed in the same cell, at its top level, "
                "by a method of a kind of data source (e.g. source.gene_gene(...))"
            )
        _claim_cell_rewrite()
        form = _EditSession(self.source, self, _kind_tree(self.source)).run()
        shell = get_ipython()
        shell.set_next_input(
            _rewritten_cell(
                _current_cell_source(),
                form_position=call_site.position,
                form_keywords=form.arguments(),
                display_position=display_site.position,
                is_interactive=False,
                form_method=None if type(form) is type(self) else _method_name(self.source, type(form)),
                namespace=shell.user_ns,
            ),
            replace=True,
        )
        return form


# The interactive figure is drawn before its cell has a width, so it starts narrower than the cell. It measures the cell
# again only when its layout changes. So this long after the editor is shown, its layout is changed by toggling
# ``autosize``, and it measures the cell again. The delay is a guess at how long the browser takes to give the cell its
# width. A slower browser may still show a narrow figure until its first relayout (e.g. picking the lasso tool).
_FIGURE_RESIZE_DELAY_SECONDS = 0.5


@dataclass(frozen=True)
class Branch:
    """
    A node of the tree of the graphs a kind of data source offers: a ``name``, and its ``children`` in the order they
    are shown. Each child is a graph class (a leaf, named by its class name) or another branch. The root of the tree is
    a branch too; its name titles the tree.
    """

    name: str
    children: Sequence[Union[Type[GraphForm], "Branch"]]

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

    def visible(self, source: SourceWidgets) -> Optional["Branch"]:
        """
        The tree as shown for the ``source``: without the graphs which don't exist for it, nor the branches left empty.
        If nothing is left, ``None``.
        """
        children: List[Union[Type[GraphForm], Branch]] = []
        for child in self.children:
            if isinstance(child, Branch):
                visible_child = child.visible(source)
                if visible_child is not None:
                    children.append(visible_child)
            elif child.exists(source):
                children.append(child)
        return Branch(self.name, children) if children else None


# A node of the tree of the graphs: a graph class (a leaf), or a branch.
_Node = Union[Type[GraphForm], Branch]


class GraphMenu(HBox):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Choose a graph from the ``tree`` of the graphs of a kind of data source, as shown for the ``source`` (see
    :py:meth:`Branch.visible`). This is a row of dropdowns, one per level of the tree, each starting with nothing
    chosen. Choosing a sub-menu (a branch) adds a dropdown of its children. Choosing a graph ends the row. The row starts
    with the path to the ``current`` graph class, if it is in the tree.

    The ``value`` is the chosen graph class, or ``None`` while no graph is chosen.
    """

    value = traitlets.Any(None, allow_none=True)

    def __init__(self, source: SourceWidgets, tree: Branch, current: Optional[Type[GraphForm]] = None) -> None:
        super().__init__()
        visible = tree.visible(source)
        if visible is None:
            raise ValueError(f"no graph of: {tree.name} exists for this: {type(source).__name__}")
        self._root = visible
        self._path: List[_Node] = []
        self._dropdowns: List[Dropdown] = []
        self._set_path([] if current is None else _path_to(visible, current))

    def show(self, graph_class: Optional[Type[GraphForm]]) -> None:
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
            dropdown = Dropdown(options=options, value=path[level] if level < len(path) else None)
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
    def __get__(self, source: SourceWidgets, owner: type) -> Callable[..., GraphForm]: ...

    def __get__(self, source: Optional[SourceWidgets], owner: type) -> Union["_GraphMenu", Callable[..., GraphForm]]:
        if source is None:
            return self
        tree = self.tree

        def menu(*, format: _Format = "plotly") -> GraphForm:  # pylint: disable=redefined-builtin
            """
            Show a menu of the graphs, with an editor of the chosen graph's arguments and the graph, and block the cell
            until "Done" is clicked ("Done" is disabled until a graph is chosen and its arguments are complete). Then
            rewrite this call in the code of the cell so that it creates the chosen graph's form with the edited
            arguments, and displays it in the ``format`` with ``interactive=False``, and show the graph. Returns the
            form. This must be called at the top level of the cell.
            """
            return _show_menu(source, tree, _cell_site(sys._getframe(1)), format)  # pylint: disable=protected-access

        return menu


def graph_menu(tree: Branch) -> _GraphMenu:
    """
    Offer a menu of the graphs of the ``tree`` as a method of a kind of data source, e.g. ``menu = graph_menu(tree)``.
    Then ``source.menu()`` shows the menu, with an editor of the chosen graph (see :py:class:`GraphMenu`), and rewrites
    its call into the chosen graph's when "Done" is clicked.
    """
    return _GraphMenu(tree)


def _show_menu(
    source: SourceWidgets,
    tree: Branch,
    call_site: Optional[_CallSite],
    format: _Format,  # pylint: disable=redefined-builtin
) -> GraphForm:
    # Show the menu of the graphs of the ``tree`` until "Done" is clicked, then rewrite the menu call (at the
    # ``call_site``) into the chosen form's, and show its graph in the ``format``.
    _check_format(format)
    if call_site is None:
        raise RuntimeError("a menu must be shown at the top level of a cell (e.g. source.menu())")
    _claim_cell_rewrite()
    form = _EditSession(source, None, tree).run()
    shell = get_ipython()
    shell.set_next_input(
        _rewritten_menu_cell(
            _current_cell_source(),
            menu_position=call_site.position,
            method=_method_name(source, type(form)),
            form_keywords=form.arguments(),
            format=format,
            namespace=shell.user_ns,
        ),
        replace=True,
    )
    _show_graph(form._shown_graph(), format)  # pylint: disable=protected-access
    return form


def _kind_tree(source: SourceWidgets) -> Optional[Branch]:
    # The tree of the menu the kind of the ``source`` offers (see ``graph_menu``), if it offers one.
    for kind in type(source).__mro__:
        for value in kind.__dict__.values():
            if isinstance(value, _GraphMenu):
                return value.tree
    return None


def _method_name(source: SourceWidgets, graph_class: Type[GraphForm]) -> str:
    # The name of the method by which the kind of the ``source`` offers the ``graph_class``.
    return next(name for name, offered in type(source).offered_graphs().items() if offered is graph_class)


# The values of the arguments of the forms left during an editing session: per name, the last value and its type
# annotation.
_Pool = Dict[str, Tuple[Any, Any]]


def _pooled(pool: _Pool, form: GraphForm) -> None:
    # Put the arguments of the ``form`` into the ``pool``, replacing the earlier values of the same names. An argument
    # edited by an ``ArgumentsEditor`` is pooled with what the editor intends, including what isn't valid for this form
    # (e.g. a hidden tweak which applies to another graph type).
    hints = typing.get_type_hints(type(form).__init__)
    for name, value in form.arguments().items():
        widget = form._bound.get(name)  # pylint: disable=protected-access
        if isinstance(widget, ArgumentsEditor):
            value = widget.intended()
        pool[name] = (value, hints.get(name))


def _switched_form(
    graph_class: Type[GraphForm], source: SourceWidgets, pool: _Pool, selection_points: Optional[Any]
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


class _EditSession:  # pylint: disable=too-many-instance-attributes
    # The editor of a form (or, with no form, of a graph to choose), shown until "Done" is clicked. With a ``tree``, it
    # also has a menu of its graphs, and a "Graphs" button which shows or hides it. The menu is shown at first only if
    # there is no form. Choosing a graph in the menu replaces the edited form with one of the chosen graph (see
    # ``_switched_form``). The session pools the values of the arguments of the forms it leaves, so values set in one
    # graph reach any later graph which has them, and going back to a graph restores them. A "Revert" button goes back
    # to the graph and the arguments the session started with (or to no graph), and clears the pool.

    def __init__(self, source: SourceWidgets, form: Optional[GraphForm], tree: Optional[Branch] = None) -> None:
        self._source = source
        self._form = form
        self._original = None if form is None else (type(form), copy.deepcopy(form.arguments()))
        self._pool: _Pool = {}
        self._pooled_selection_points: Optional[Any] = None
        self._is_reverting = False
        self._done = Button(description="Done", button_style="primary")
        revert = Button(description="Revert")
        revert.on_click(self._on_revert)
        self._errors = Output()
        self._tweaks: Optional[ListEditor[Tweak]] = None
        # The editors are made before the graph is drawn, since binding them leaves out of the form's arguments what
        # isn't valid.
        self._body = VBox([] if form is None else self._form_widgets(form))
        graph = (
            form._shown_graph() if form is not None and form.is_complete() else None  # pylint: disable=protected-access
        )
        self._figure = FigureWidget(Figure() if graph is None else graph.figure)
        if graph is not None and self._tweaks is not None:
            self._tweaks.update_graph(graph)
        toolbar: List[Widget] = [self._done, revert]
        rows: List[Widget] = []
        self._menu: Optional[GraphMenu] = None
        visible = None if tree is None else tree.visible(source)
        if tree is not None and visible is not None and (form is None or _path_to(visible, type(form))):
            self._menu = GraphMenu(source, tree, None if form is None else type(form))
            self._menu.observe(self._on_menu_change, names="value")
            self._menu.layout.display = None if form is None else "none"
            graphs = Button(description="Graphs")
            graphs.on_click(self._on_graphs)
            toolbar.append(graphs)
            rows.append(self._menu)
        self._editor = VBox([HBox(toolbar), *rows, self._body, self._figure, self._errors])
        self._watch_selection()
        self._update_done()

    def run(self) -> GraphForm:
        """
        Show the editor and block until "Done" is clicked, while serving its jobs. Returns the edited form.
        """
        _route_to_subshell(self._editor, _owned_subshell_id())
        display_in_cell(self._editor)
        jobs = _MainThreadJobs()
        is_done = threading.Event()

        def on_done(_button: Button) -> None:
            if self._is_complete():
                is_done.set()
                jobs.wake()

        self._done.on_click(on_done)
        shown_at = time.monotonic()
        is_resized = False

        def on_poll() -> None:
            nonlocal is_resized
            if not is_resized and time.monotonic() - shown_at >= _FIGURE_RESIZE_DELAY_SECONDS:
                self._figure.layout.autosize = False
                self._figure.layout.autosize = True
                is_resized = True
            self._update_done()
            try:
                if self._form is not None:
                    self._form._poll_redraw(self._redraw)  # pylint: disable=protected-access
            except Exception:  # pylint: disable=broad-except
                with self._errors:
                    traceback.print_exc()

        with _routing_new_widgets(_owned_subshell_id()), _reporting_callback_errors(self._errors):
            jobs.serve(is_done, on_poll)
        self._editor.close()
        assert self._form is not None
        return self._form

    def _form_widgets(self, form: GraphForm) -> List[Widget]:
        # The widgets editing the arguments of the ``form``, and its tweaks.
        editor = form.editor()
        self._tweaks = form._tweaks_editor()  # pylint: disable=protected-access
        return [editor, self._tweaks]

    def _redraw(self, graph: Graph) -> None:
        # Show the redrawn ``graph``, and let the editors of the tweaks follow it.
        self._draw(graph.figure)
        if self._tweaks is not None:
            self._tweaks.update_graph(graph)

    def _is_complete(self) -> bool:
        # Whether there is a form to rewrite the cell with: one is chosen, and its arguments are complete.
        return self._form is not None and self._form.is_complete()

    def _update_done(self) -> None:
        self._done.disabled = not self._is_complete()

    def _on_graphs(self, _button: Button) -> None:
        assert self._menu is not None
        self._menu.layout.display = "none" if self._menu.layout.display is None else None

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

    def _switch(self, graph_class: Optional[Type[GraphForm]]) -> None:
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
        # Show the widgets of the edited form (if any), and an empty figure until its graph is drawn.
        self._tweaks = None
        self._body.children = [] if self._form is None else self._form_widgets(self._form)
        self._draw(Figure())
        if self._form is not None:
            self._form.request_redraw()
        self._update_done()

    def _draw(self, figure: Figure) -> None:
        # Show the ``figure``, and report its selections to the edited form.
        _replace_figure(self._figure, figure)
        self._watch_selection()

    def _watch_selection(self) -> None:
        # Report the selections of the points of the shown figure to the edited form.
        for trace in self._figure.data:
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


def _check_format(format: str) -> None:  # pylint: disable=redefined-builtin
    # Fail unless the ``format`` is one of the formats of showing a graph.
    if format not in ("plotly", "svg", "png"):
        raise ValueError(f"unknown format: {format} (expected plotly, svg or png)")


def _show_graph(graph: Graph, format: _Format) -> None:  # pylint: disable=redefined-builtin
    # Show the ``graph`` in the notebook cell, in the ``format``.
    if format == "svg":
        display_in_cell(SVG(graph.svg))
    elif format == "png":
        display_in_cell(Image(data=graph.png, format="png"))
    else:
        display_in_cell(graph.figure)


def _replace_figure(widget: FigureWidget, figure: Figure) -> None:
    # Show the ``figure`` in the interactive figure ``widget``, replacing its traces and its layout.
    with widget.batch_update():
        widget.data = []
        widget.add_traces(list(figure.data))
        widget.layout = figure.layout
