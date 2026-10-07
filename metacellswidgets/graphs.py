"""
The graphs a form can show. Each graph serves all the kinds of data sources which offer it.

The part of a graph which differs between kinds (e.g. building its base graph from the data) is a dispatched method,
which each kind implements in its own module (see :py:func:`~metacellswidgets.properties.implements`).
"""

from typing import List
from typing import Optional

from somegraphspy import PointsGraph

from .forms import GraphForm
from .properties import Property
from .sources import SourceWidgets

__all__: List[str] = [
    "GeneGene",
]


class GeneGene(GraphForm):
    """
    The expression of ``x_gene`` against ``y_gene``, a point per entry of the ``axis``, on log scale. The points may be
    colored by the ``colors`` property, and sized by the ``sizes`` property.
    """

    def __init__(
        self,
        source: SourceWidgets,
        *,
        axis: str = "metacell",
        x_gene: str,
        y_gene: str,
        colors: Optional[Property] = None,
        sizes: Optional[Property] = None,
    ) -> None:
        super().__init__(source)
        self.axis = axis
        self.x_gene = x_gene
        self.y_gene = y_gene
        self.colors = colors
        self.sizes = sizes

    def graph(self) -> PointsGraph:
        graph = self.base_graph(self.source)
        assert isinstance(graph, PointsGraph)
        if self.colors is not None:
            self.colors.fill(self.source, graph.points_colors_vector_fields(), self.axis)
        if self.sizes is not None:
            self.sizes.fill(self.source, graph.points_sizes_vector_fields(), self.axis)
        return graph
