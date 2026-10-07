"""
What properties, graphs and tweaks share: holding the values of their arguments, so they can be written back into the
code of a cell, and methods implemented separately for each type of their first argument.
"""

import functools
import inspect
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Dict
from typing import FrozenSet
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import TypeVar

from .rewrite import _literal_text

__all__: List[str] = [
    "Arguments",
    "implements",
]


class Arguments:
    """
    The base class of objects which hold the values of their arguments, such as properties and graphs.

    The ``__init__`` of such an object stores the value of each of its arguments in an attribute of the same name. This
    is what lets a form write the object back into the code of its cell.

    Two such objects are equal if they have the same type and the same values of all the parameters of ``__init__``.
    They aren't hashable, since they may change (e.g., a form while it is edited).
    """

    # The parameters of ``__init__`` which are not arguments (e.g., the data source of a graph).
    _not_arguments: ClassVar[FrozenSet[str]] = frozenset()

    def arguments(self) -> Dict[str, Any]:
        """
        The values of the arguments, by the names of the parameters of ``__init__``.
        """
        return {name: value for name, value in self._parameter_values().items() if name not in self._not_arguments}

    def _parameter_values(self) -> Dict[str, Any]:
        # The values of all the parameters of ``__init__``, including those which are not arguments.
        parameters = list(inspect.signature(type(self).__init__).parameters.values())[1:]
        return {
            parameter.name: getattr(self, parameter.name)
            for parameter in parameters
            if parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }

    def code(self, callee: str, namespace: Optional[Mapping[str, Any]] = None) -> str:
        """
        The code which creates the object with its arguments, calling the ``callee`` (e.g., ``mw.GeneExpression``).
        Arguments which are themselves such objects name their classes as the ``namespace`` (of the cell) does.
        """
        arguments = [f"{name}={_literal_text(name, value, namespace)}" for name, value in self.arguments().items()]
        return f"{callee}({', '.join(arguments)})"

    def __repr__(self) -> str:
        return self.code(type(self).__name__)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Arguments)
            and type(other) is type(self)
            and other._parameter_values() == self._parameter_values()
        )


def _give_own_dispatchers(cls: type, base: type, names: Sequence[str]) -> None:
    # Give a subclass ``cls`` dispatchers of its own for the methods with the ``names`` of the ``base`` class, so that
    # registering an implementation of the methods of one subclass doesn't affect any other. The base's methods are the
    # implementations for any type which has none registered. A method the subclass defines itself is kept as is.
    for name in names:
        if name not in cls.__dict__:
            setattr(cls, name, functools.singledispatchmethod(base.__dict__[name]))


_Function = TypeVar("_Function", bound=Callable[..., Any])


def implements(method: Callable[..., Any], dispatch_type: type) -> Callable[[_Function], _Function]:
    """
    Register the decorated function as the implementation of a ``method`` for a ``dispatch_type`` of its first argument
    (after ``self`` or ``cls``). E.g., ``@implements(GeneExpression.fill, DafWidgets)`` implements a property's method
    for a kind of data source. The ``method`` is a ``functools.singledispatchmethod``. The function takes the same
    arguments as the method, including ``self`` (or ``cls`` for a class method).
    """
    # ``singledispatchmethod`` has a typed ``register``, but reading it through the class gives a function whose
    # ``register`` the type stubs don't declare.
    register = getattr(method, "register")
    is_class_method = isinstance(register.__self__.func, classmethod)

    def decorate(function: _Function) -> _Function:
        register(dispatch_type, classmethod(function) if is_class_method else function)
        return function

    return decorate
