"""
Test the base of the kinds of data sources.
"""

import functools
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


class _Kind(Property):
    """
    A categorical property.
    """

    eltype = Eltype.CATEGORICAL
    shape = Shape.VECTOR

    @functools.singledispatchmethod
    @classmethod
    def exists(cls, source: SourceWidgets, axis: str) -> bool:  # pylint: disable=unused-argument
        return False

    @functools.singledispatchmethod
    def fill(self, source: SourceWidgets, sinks: Any, axis: str) -> None:  # pylint: disable=unused-argument
        raise TypeError(type(source).__name__)


class _Level(Property):
    """
    A numeric property.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR

    @functools.singledispatchmethod
    @classmethod
    def exists(cls, source: SourceWidgets, axis: str) -> bool:  # pylint: disable=unused-argument
        return False


@implements(_Kind.exists, _Toys)
def _toys_have_kind(_cls: type, source: _Toys, axis: str) -> bool:
    return f"kind of {axis}" in source.names


@implements(_Kind.fill, _Toys)
def _toys_fill_kind(_self: _Kind, source: _Toys, sinks: List[str], axis: str) -> None:
    sinks.append(f"kind of {axis} from {len(source.names)} names")


@implements(_Level.exists, _Toys)
def _toys_have_level(_cls: type, source: _Toys, axis: str) -> bool:
    return f"level of {axis}" in source.names


_Toys.register_properties(axis="cell", properties=[_Kind, _Level])
_MoreToys.register_properties(axis="gene", properties=[_Level])


def test_registered_properties() -> None:
    """
    A kind offers the properties registered for it and for its base classes.
    """
    assert _Toys.registered_properties("cell") == [_Kind, _Level]
    assert not _Toys.registered_properties("gene")
    assert _MoreToys.registered_properties("cell") == [_Kind, _Level]
    assert _MoreToys.registered_properties("gene") == [_Level]


def test_register_twice() -> None:
    """
    Registering a property twice for the same axis is an error, even through a base class.
    """
    with pytest.raises(ValueError, match="the property: _Kind is already registered for the axis: cell of: _MoreToys"):
        _MoreToys.register_properties(axis="cell", properties=[_Kind])


def test_properties() -> None:
    """
    A slot offers the registered properties which suit it and which the data source has.
    """
    toys = _Toys({"kind of cell", "level of cell"})
    assert toys.properties(axis="cell", slot=Slot.COLORS) == [_Kind, _Level]
    assert toys.properties(axis="cell", slot=Slot.SIZES) == [_Level]
    assert toys.properties(axis="cell", slot=Slot.GROUPS) == [_Kind]
    assert not toys.properties(axis="cell", slot=Slot.MASK)

    assert _Toys({"kind of cell"}).properties(axis="cell", slot=Slot.COLORS) == [_Kind]
    assert not _Toys(set()).properties(axis="cell", slot=Slot.COLORS)


def test_fill() -> None:
    """
    Filling dispatches on the kind of the data source.
    """
    sinks: List[str] = []
    _Kind().fill(_Toys({"kind of cell"}), sinks, "cell")
    assert sinks == ["kind of cell from 1 names"]


def test_unimplemented() -> None:
    """
    A property doesn't exist for a kind which doesn't implement it, and can't fill a graph from it.
    """

    class _Others(SourceWidgets):
        pass

    assert not _Kind.exists(_Others(), "cell")
    with pytest.raises(TypeError, match="_Others"):
        _Kind().fill(_Others(), [], "cell")
    assert _Kind.editor(_Others(), "cell", None) is None
