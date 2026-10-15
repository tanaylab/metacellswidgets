"""
The graphs a form can show. Each graph serves all the kinds of data sources which offer it.

The part of a graph which differs between kinds (e.g. building its base graph from the data) is a dispatched method,
which each kind implements in its own module (see :py:func:`~metacellswidgets.common.implements`).
"""

from typing import List
from typing import Optional
from typing import Sequence
from typing import cast

import numpy as np
from ipywidgets import HBox  # type: ignore
from ipywidgets import Label  # type: ignore
from ipywidgets import VBox  # type: ignore
from ipywidgets import Widget  # type: ignore
from metacellsgraphspy import Entries
from somegraphspy import Graph
from somegraphspy import HeatmapGraph
from somegraphspy import PointsGraph

from .editors import AxisPicker
from .editors import GeneChoices
from .editors import GenePicker
from .editors import ListEditor
from .editors import PropertyPicker
from .entries import EntryFilter
from .entries import EntryFilterPicker
from .entries import GeneSelection
from .entries import GeneSelectionPicker
from .entries import TopMarkers
from .forms import GraphForm
from .properties import IsLateral
from .properties import Property
from .properties import Slot
from .properties import Type
from .sources import SourceWidgets
from .tweaks import Tweak

__all__: List[str] = [
    "GeneGene",
    "GenesHeatmap",
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


class GenesHeatmap(GraphForm):
    """
    The expression of the ``genes`` in each of the ``entries`` of the ``axis``, as the fold factor of each gene from
    its median across the entries. The rows (the genes) and the columns (the entries) may be annotated by properties.

    Left out, the ``genes`` are the strongest markers (:py:class:`~metacellswidgets.entries.TopMarkers`), the
    ``entries`` are all of them, and each side's annotations are its defaults: whether each gene is lateral, and the
    type of each entry, each only if the data has it. These are what ``add_genes_heatmap_default_rows_annotations``
    and ``add_genes_heatmap_default_columns_annotations`` of ``metacellsgraphspy`` add.
    """

    def __init__(
        self,
        source: SourceWidgets,
        *,
        axis: str = "metacell",
        genes: Optional[GeneSelection] = None,
        entries: Optional[Sequence[EntryFilter]] = None,
        row_annotations: Optional[Sequence[Property]] = None,
        column_annotations: Optional[Sequence[Property]] = None,
        tweaks: Optional[Sequence[Tweak]] = None,
    ) -> None:
        super().__init__(source, tweaks)
        self.axis = axis
        self.genes = genes
        self.entries = None if entries is None else list(entries)
        self.row_annotations = None if row_annotations is None else list(row_annotations)
        self.column_annotations = None if column_annotations is None else list(column_annotations)

    def default_row_annotations(self) -> List[Property]:
        """
        The annotations of the rows (the genes) when ``row_annotations`` is left out: whether each gene is lateral, if
        the data has it.
        """
        return [property_class() for property_class in (IsLateral,) if property_class.exists(self.source, "gene")]

    def default_column_annotations(self, axis: Optional[str] = None) -> List[Property]:
        """
        The annotations of the columns (the entries) when ``column_annotations`` is left out: the type of each entry,
        if the data has it. The entries are of the ``axis`` (by default, the form's).
        """
        axis = self.axis if axis is None else axis
        return [property_class() for property_class in (Type,) if property_class.exists(self.source, axis)]

    def selected_genes(self) -> Entries:
        """
        The genes the ``genes`` select (by default, the strongest markers).
        """
        return (TopMarkers() if self.genes is None else self.genes).genes(self.source)

    def selected_entries(self) -> Optional[np.ndarray]:
        """
        The mask of the entries which pass all the ``entries`` filters, or ``None`` for all of them.
        """
        mask: Optional[np.ndarray] = None
        for entry_filter in self.entries or []:
            filter_mask = entry_filter.mask(self.source, self.axis)
            mask = filter_mask if mask is None else mask & filter_mask
        return mask

    def editor(self) -> Widget:
        axis = AxisPicker(self.source, ["metacell", "block"], self.axis)
        genes = GeneSelectionPicker(self.source, self.genes)
        entries: ListEditor[EntryFilter] = ListEditor(
            lambda current: EntryFilterPicker(self.source, axis, current), self.entries, title="Filters"
        )
        row_annotations: ListEditor[Property] = ListEditor(
            lambda current: PropertyPicker(self.source, Slot.COLORS, "gene", current),
            self.row_annotations,
            default=self.default_row_annotations(),
            title="Row annotations",
        )
        column_annotations: ListEditor[Property] = ListEditor(
            lambda current: PropertyPicker(self.source, Slot.COLORS, axis, current),
            self.column_annotations,
            axis=axis,
            default=self.default_column_annotations,
            title="Column annotations",
        )
        self.bind(
            axis=axis,
            genes=genes,
            entries=entries,
            row_annotations=row_annotations,
            column_annotations=column_annotations,
        )
        return VBox(
            [
                HBox([Label("Axis"), axis, Label("Genes"), genes]),
                entries,
                row_annotations,
                column_annotations,
            ]
        )

    def fill_slots(self, graph: Graph) -> None:
        assert isinstance(graph, HeatmapGraph)
        rows = self.default_row_annotations() if self.row_annotations is None else self.row_annotations
        for row_property in rows:
            row_property.fill(
                self.source, graph.rows_annotations_colors_vector_fields(graph.add_rows_annotation()), "gene"
            )
        columns = self.default_column_annotations() if self.column_annotations is None else self.column_annotations
        for column_property in columns:
            column_property.fill(
                self.source, graph.columns_annotations_colors_vector_fields(graph.add_columns_annotation()), self.axis
            )
