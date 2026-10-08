"""
Test the tweaks.
"""

from typing import Any
from typing import List
from typing import Optional

import pytest
import somegraphspy as sg
from ipywidgets import Widget  # type: ignore

import metacellswidgets as mw

from .test_daf_widgets import _full_daf


@mw.tweak
class _Width(mw.Tweak):
    """
    Set the width of every graph.
    """

    def __init__(self, width: int = 800) -> None:
        self.width = width

    def apply(self, graph: sg.Graph, source: mw.SourceWidgets) -> None:
        graph.configuration.figure.width = self.width

    @classmethod
    def editor(cls, source: mw.SourceWidgets, graph: sg.Graph, current: Optional[mw.Tweak]) -> Optional[Widget]:
        return Widget()


@mw.tweak
class _Heatmaps(mw.Tweak):
    """
    Change only heatmaps.
    """


@mw.implements(_Heatmaps.apply, sg.HeatmapGraph)
def _heatmaps(_self: _Heatmaps, _graph: sg.HeatmapGraph, _source: mw.SourceWidgets) -> None:
    pass


class _Unregistered(mw.Tweak):
    """
    Not registered, so never offered.
    """

    def apply(self, graph: sg.Graph, source: mw.SourceWidgets) -> None:
        pass


def _points_graph() -> sg.PointsGraph:
    # A points graph of a small data set.
    graph = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B").graph()
    assert isinstance(graph, sg.PointsGraph)
    return graph


def test_tweak_in_class() -> None:
    """
    A tweak which defines ``apply`` in its class applies to every graph.
    """
    graph = _points_graph()
    _Width(width=640).apply(graph, mw.DafWidgets(_full_daf()))
    assert graph.configuration.figure.width == 640
    assert _Width.applies_to(sg.PointsGraph)
    assert _Width.applies_to(sg.HeatmapGraph)


def test_tweak_per_graph_type() -> None:
    """
    A tweak which implements ``apply`` per graph type applies only to these types, and fails on any other.
    """
    assert _Heatmaps.applies_to(sg.HeatmapGraph)
    assert not _Heatmaps.applies_to(sg.PointsGraph)
    with pytest.raises(TypeError, match="_Heatmaps.apply is not implemented for: PointsGraph"):
        _Heatmaps().apply(_points_graph(), mw.DafWidgets(_full_daf()))


def test_tweak_base() -> None:
    """
    The base tweak applies to no graph, and has no editor.
    """
    assert not mw.Tweak.applies_to(sg.PointsGraph)
    assert mw.Tweak.editor(mw.DafWidgets(_full_daf()), _points_graph(), None) is None
    assert _Heatmaps.editor(mw.DafWidgets(_full_daf()), _points_graph(), None) is None
    assert isinstance(_Width.editor(mw.DafWidgets(_full_daf()), _points_graph(), None), Widget)


def test_tweak_derives_directly() -> None:
    """
    A tweak class must derive directly from ``Tweak``.
    """
    with pytest.raises(TypeError, match="must derive directly from: Tweak"):

        class _Wider(_Width):
            pass


def test_tweak_code() -> None:
    """
    A tweak is written into the code of a cell by its arguments, and compares by them.
    """
    assert _Width(width=640).code("mw.Width") == "mw.Width(width=640)"
    assert _Heatmaps().code("mw.Heatmaps") == "mw.Heatmaps()"
    assert _Width(width=640) == _Width(width=640)
    assert _Width(width=640) != _Width()


def test_function_tweak() -> None:
    """
    A function becomes a tweak without arguments, which applies to the graph type of its first parameter.
    """
    calls: List[Any] = []

    @mw.tweak
    def points_only(graph: sg.PointsGraph, source: mw.SourceWidgets) -> None:
        """
        Only points.
        """
        calls.append((graph, source))

    assert isinstance(points_only, type) and issubclass(points_only, mw.Tweak)
    assert points_only.__name__ == "points_only"
    assert points_only.__doc__ is not None and "Only points." in points_only.__doc__
    assert points_only().code("points_only") == "points_only()"  # pylint: disable=no-value-for-parameter
    assert points_only.applies_to(sg.PointsGraph)
    assert not points_only.applies_to(sg.HeatmapGraph)

    graph = _points_graph()
    source = mw.DafWidgets(_full_daf())
    points_only().apply(graph, source)  # pylint: disable=no-value-for-parameter
    assert calls == [(graph, source)]


def test_function_tweak_needs_a_graph_type() -> None:
    """
    A function must annotate its first parameter with a graph type.
    """

    def untyped(_graph, _source):  # type: ignore
        pass

    with pytest.raises(TypeError, match="must be annotated with a graph type"):
        mw.tweak(untyped)


