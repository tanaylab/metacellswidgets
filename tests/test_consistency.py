"""
Test that each kind of data source implements every property it registers.
"""

from typing import List
from typing import Tuple
from typing import Type

import pytest

import metacellswidgets as mw

_KINDS: List[Type[mw.SourceWidgets]] = [mw.DafWidgets, mw.AnnDataWidgets]


def _registrations() -> List[Tuple[Type[mw.SourceWidgets], str, Type[mw.Property]]]:
    """
    Each (kind, axis, property) registered by the kinds.
    """
    return [
        (kind, axis, property_class)
        for kind in _KINDS
        for axis in kind.registered_axes()
        for property_class in kind.registered_properties(axis)
    ]


def _is_implemented(property_class: Type[mw.Property], method: str, kind: Type[mw.SourceWidgets]) -> bool:
    """
    Whether the ``kind`` has an implementation of its own of the ``method`` of the ``property_class``.
    """
    dispatcher = property_class.__dict__[method].dispatcher
    return dispatcher.dispatch(kind) is not dispatcher.dispatch(object)


def _has_arguments(property_class: Type[mw.Property]) -> bool:
    """
    Whether the ``property_class`` takes any arguments.
    """
    return property_class.__init__ is not object.__init__


@pytest.mark.parametrize("kind, axis, property_class", _registrations())
def test_implemented(kind: Type[mw.SourceWidgets], axis: str, property_class: Type[mw.Property]) -> None:
    """
    A registered property has the implementations the kind needs.
    """
    assert axis
    assert _is_implemented(property_class, "exists", kind)
    assert _is_implemented(property_class, "fill", kind)
    if _has_arguments(property_class):
        assert _is_implemented(property_class, "editor", kind)


def test_some_have_arguments() -> None:
    """
    The check of the editors is not vacuous.
    """
    assert _has_arguments(mw.GeneExpression)
    assert not _has_arguments(mw.Type)
