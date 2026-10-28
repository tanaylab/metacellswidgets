"""
Properties: the data a form can show in a slot of a graph, such as the colors or the sizes of its points.

A property is a class. Its instance holds the values of its arguments, e.g. ``GeneExpression("Foxa1")``. Each property
says what kind of values it produces (its ``eltype``), and that decides which slots it suits. Whether a data source has
a property, and how to fill a graph from it, is implemented separately for each kind of data source.

Some arguments change only how a property is shown, not its data: ``show_legend``, and for a property shown on a log
scale, ``log_base``. They mirror the keywords of the property's data source in ``metacellsgraphspy``, and ``DEFAULT``
leaves the data source's default. They are the property's look arguments.
"""

from enum import Enum
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Dict
from typing import FrozenSet
from typing import List
from typing import Mapping
from typing import Optional
from typing import Tuple
from typing import Union

import metacellsgraphspy as mg
from dafpy.julia_import import DEFAULT
from dafpy.julia_import import DefaultValue
from ipywidgets import Widget  # type: ignore
from somegraphspy import LogBase
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
    # Re-exported from ``somegraphspy``, since a form writes it into the code of a cell (e.g. ``mw.LogBase.Log2Base``).
    "LogBase",
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

    #: The ``metacellsgraphspy`` data source which fills the property from a ``Daf`` data set (e.g.,
    #: ``metacellsgraphspy.fill_total_UMIs``). Its keywords are the property's look arguments, with their defaults.
    data_source: Callable[..., None]

    # The arguments which change only how the property is shown, not its data (e.g. ``show_legend``).
    _look_arguments: ClassVar[FrozenSet[str]] = frozenset()

    # The defaults of the look arguments, as read from the data source, per class and name.
    _look_defaults: ClassVar[Dict[Tuple[type, str], Any]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, Property, ("exists", "fill", "editor"))

    @classmethod
    def look_default(cls, name: str) -> Any:
        """
        The default of the look argument with the ``name``, which applies while the argument is ``DEFAULT``. This is
        the default of the keyword of the same name of the ``data_source``.
        """
        key = (cls, name)
        if key not in Property._look_defaults:
            Property._look_defaults[key] = mg.function_default(cls.data_source, name)
        return Property._look_defaults[key]

    def look_arguments(self) -> Dict[str, Any]:
        """
        The values of the look arguments which are set (not ``DEFAULT``), by their names. These change only how the
        property is shown (e.g. ``show_legend``). A kind of data source passes them to the property's data source, which
        uses its own defaults for the others.
        """
        return {
            name: getattr(self, name)
            for name in sorted(self._look_arguments)
            if not isinstance(getattr(self, name), DefaultValue)
        }

    def _written_arguments(self) -> Dict[str, Any]:
        # A look argument which is ``DEFAULT`` leaves the data source's default, so it isn't written.
        return {
            name: value
            for name, value in self.arguments().items()
            if not isinstance(value, DefaultValue) or name not in self._look_arguments
        }

    def has_same_content(self, other: Any) -> bool:
        """
        Whether the ``other`` is a property of the same class, with the same values of the arguments other than the look
        arguments, so both show the same data.
        """
        if type(other) is not type(self):
            return False
        return _content_arguments(self) == _content_arguments(other)

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


# The arguments of a property other than its look arguments.
def _content_arguments(property_object: Property) -> Dict[str, Any]:
    look_arguments = property_object._look_arguments  # pylint: disable=protected-access
    return {name: value for name, value in property_object.arguments().items() if name not in look_arguments}


def size_property(
    class_name: str,
    *,
    property: str,  # pylint: disable=redefined-builtin
    data_source: Callable[..., None],
    doc: str,
) -> Any:
    """
    Make the class of a property which is a count, such as UMIs, named ``class_name`` and documented by the ``doc``.
    The data gives it the name ``property``, and the ``data_source`` fills it. Its objects take the look arguments
    ``show_legend`` and ``log_base``.
    """
    return _factory_property(
        class_name,
        eltype=Eltype.NUMBER,
        property_name=property,
        data_source=data_source,
        doc=doc,
        init=_init_with_show_legend_and_log_base,
        look_arguments=frozenset(["show_legend", "log_base"]),
    )


def category_property(
    class_name: str,
    *,
    property: str,  # pylint: disable=redefined-builtin
    data_source: Callable[..., None],
    doc: str,
) -> Any:
    """
    Make the class of a property which names a category, such as a type, named ``class_name`` and documented by the
    ``doc``. The data gives it the name ``property``, and the ``data_source`` fills it. Its objects take the look
    argument ``show_legend``.
    """
    return _factory_property(
        class_name,
        eltype=Eltype.CATEGORICAL,
        property_name=property,
        data_source=data_source,
        doc=doc,
        init=_init_with_show_legend,
        look_arguments=frozenset(["show_legend"]),
    )


def boolean_property(
    class_name: str,
    *,
    property: str,  # pylint: disable=redefined-builtin
    data_source: Callable[..., None],
    doc: str,
) -> Any:
    """
    Make the class of a property which is a Boolean flag, named ``class_name`` and documented by the ``doc``. The data
    gives it the name ``property``, and the ``data_source`` fills it. Its objects take the look argument
    ``show_legend``.
    """
    return _factory_property(
        class_name,
        eltype=Eltype.BOOLEAN,
        property_name=property,
        data_source=data_source,
        doc=doc,
        init=_init_with_show_legend,
        look_arguments=frozenset(["show_legend"]),
    )


