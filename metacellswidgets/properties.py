"""
Properties: the data a form can show in a slot of a graph, such as the colors or the sizes of its points.

A property is a class. Its instance holds the values of its arguments, e.g. ``GeneExpression("Foxa1")``. Each property
says what kind of values it produces (its ``eltype``), and that decides which slots it suits. Whether a data source has
a property, and how to fill a graph from it, is implemented separately for each kind of data source.
"""

import inspect
from enum import Enum
from typing import Any
from typing import Dict
from typing import FrozenSet
from typing import List
from typing import Mapping

from .rewrite import _literal_text

__all__: List[str] = [
    "Eltype",
    "Property",
    "Shape",
    "Slot",
]


class Eltype(Enum):
    """
    The kind of values a property produces.
    """

    #: Numbers, integer or not, such as UMI counts or gene fractions.
    NUMBER = "number"

    #: Names of categories, such as cell types.
    CATEGORICAL = "categorical"

    #: Boolean flags, such as a mask.
    BOOLEAN = "boolean"

    #: Numbers which say how to lay out entries (which go together, and in what order), such as a global flow order.
    ARRANGEMENT = "arrangement"


class Shape(Enum):
    """
    The shape of the values a property produces.
    """

    #: A value per entry of an axis.
    VECTOR = "vector"

    #: A value per pair of entries of two axes.
    MATRIX = "matrix"


class Slot(Enum):
    """
    A place in a graph that a property can fill.
    """

    #: The coordinates of points along an axis of the graph.
    COORDINATES = "coordinates"

    #: The sizes of points.
    SIZES = "sizes"

    #: The colors of points, or of an annotation strip.
    COLORS = "colors"

    #: Which entries are laid out together, and in what order.
    GROUPS = "groups"

    #: Which entries are shown.
    MASK = "mask"

    #: Lines added to the hover text of entries.
    HOVERS = "hovers"


# The kinds of values each slot can show.
_SLOT_ELTYPES: Mapping[Slot, FrozenSet[Eltype]] = {
    Slot.COORDINATES: frozenset([Eltype.NUMBER]),
    Slot.SIZES: frozenset([Eltype.NUMBER]),
    Slot.COLORS: frozenset([Eltype.NUMBER, Eltype.CATEGORICAL, Eltype.BOOLEAN]),
    Slot.GROUPS: frozenset([Eltype.CATEGORICAL, Eltype.ARRANGEMENT]),
    Slot.MASK: frozenset([Eltype.BOOLEAN]),
    Slot.HOVERS: frozenset([Eltype.NUMBER, Eltype.CATEGORICAL, Eltype.BOOLEAN, Eltype.ARRANGEMENT]),
}


class Property:
    """
    The base class of all properties.

    A property's ``__init__`` takes the values of its arguments, and stores each in an attribute of the same name. This
    is what lets a form write the property back into the code of its cell.
    """

    #: The kind of values the property produces.
    eltype: Eltype

    #: The shape of the values the property produces.
    shape: Shape

    @classmethod
    def suits(cls, slot: Slot) -> bool:
        """
        Whether the property can fill the ``slot``, which depends on its ``eltype``.
        """
        return cls.eltype in _SLOT_ELTYPES[slot]

    def arguments(self) -> Dict[str, Any]:
        """
        The values of the property's arguments, by the names of the parameters of its ``__init__``.
        """
        parameters = list(inspect.signature(type(self).__init__).parameters.values())[1:]
        return {
            parameter.name: getattr(self, parameter.name)
            for parameter in parameters
            if parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }

    def code(self, callee: str) -> str:
        """
        The code which creates the property, calling its class by the ``callee`` name (e.g., ``mw.GeneExpression``).
        """
        arguments = [f"{name}={_literal_text(name, value)}" for name, value in self.arguments().items()]
        return f"{callee}({', '.join(arguments)})"

    def __repr__(self) -> str:
        return self.code(type(self).__name__)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Property) and type(other) is type(self) and other.arguments() == self.arguments()

    def __hash__(self) -> int:
        return hash((type(self), tuple(self.arguments().items())))
