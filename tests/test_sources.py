"""
Test the base of the kinds of data sources.
"""

import inspect
from typing import Any
from typing import List
from typing import Set

import pytest

from metacellswidgets.properties import Eltype
from metacellswidgets.properties import Property
from metacellswidgets.properties import Shape
from metacellswidgets.properties import Slot
from metacellswidgets.properties import implements
from metacellswidgets.sources import SourceWidgets
from metacellswidgets.sources import graph_constructor


class _Toys(SourceWidgets):
    """
    A kind of data source holding the names of the properties it has.
    """

    def __init__(self, names: Set[str]) -> None:
        self.names = names


class _MoreToys(_Toys):
    """
    A kind extending another.
    """


class _Category(Property):
    """
    The category of each entry.
    """

    eltype = Eltype.CATEGORICAL
    shape = Shape.VECTOR


class _Amount(Property):
    """
    The amount of each entry.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR


@implements(_Category.exists, _Toys)
def _toys_have_category(_cls: type, source: _Toys, axis: str) -> bool:
    return f"category of {axis}" in source.names


@implements(_Category.fill, _Toys)
def _toys_fill_category(_self: _Category, source: _Toys, sinks: List[str], axis: str) -> None:
    sinks.append(f"category of {axis} from {len(source.names)} names")


@implements(_Amount.exists, _Toys)
def _toys_have_amount(_cls: type, source: _Toys, axis: str) -> bool:
    return f"amount of {axis}" in source.names


_Toys.register_properties(axis="cell", properties=[_Category, _Amount])
_MoreToys.register_properties(axis="gene", properties=[_Amount])


def test_registered_properties() -> None:
    """
    A kind offers the properties registered for it and for its base classes.
    """
    assert _Toys.registered_properties("cell") == [_Category, _Amount]
    assert not _Toys.registered_properties("gene")
    assert _MoreToys.registered_properties("cell") == [_Category, _Amount]
    assert _MoreToys.registered_properties("gene") == [_Amount]


def test_register_twice() -> None:
    """
    Registering a property twice for the same axis is an error, even through a base class.
    """
    with pytest.raises(
        ValueError, match="the property: _Category is already registered for the axis: cell of: _MoreToys"
    ):
        _MoreToys.register_properties(axis="cell", properties=[_Category])


def test_properties() -> None:
    """
    A slot offers the registered properties which suit it and which the data source has.
    """
    toys = _Toys({"category of cell", "amount of cell"})
    assert toys.properties(axis="cell", slot=Slot.COLORS) == [_Category, _Amount]
    assert toys.properties(axis="cell", slot=Slot.SIZES) == [_Amount]
    assert toys.properties(axis="cell", slot=Slot.GROUPS) == [_Category]
    assert not toys.properties(axis="cell", slot=Slot.MASK)

    assert _Toys({"category of cell"}).properties(axis="cell", slot=Slot.COLORS) == [_Category]
    assert not _Toys(set()).properties(axis="cell", slot=Slot.COLORS)


def test_fill() -> None:
    """
    Filling dispatches on the kind of the data source.
    """
    sinks: Any = []
    _Category().fill(_Toys({"category of cell"}), sinks, "cell")
    assert sinks == ["category of cell from 1 names"]


def test_dispatchers_are_per_property() -> None:
    """
    Registering a kind's implementation of one property doesn't implement any other property for that kind.
    """
    assert _Category.__dict__["fill"] is not _Amount.__dict__["fill"]
    sinks: Any = []
    with pytest.raises(TypeError, match="_Amount.fill is not implemented for: _Toys"):
        _Amount().fill(_Toys({"amount of cell"}), sinks, "cell")


def test_unimplemented() -> None:
    """
    A property doesn't exist for a kind which doesn't implement it, and can't fill a graph from it.
    """

    class _Others(SourceWidgets):
        pass

    sinks: Any = []
    assert not _Category.exists(_Others(), "cell")
    with pytest.raises(TypeError, match="_Others"):
        _Category().fill(_Others(), sinks, "cell")
    assert _Category.editor(_Others(), "cell", None) is None


class _Chart:
    """
    A chart of some ``things``.
    """

    def __init__(self, source: SourceWidgets, *, things: str, size: int = 1) -> None:
        self.source = source
        self.things = things
        self.size = size


class _Charting(_Toys):
    """
    A kind offering a chart.
    """

    chart = graph_constructor(_Chart)


def test_graph_constructor() -> None:
    """
    A graph constructor constructs the graph with the data source, followed by the given arguments.
    """
    source = _Charting(set())
    chart = source.chart(things="cells", size=2)
    assert isinstance(chart, _Chart)
    assert chart.source is source
    assert chart.things == "cells"
    assert chart.size == 2


def test_graph_constructor_help() -> None:
    """
    The method has the name, the parameters (without the data source) and the documentation of the graph.
    """
    method = _Charting(set()).chart
    assert method.__name__ == "chart"
    assert method.__qualname__ == "_Charting.chart"
    assert method.__doc__ == _Chart.__doc__
    signature = inspect.signature(method)
    assert list(signature.parameters) == ["things", "size"]
    assert signature.return_annotation is _Chart