# The constructor of a property whose only argument is ``show_legend``.
def _init_with_show_legend(self: Property, *, show_legend: Union[bool, DefaultValue] = DEFAULT) -> None:
    setattr(self, "show_legend", show_legend)


# The constructor of a property whose only arguments are ``show_legend`` and ``log_base``.
def _init_with_show_legend_and_log_base(
    self: Property,
    *,
    show_legend: Union[bool, DefaultValue] = DEFAULT,
    log_base: Union[LogBase, DefaultValue] = DEFAULT,
) -> None:
    setattr(self, "show_legend", show_legend)
    setattr(self, "log_base", log_base)


# Make the class of a property whose only arguments are its look arguments, as a factory does. The factories return the
# class as ``Any``, since a type checker can't see its generated constructor, and a property class can't inherit a typed
# one (it must derive directly from ``Property``, see ``_give_own_dispatchers``).
def _factory_property(
    class_name: str,
    *,
    eltype: Eltype,
    property_name: str,
    data_source: Callable[..., None],
    doc: str,
    init: Callable[..., None],
    look_arguments: FrozenSet[str],
) -> Any:
    namespace = {
        "__doc__": doc,
        "__module__": __name__,
        "__qualname__": class_name,
        "__init__": init,
        "eltype": eltype,
        "shape": Shape.VECTOR,
        "property_name": property_name,
        "data_source": staticmethod(data_source),
        "_look_arguments": look_arguments,
    }
    return type(class_name, (Property,), namespace)


Type = category_property(
    "Type",
    property="type",
    data_source=mg.fill_type,
    doc="The type of each entry, such as the cell type of each metacell, shown in its color.",
)

Block = category_property("Block", property="block", data_source=mg.fill_block, doc="The block each entry belongs to.")


class GeneExpression(Property):
    """
    The expression level (linear fraction) of the ``gene`` in each entry, shown on a log scale (base 2 by default). It
    takes the look arguments ``show_legend`` and ``log_base``.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR
    data_source = staticmethod(mg.fill_gene_expression)
    _look_arguments = frozenset(["show_legend", "log_base"])

    def __init__(
        self,
        gene: str,
        *,
        show_legend: Union[bool, DefaultValue] = DEFAULT,
        log_base: Union[LogBase, DefaultValue] = DEFAULT,
    ) -> None:
        self.gene = gene
        self.show_legend = show_legend
        self.log_base = log_base


TotalUMIs = size_property(
    "TotalUMIs",
    property="total_UMIs",
    data_source=mg.fill_total_UMIs,
    doc="The total number of UMIs of each entry.",
)

NCells = size_property(
    "NCells", property="n_cells", data_source=mg.fill_n_cells, doc="The number of cells of each entry."
)

NMetacells = size_property(
    "NMetacells",
    property="n_metacells",
    data_source=mg.fill_n_metacells,
    doc="The number of metacells of each entry.",
)

IsLateral = boolean_property(
    "IsLateral", property="is_lateral", data_source=mg.fill_is_lateral, doc="Whether each gene is lateral."
)

IsMarker = boolean_property(
    "IsMarker", property="is_marker", data_source=mg.fill_is_marker, doc="Whether each gene is a marker gene."
)


class MeanCellsPerMetacell(Property):
    """
    The mean number of cells per metacell of each entry. It takes the look arguments ``show_legend`` and ``log_base``.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR
    data_source = staticmethod(mg.fill_mean_cells_per_metacell)
    _look_arguments = frozenset(["show_legend", "log_base"])
    __init__ = _init_with_show_legend_and_log_base


class MeanTotalUMIsPerMetacell(Property):
    """
    The mean total number of UMIs per metacell of each entry. It takes the look arguments ``show_legend`` and
    ``log_base``.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR
    data_source = staticmethod(mg.fill_mean_total_UMIs_per_metacell)
    _look_arguments = frozenset(["show_legend", "log_base"])
    __init__ = _init_with_show_legend_and_log_base


class MeanTotalUMIsPerCell(Property):
    """
    The mean total number of UMIs per cell of each entry. It takes the look arguments ``show_legend`` and ``log_base``.
    """

    eltype = Eltype.NUMBER
    shape = Shape.VECTOR
    data_source = staticmethod(mg.fill_mean_total_UMIs_per_cell)
    _look_arguments = frozenset(["show_legend", "log_base"])
    __init__ = _init_with_show_legend_and_log_base


class BooleanMask(Property):
    """
    The Boolean mask property with the ``name`` of each entry. It takes the look argument ``show_legend``.
    """

    eltype = Eltype.BOOLEAN
    shape = Shape.VECTOR
    data_source = staticmethod(mg.fill_boolean)
    _look_arguments = frozenset(["show_legend"])

    def __init__(self, name: str, *, show_legend: Union[bool, DefaultValue] = DEFAULT) -> None:
        self.name = name
        self.show_legend = show_legend


class GlobalFlowOrder(Property):
    """
    The position of the type of each entry in the global flow order of the types.
    """

    eltype = Eltype.ARRANGEMENT
    shape = Shape.VECTOR
    data_source = staticmethod(mg.fill_global_flow_order)


class UMAP(Property):
    """
    The UMAP ``coordinate`` (``x`` or ``y``) of each entry, shown along an axis without ticks or a grid.
    """

    eltype = Eltype.COORDINATE
    shape = Shape.VECTOR
    data_source = staticmethod(mg.fill_umap)

    def __init__(self, coordinate: str) -> None:
        self.coordinate = coordinate
