"""
Kinds of data sources. Each kind is a class wrapping its data, such as a single ``Daf`` data set.

Each kind registers, per axis of its data, the properties a form may offer for that axis. The properties a slot
offers for an actual data source are those registered for its kind and axis, which suit the slot, and which the data
source has.
"""

from typing import ClassVar
from typing import Dict
from typing import List
from typing import Sequence
from typing import Set
from typing import Type

from .properties import Property
from .properties import Slot

__all__: List[str] = [
    "SourceWidgets",
]


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
