"""
The points selected in a points graph.

A selection is a box or a lasso (a polygon), stored in the units of the graph's data, so it passes as is to the graph's
``selection`` (see ``somegraphspy.SelectionData``). Its values are rounded to 4 significant digits, and a lasso is
thinned to at most 40 vertices, so they read well in the code of a cell.

Plotly reports a selection in plotted coordinates, which differ from the data units on a scaled axis (e.g. a log scale).
The conversion is the inverse of how SomeGraphs plots an axis value: ``log_b((value + regularization) * scale)`` with a
log base, and otherwise ``value * scale + regularization``, where ``scale`` is 100 for a percent axis and 1 otherwise.

Which points are selected is computed in plotted coordinates, since the edges of a lasso are straight on the screen.
"""

import math
from typing import Any
from typing import List
from typing import Sequence
from typing import Tuple

from somegraphspy import LogBase
from somegraphspy import PointsGraph
from somegraphspy import ScaleConfiguration
from somegraphspy import SelectionData

__all__: List[str] = []

# A selected box: the minimal X, maximal X, minimal Y and maximal Y, in data units.
_Box = Tuple[float, float, float, float]

# A selected lasso: the X and Y of each of its vertices, in data units.
_Lasso = List[Tuple[float, float]]

# The most vertices a stored lasso has.
_MAX_LASSO_VERTICES = 40


def _plotted(scale: ScaleConfiguration, value: float) -> float:
    # The plotted coordinate of a data ``value`` along an axis of the ``scale``.
    factor = 100.0 if scale.percent else 1.0
    if scale.log_base == LogBase.Log10Base:
        return math.log10((value + scale.log_regularization) * factor)
    if scale.log_base == LogBase.Log2Base:
        return math.log2((value + scale.log_regularization) * factor)
    return value * factor + scale.log_regularization


def _data_value(scale: ScaleConfiguration, plotted: float) -> float:
    # The data value plotted at the ``plotted`` coordinate along an axis of the ``scale``.
    factor = 100.0 if scale.percent else 1.0
    if scale.log_base == LogBase.Log10Base:
        return 10.0**plotted / factor - scale.log_regularization
    if scale.log_base == LogBase.Log2Base:
        return 2.0**plotted / factor - scale.log_regularization
    return (plotted - scale.log_regularization) / factor


def _rounded(value: float) -> float:
    # The ``value`` rounded to 4 significant digits.
    return float(f"{value:.4g}")


def _box_of(graph: PointsGraph, x_range: Sequence[float], y_range: Sequence[float]) -> _Box:
    # The box selected in the ``graph`` by plotly's plotted ``x_range`` and ``y_range``, in data units.
    x_scale = graph.configuration.x_axis.scale
    y_scale = graph.configuration.y_axis.scale
    x_values = sorted(_rounded(_data_value(x_scale, plotted)) for plotted in x_range)
    y_values = sorted(_rounded(_data_value(y_scale, plotted)) for plotted in y_range)
    return (x_values[0], x_values[-1], y_values[0], y_values[-1])


def _lasso_of(graph: PointsGraph, xs: Sequence[float], ys: Sequence[float]) -> _Lasso:
    # The lasso selected in the ``graph`` by plotly's plotted vertices ``xs`` and ``ys``, in data units, thinned to at
    # most ``_MAX_LASSO_VERTICES`` evenly spaced vertices.
    x_scale = graph.configuration.x_axis.scale
    y_scale = graph.configuration.y_axis.scale
    count = len(xs)
    if count > _MAX_LASSO_VERTICES:
        indices = [round(index * (count - 1) / (_MAX_LASSO_VERTICES - 1)) for index in range(_MAX_LASSO_VERTICES)]
    else:
        indices = list(range(count))
    return [(_rounded(_data_value(x_scale, xs[index])), _rounded(_data_value(y_scale, ys[index]))) for index in indices]


def _selection_data(box: _Box | None, lasso: Sequence[Tuple[float, float]] | None) -> SelectionData:
    # The graph's ``selection`` for the ``box`` or the ``lasso`` (at most one of them).
    if box is not None:
        return SelectionData(box=box)
    if lasso is not None:
        return SelectionData(polygon=list(lasso))
    return SelectionData()


def _points_key(graph: Any) -> Tuple[Any, ...] | None:
    # What a selection in the ``graph`` depends on: the X and Y of each point in data units, the names of the points, and
    # which of them are shown. Only a change of these clears the selection (a change of the look keeps it). ``None`` for
    # a graph which isn't a points graph.
    if not isinstance(graph, PointsGraph):
        return None
    xs, ys, names, mask = _points_of(graph)
    return (tuple(xs), tuple(ys), tuple(names), None if mask is None else tuple(mask))


def _points_of(graph: PointsGraph) -> Tuple[List[float], List[float], List[str], List[bool] | None]:
    # The X and Y of each point of the ``graph`` in data units, the names of the points, and which of them are shown (or
    # ``None`` if all are).
    entities = graph.data.points.entities
    xs = [] if graph.data.x.vector is None else [float(value) for value in graph.data.x.vector]
    ys = [] if graph.data.y.vector is None else [float(value) for value in graph.data.y.vector]
    names = [] if entities.names is None else [str(name) for name in entities.names]
    mask = None if entities.mask is None else [bool(is_shown) for is_shown in entities.mask]
    return xs, ys, names, mask


def _without_selection(graph: Any) -> None:
    # Remove the selection the ``graph`` shows, if it is a points graph.
    if isinstance(graph, PointsGraph):
        graph.data.selection = SelectionData()


def _selected_names(graph: PointsGraph, box: _Box | None, lasso: Sequence[Tuple[float, float]] | None) -> List[str]:
    # The names of the shown points of the ``graph`` inside the ``box`` or the ``lasso``, in the order of the points.
    if box is None and lasso is None:
        return []
    x_scale = graph.configuration.x_axis.scale
    y_scale = graph.configuration.y_axis.scale
    data_xs, data_ys, names, mask = _points_of(graph)
    xs = [_plotted(x_scale, value) for value in data_xs]
    ys = [_plotted(y_scale, value) for value in data_ys]
    if box is not None:
        x_min, x_max = sorted((_plotted(x_scale, box[0]), _plotted(x_scale, box[1])))
        y_min, y_max = sorted((_plotted(y_scale, box[2]), _plotted(y_scale, box[3])))

        def is_inside(x: float, y: float) -> bool:
            return x_min <= x <= x_max and y_min <= y <= y_max

    else:
        assert lasso is not None
        polygon = [(_plotted(x_scale, x), _plotted(y_scale, y)) for x, y in lasso]

        def is_inside(x: float, y: float) -> bool:
            return _is_in_polygon(polygon, x, y)

    return [
        names[index] for index, (x, y) in enumerate(zip(xs, ys)) if (mask is None or mask[index]) and is_inside(x, y)
    ]


def _is_in_polygon(polygon: Sequence[Tuple[float, float]], x: float, y: float) -> bool:
    # Whether the point (``x``, ``y``) is inside the ``polygon``, by counting the edges a ray from it crosses.
    is_inside = False
    count = len(polygon)
    for index in range(count):
        x_from, y_from = polygon[index]
        x_to, y_to = polygon[(index + 1) % count]
        if (y_from > y) != (y_to > y) and x < x_from + (y - y_from) * (x_to - x_from) / (y_to - y_from):
            is_inside = not is_inside
    return is_inside
