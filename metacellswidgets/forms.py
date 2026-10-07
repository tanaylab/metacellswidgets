"""
Forms: the graphs a notebook cell shows, holding the arguments they were created with.

A form is created by a method of a kind of data source, e.g. ``mw.DafWidgets(daf).gene_gene(x_gene="Foxa1", ...)``.
Displaying it shows its graph.
"""

from typing import ClassVar
from typing import FrozenSet
from typing import List

from IPython.display import display as display_in_cell
from somegraphspy import Graph

from .arguments import Arguments
from .sources import SourceWidgets

__all__: List[str] = [
    "GraphForm",
]


class GraphForm(Arguments):
    """
    The base class of the forms of graphs. It holds the data ``source`` the graph is drawn from, and the values of the
    graph's arguments (see :py:class:`~metacellswidgets.arguments.Arguments`).
    """

    # The data source is written into the code of the cell as the receiver of the call (e.g. ``source.gene_gene(...)``),
    # not as an argument.
    _not_arguments: ClassVar[FrozenSet[str]] = frozenset(["source"])

    def __init__(self, source: SourceWidgets) -> None:
        self.source = source

    def graph(self) -> Graph:
        """
        The graph, built from the data source and the arguments.
        """
        raise NotImplementedError(f"{type(self).__name__}.graph")

    def display(self) -> "GraphForm":
        """
        Show the graph in the notebook cell. Returns the form, so it can be chained to its creation.
        """
        display_in_cell(self.graph().figure)
        return self
