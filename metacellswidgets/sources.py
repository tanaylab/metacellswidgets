"""
Kinds of data sources. Each kind is a class wrapping its data, such as a single ``Daf`` data set.

Each kind registers, per axis of its data, the properties a form may offer for that axis. The properties a slot
offers for an actual data source are those registered for its kind and axis, which suit the slot, and which the data
source has.

Each kind also offers its graphs as methods, e.g. ``DafWidgets(daf).gene_gene(...)``, using ``graph_constructor``.
"""

import inspect
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Concatenate
from typing import Dict
from typing import Generic
from typing import List
from typing import Optional
from typing import ParamSpec
from typing import Sequence
from typing import Set
from typing import Type
from typing import TypeVar
from typing import Union
from typing import overload

from .properties import Property
from .properties import Slot

__all__: List[str] = [
    "SourceWidgets",
    "graph_constructor",
]

_Parameters = ParamSpec("_Parameters")
_Graph = TypeVar("_Graph")


class _GraphConstructor(Generic[_Parameters, _Graph]):
    # Constructs a graph class with the data source it is read through, followed by the given arguments.

    def __init__(self, graph_class: Callable[Concatenate[Any, _Parameters], _Graph]) -> None:
        self.graph_class = graph_class
        self._name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    @overload
    def __get__(self, source: None, owner: type) -> "_GraphConstructor[_Parameters, _Graph]": ...

    @overload
    def __get__(self, source: "SourceWidgets", owner: type) -> Callable[_Parameters, _Graph]: ...

    def __get__(
        self, source: Optional["SourceWidgets"], owner: type
    ) -> Union["_GraphConstructor[_Parameters, _Graph]", Callable[_Parameters, _Graph]]:
        if source is None:
            return self
        graph_class = self.graph_class

        def construct(*args: _Parameters.args, **kwargs: _Parameters.kwargs) -> _Graph:
            return graph_class(source, *args, **kwargs)

        # So that completion and help show the graph's parameters and documentation.
        parameters = list(inspect.signature(graph_class).parameters.values())[1:]
        construct.__name__ = self._name
        construct.__qualname__ = f"{owner.__name__}.{self._name}"
        construct.__doc__ = graph_class.__doc__
        signature = inspect.signature(graph_class).replace(parameters=parameters, return_annotation=graph_class)
        setattr(construct, "__signature__", signature)
        return construct


def graph_constructor(
    graph_class: Callable[Concatenate[Any, _Parameters], _Graph],
) -> _GraphConstructor[_Parameters, _Graph]:
    """
    Offer the ``graph_class`` as a method of a kind of data source, e.g. ``gene_gene = graph_constructor(GeneGene)``.
    Then ``source.gene_gene(...)`` is ``GeneGene(source, ...)``. The method takes the parameters of the class's
    constructor after the data source, and has the class's documentation.
    """
    return _GraphConstructor(graph_class)


class SourceWidgets:
    """
    The base class of the kinds of data sources.

    A subclass also offers the properties registered for its base classes, so a kind can be extended by subclassing it.
    """

    # The properties registered for this class itself (not its base classes), per axis.
    _properties_per_axis: ClassVar[Dict[str, List[Type[Property]]]] = {}

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls._properties_per_axis = {}

    @classmethod
    def register_properties(cls, *, axis: str, properties: Sequence[Type[Property]]) -> None:
        """
        Register the ``properties`` a form may offer for the entries of the ``axis`` of this kind of data source.
        Registering a property which is already registered for the ``axis`` is an error.
        """
        registered = cls.registered_properties(axis)
        own = cls._properties_per_axis.setdefault(axis, [])
        for property_class in properties:
            if property_class in registered:
                raise ValueError(
                    f"the property: {property_class.__name__} is already registered "
                    f"for the axis: {axis} of: {cls.__name__}"
                )
            registered.append(property_class)
            own.append(property_class)

    @classmethod
    def registered_axes(cls) -> List[str]:
        """
        The axes of this kind of data source with any registered properties, including those of its base classes,
        sorted.
        """
        axes: Set[str] = set()
        for kind in cls.__mro__:
            if issubclass(kind, SourceWidgets):
                axes.update(kind._properties_per_axis)
        return sorted(axes)

    @classmethod
    def registered_properties(cls, axis: str) -> List[Type[Property]]:
        """
        The properties registered for the ``axis`` of this kind of data source, including those registered for its base
        classes, in the order they were registered (base classes first).
        """
        registered: List[Type[Property]] = []
        for kind in reversed(cls.__mro__):
            if issubclass(kind, SourceWidgets):
                registered += kind._properties_per_axis.get(axis, [])
        return registered

    @classmethod
    def offered_graphs(cls) -> Dict[str, Any]:
        """
        The graph classes this kind of data source offers as methods (using ``graph_constructor``), including those of
        its base classes, by the names of the methods.
        """
        graphs: Dict[str, Any] = {}
        for kind in reversed(cls.__mro__):
            for name, value in kind.__dict__.items():
                if isinstance(value, _GraphConstructor):
                    graphs[name] = value.graph_class
        return graphs

    def has_axis(self, axis: str) -> bool:  # pylint: disable=unused-argument
        """
        Whether this data source has entries of the ``axis``. Each kind of data source implements this.
        """
        return False

    def axes(self) -> List[str]:
        """
        The axes this data source has, of those with registered properties for its kind, sorted.
        """
        return [axis for axis in self.registered_axes() if self.has_axis(axis)]

    def properties(self, *, axis: str, slot: Slot) -> List[Type[Property]]:
        """
        The properties this data source can show in the ``slot`` for the entries of the ``axis``: those registered for
        its kind and the ``axis``, which suit the ``slot``, and which this data source has.
        """
        return [
            property_class
            for property_class in self.registered_properties(axis)
            if property_class.suits(slot) and property_class.exists(self, axis)
        ]
