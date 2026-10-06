"""
Test the property base.
"""

import pytest

from metacellswidgets.properties import Eltype
from metacellswidgets.properties import Property
from metacellswidgets.properties import Shape
from metacellswidgets.properties import Slot


class _Kind(Property):
    """
    A property without arguments.
    """

    eltype = Eltype.CATEGORICAL
    shape = Shape.VECTOR


class _Level(Property):
    """
    A property with arguments.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR

    def __init__(self, gene: str, *, scale: float = 1.0) -> None:
        self.gene = gene
        self.scale = scale


class _Bad(Property):
    """
    A property whose value isn't a literal.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR

    def __init__(self, thing: object) -> None:
        self.thing = thing


def test_arguments() -> None:
    """
    The arguments are the attributes named after the parameters of ``__init__``.
    """
    assert not _Kind().arguments()
    assert _Level("Foxa1", scale=2.0).arguments() == {"gene": "Foxa1", "scale": 2.0}


def test_code() -> None:
    """
    The code calls the class by the given name, with each argument as a keyword.
    """
    assert _Kind().code("mw.Kind") == "mw.Kind()"
    assert _Level("Foxa1").code("mw.Level") == "mw.Level(gene='Foxa1', scale=1.0)"
    assert repr(_Level("Foxa1", scale=2.0)) == "_Level(gene='Foxa1', scale=2.0)"


def test_code_of_non_literal() -> None:
    """
    An argument which can't be written as a literal is an error.
    """
    with pytest.raises(TypeError, match="the value of thing can't be written as a Python literal"):
        _Bad(object()).code("mw.Bad")


def test_equality() -> None:
    """
    Properties are equal when they are of the same class with the same arguments.
    """
    assert _Level("Foxa1") == _Level("Foxa1")
    assert _Level("Foxa1") != _Level("Sox2")
    assert _Level("Foxa1") != _Kind()
    assert _Kind() == _Kind()
    assert len({_Level("Foxa1"), _Level("Foxa1"), _Kind()}) == 2


@pytest.mark.parametrize(
    "eltype, slots",
    [
        (Eltype.NUMBER, {Slot.COORDINATES, Slot.SIZES, Slot.COLORS, Slot.HOVERS}),
        (Eltype.CATEGORICAL, {Slot.COLORS, Slot.GROUPS, Slot.HOVERS}),
        (Eltype.BOOLEAN, {Slot.COLORS, Slot.MASK, Slot.HOVERS}),
        (Eltype.ARRANGEMENT, {Slot.GROUPS, Slot.HOVERS}),
    ],
)
def test_slots_of_eltype(eltype: Eltype, slots: set) -> None:
    """
    The slots a property suits follow from its ``eltype``.
    """

    class _Toy(Property):
        shape = Shape.VECTOR

    _Toy.eltype = eltype
    assert {slot for slot in Slot if _Toy.suits(slot)} == slots
