"""
Properties: the data a form can show in a slot of a graph, such as the colors or the sizes of its points.

A property is a class. Its instance holds the values of its arguments, e.g. ``GeneExpression("Foxa1")``. Each property
says what kind of values it produces (its ``eltype``), and that decides which slots it suits. Whether a data source has
a property, and how to fill a graph from it, is implemented separately for each kind of data source.
"""

from enum import Enum
from typing import TYPE_CHECKING
from typing import Any
from typing import FrozenSet
from typing import List
from typing import Mapping
from typing import Optional

from ipywidgets import Widget  # type: ignore
from somegraphspy import VectorDataSinks

from .common import Arguments
from .common import _give_own_dispatchers

if TYPE_CHECKING:
    from .sources import SourceWidgets

__all__: List[str] = [
    "Block",
    "BooleanMask",
    "Eltype",
    "GeneExpression",
    "GlobalFlowOrder",
    "IsLateral",
    "IsMarker",
    "MeanCellsPerMetacell",
    "MeanTotalUMIsPerCell",
    "MeanTotalUMIsPerMetacell",
    "NCells",
    "NMetacells",
    "Property",
    "Shape",
    "Slot",
    "TotalUMIs",
    "Type",
    "UMAP",
    "boolean_property",
    "category_property",
    "size_property",
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

    #: Positions in an embedding, such as a UMAP, which mean something only relative to each other.
    COORDINATE = "coordinate"


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
    Slot.COORDINATES: frozenset([Eltype.NUMBER, Eltype.COORDINATE]),
    Slot.SIZES: frozenset([Eltype.NUMBER]),
    Slot.COLORS: frozenset([Eltype.NUMBER, Eltype.CATEGORICAL, Eltype.BOOLEAN]),
    Slot.GROUPS: frozenset([Eltype.CATEGORICAL, Eltype.ARRANGEMENT]),
    Slot.MASK: frozenset([Eltype.BOOLEAN]),
    # A coordinate puts no hover line, so it isn't offered as one.
    Slot.HOVERS: frozenset([Eltype.NUMBER, Eltype.CATEGORICAL, Eltype.BOOLEAN, Eltype.ARRANGEMENT]),
}


class Property(Arguments):
    """
    The base class of all properties. Its instance holds the values of its arguments (see
    :py:class:`~metacellswidgets.common.Arguments`). A property class must derive directly from this class.
    """

    #: The kind of values the property produces.
    eltype: Eltype

    #: The shape of the values the property produces.
    shape: Shape

    #: The name the data gives the property, for a property made by a factory (e.g., :py:func:`size_property`).
    property_name: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, Property, ("exists", "fill", "editor"))

    @classmethod
    def suits(cls, slot: Slot) -> bool:
        """
        Whether the property can fill the ``slot``, which depends on its ``eltype``.
        """
        return cls.eltype in _SLOT_ELTYPES[slot]

    @classmethod
    def exists(cls, source: "SourceWidgets", axis: str) -> bool:  # pylint: disable=unused-argument
        """
        Whether the ``source`` has the property for the entries of the ``axis``. Each kind of data source implements
        this for the properties it supports; for any other, the property does not exist.
        """
        return False

    def fill(self, source: "SourceWidgets", sinks: VectorDataSinks, axis: str) -> None:
        """
        Fill the ``sinks`` of a graph with the property's value for each entry of the ``axis`` of the ``source``. Each
        kind of data source implements this for the properties it supports; for any other, this is an error.
        """
        raise TypeError(f"{type(self).__name__}.fill is not implemented for: {type(source).__name__}")

    @classmethod
    def editor(
        cls, source: "SourceWidgets", axis: str, current: Optional["Property"]  # pylint: disable=unused-argument
    ) -> Optional[Widget]:
        """
        A widget for editing the property's arguments for the ``axis`` of the ``source``, starting from the
        ``current`` property (if any). Its ``value`` is the property, or ``None`` while the arguments are incomplete.
        A property without arguments has no editor.
        """
        return None


def size_property(
    class_name: str,
    *,
    property: str,  # pylint: disable=redefined-builtin
    doc: str,
) -> type[Property]:
    """
    Make the class of a property which is a count, such as UMIs, named ``class_name`` and documented by the ``doc``.
    The data gives it the name ``property``.
    """
    return _factory_property(class_name, eltype=Eltype.NUMBER, property_name=property, doc=doc)


def category_property(
    class_name: str,
    *,
    property: str,  # pylint: disable=redefined-builtin
    doc: str,
) -> type[Property]:
    """
    Make the class of a property which names a category, such as a type, named ``class_name`` and documented by the
    ``doc``. The data gives it the name ``property``.
    """
    return _factory_property(class_name, eltype=Eltype.CATEGORICAL, property_name=property, doc=doc)


def boolean_property(
    class_name: str,
    *,
    property: str,  # pylint: disable=redefined-builtin
    doc: str,
) -> type[Property]:
    """
    Make the class of a property which is a Boolean flag, named ``class_name`` and documented by the ``doc``. The data
    gives it the name ``property``.
    """
    return _factory_property(class_name, eltype=Eltype.BOOLEAN, property_name=property, doc=doc)


# Make the class of a property without arguments, as a factory does.
def _factory_property(class_name: str, *, eltype: Eltype, property_name: str, doc: str) -> type[Property]:
    namespace = {
        "__doc__": doc,
        "__module__": __name__,
        "__qualname__": class_name,
        "eltype": eltype,
        "shape": Shape.VECTOR,
        "property_name": property_name,
    }
    return type(class_name, (Property,), namespace)


Type = category_property(
    "Type", property="type", doc="The type of each entry, such as the cell type of each metacell, shown in its color."
)

Block = category_property("Block", property="block", doc="The block each entry belongs to.")


class GeneExpression(Property):
    """
    The expression level (linear fraction) of the ``gene`` in each entry, shown in log base 2.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR

    def __init__(self, gene: str) -> None:
        self.gene = gene


TotalUMIs = size_property("TotalUMIs", property="total_UMIs", doc="The total number of UMIs of each entry.")

NCells = size_property("NCells", property="n_cells", doc="The number of cells of each entry.")

NMetacells = size_property("NMetacells", property="n_metacells", doc="The number of metacells of each entry.")

IsLateral = boolean_property("IsLateral", property="is_lateral", doc="Whether each gene is lateral.")

IsMarker = boolean_property("IsMarker", property="is_marker", doc="Whether each gene is a marker gene.")


class MeanCellsPerMetacell(Property):
    """
    The mean number of cells per metacell of each entry.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR


class MeanTotalUMIsPerMetacell(Property):
    """
    The mean total number of UMIs per metacell of each entry.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR


class MeanTotalUMIsPerCell(Property):
    """
    The mean total number of UMIs per cell of each entry.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR


class BooleanMask(Property):
    """
    The Boolean mask property with the ``name`` of each entry.
    """

    eltype = Eltype.BOOLEAN
    shape = Shape.VECTOR

    def __init__(self, name: str) -> None:
        self.name = name


class GlobalFlowOrder(Property):
    """
    The position of the type of each entry in the global flow order of the types.
    """

    eltype = Eltype.ARRANGEMENT
    shape = Shape.VECTOR


class UMAP(Property):
    """
    The UMAP ``coordinate`` (``x`` or ``y``) of each entry, shown along an axis without ticks or a grid.
    """

    eltype = Eltype.COORDINATE
    shape = Shape.VECTOR

    def __init__(self, coordinate: str) -> None:
        self.coordinate = coordinate
