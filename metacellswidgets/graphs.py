"""
The graphs a form can show. Each graph serves all the kinds of data sources which offer it.

The part of a graph which differs between kinds (e.g. building its base graph from the data) is a dispatched method,
which each kind implements in its own module (see :py:func:`~metacellswidgets.common.implements`).
"""

from typing import List
from typing import Optional
from typing import Sequence
from typing import cast

from ipywidgets import HBox  # type: ignore
from ipywidgets import Label  # type: ignore
from ipywidgets import VBox  # type: ignore
from ipywidgets import Widget  # type: ignore
from somegraphspy import Graph
from somegraphspy import PointsGraph

from .editors import AxisPicker
from .editors import GeneChoices
from .editors import GenePicker
from .editors import PropertyPicker
from .forms import GraphForm
from .properties import Property
from .properties import Slot
from .sources import SourceWidgets
from .tweaks import Tweak

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
        tweaks: Optional[Sequence[Tweak]] = None,
    ) -> None:
        super().__init__(source, tweaks)
        self.axis = axis
        # While editing, a gene may not be picked yet.
        self.x_gene: Optional[str] = x_gene
        self.y_gene: Optional[str] = y_gene
        self.colors = colors
        self.sizes = sizes

    def editor(self) -> Widget:
        # Every kind of data source offering this graph has genes to pick from.
        genes = cast(GeneChoices, self.source)
        axis = AxisPicker(self.source, ["metacell", "block"], self.axis)
        x_gene = GenePicker(genes, self.x_gene)
        y_gene = GenePicker(genes, self.y_gene)
        colors = PropertyPicker(self.source, Slot.COLORS, axis, self.colors)
        sizes = PropertyPicker(self.source, Slot.SIZES, axis, self.sizes)
        self.bind(axis=axis, x_gene=x_gene, y_gene=y_gene, colors=colors, sizes=sizes)
        return VBox(
            [
                HBox([Label("Axis"), axis, Label("X"), x_gene, Label("Y"), y_gene]),
                HBox([Label("Colors"), colors]),
                HBox([Label("Sizes"), sizes]),
            ]
        )

    def fill_slots(self, graph: Graph) -> None:
        assert isinstance(graph, PointsGraph)
        if self.colors is not None:
            self.colors.fill(self.source, graph.points_colors_vector_fields(), self.axis)
        if self.sizes is not None:
            self.sizes.fill(self.source, graph.points_sizes_vector_fields(), self.axis)
