"""
Objects which hold the values of their arguments, so they can be written back into the code of a cell.
"""

import inspect
from typing import Any
from typing import ClassVar
from typing import Dict
from typing import FrozenSet
from typing import List
from typing import Mapping
from typing import Optional

from .rewrite import _literal_text

__all__: List[str] = [
    "Arguments",
]


class Arguments:
    """
    The base class of objects which hold the values of their arguments, such as properties and graphs.

    The ``__init__`` of such an object stores the value of each of its arguments in an attribute of the same name. This
    is what lets a form write the object back into the code of its cell.
    """

    # The parameters of ``__init__`` which are not arguments (e.g., the data source of a graph).
    _not_arguments: ClassVar[FrozenSet[str]] = frozenset()

    def arguments(self) -> Dict[str, Any]:
        """
        The values of the arguments, by the names of the parameters of ``__init__``.
        """
        parameters = list(inspect.signature(type(self).__init__).parameters.values())[1:]
        return {
            parameter.name: getattr(self, parameter.name)
            for parameter in parameters
            if parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            and parameter.name not in self._not_arguments
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