def test_registered_tweaks() -> None:
    """
    The registered tweaks are offered for the graphs they apply to, in the order they were registered. Registering a
    tweak with the same name again replaces it.
    """
    assert _Width in mw.registered_tweaks(sg.PointsGraph)
    assert _Heatmaps not in mw.registered_tweaks(sg.PointsGraph)
    assert mw.registered_tweaks(sg.HeatmapGraph).index(_Width) < mw.registered_tweaks(sg.HeatmapGraph).index(_Heatmaps)
    assert _Unregistered not in mw.registered_tweaks(sg.PointsGraph)

    first = _registered_again()
    second = _registered_again()
    assert first is not second
    tweaks = mw.registered_tweaks(sg.PointsGraph)
    assert second in tweaks
    assert first not in tweaks


def _registered_again() -> type:
    # A new tweak class with the same name each time, as when a notebook cell runs again.
    @mw.tweak
    def again(_graph: sg.Graph, _source: mw.SourceWidgets) -> None:
        pass

    return again


def test_built_in_tweaks() -> None:
    """
    The built-in tweaks are offered first, for every graph.
    """
    assert mw.registered_tweaks(sg.PointsGraph)[:3] == [mw.Size, mw.Title, mw.Legends]


def test_size() -> None:
    """
    A size sets the dimensions it gives, and leaves the others as the graph has them.
    """
    graph = _points_graph()
    mw.Size(width=640).apply(graph, mw.DafWidgets(_full_daf()))
    assert graph.configuration.figure.width == 640
    assert graph.configuration.figure.height is None
    mw.Size(height=480).apply(graph, mw.DafWidgets(_full_daf()))
    assert graph.configuration.figure.width == 640
    assert graph.configuration.figure.height == 480
    assert mw.Size(width=640).code("mw.Size") == "mw.Size(width=640, height=None)"


def test_size_editor() -> None:
    """
    A new size gives both dimensions, at Plotly's default size. Unchecking a dimension disables its number.
    """
    source = mw.DafWidgets(_full_daf())
    editor = mw.Size.editor(source, _points_graph(), None)
    assert editor.value == mw.Size(width=700, height=450)
    width_checkbox, width_number, _height_checkbox, height_number = editor.children
    width_checkbox.value = False
    assert width_number.disabled
    assert editor.value == mw.Size(width=None, height=450)
    height_number.value = 300
    assert editor.value == mw.Size(width=None, height=300)
    assert mw.Size.editor(source, _points_graph(), mw.Size(height=200)).value == mw.Size(height=200)


def test_title() -> None:
    """
    A title sets the title of the figure, or removes it.
    """
    graph = _points_graph()
    source = mw.DafWidgets(_full_daf())
    mw.Title(text="Genes").apply(graph, source)
    assert graph.data.figure_title == "Genes"
    mw.Title(text=None).apply(graph, source)
    assert graph.data.figure_title is None


def test_title_editor() -> None:
    """
    A new title starts from the title of the graph. An empty box removes the title.
    """
    graph = _points_graph()
    graph.data.figure_title = "Default"
    editor = mw.Title.editor(mw.DafWidgets(_full_daf()), graph, None)
    assert editor.value == mw.Title(text="Default")
    editor.children[0].value = ""
    assert editor.value == mw.Title(text=None)


def test_legends() -> None:
    """
    Hiding the legends hides all of them, including the legend of the lines of a lines graph. Showing them leaves them
    as they are.
    """
    source = mw.DafWidgets(_full_daf())
    graph = _points_graph()
    graph.configuration.points.colors.show_legend = True
    mw.Legends(is_shown=True).apply(graph, source)
    assert graph.configuration.points.colors.show_legend
    mw.Legends(is_shown=False).apply(graph, source)
    assert not graph.configuration.points.colors.show_legend

    lines = sg.lines_graph()
    lines.configuration.show_legend = True
    mw.Legends(is_shown=False).apply(lines, source)
    assert not lines.configuration.show_legend


def test_legends_editor() -> None:
    """
    A new legends tweak shows the legends, until its checkbox is unchecked.
    """
    editor = mw.Legends.editor(mw.DafWidgets(_full_daf()), _points_graph(), None)
    assert editor.value == mw.Legends(is_shown=True)
    editor.children[0].value = False
    assert editor.value == mw.Legends(is_shown=False)


def test_tweak_picker() -> None:
    """
    A tweak picker offers the tweaks of the graph's type, the built-in ones first, after an empty choice. Picking one
    shows its editor, which starts from the graph.
    """
    source = mw.DafWidgets(_full_daf())
    graph = _points_graph()
    picker = mw.TweakPicker(source, graph)
    assert picker.value is None
    dropdown = picker.children[0]
    assert [label for label, _choice in dropdown.options][:4] == ["", "Size", "Title", "Legends"]
    dropdown.value = mw.Size
    assert picker.value == mw.Size(width=700, height=450)
    assert mw.TweakPicker(source, graph, mw.Title(text="Genes")).value == mw.Title(text="Genes")
