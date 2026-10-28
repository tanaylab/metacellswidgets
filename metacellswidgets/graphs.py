"""
The graphs a form can show. Each graph serves all the kinds of data sources which offer it.

The part of a graph which differs between kinds (e.g. building its base graph from the data) is a dispatched method,
which each kind implements in its own module (see :py:func:`~metacellswidgets.common.implements`).
"""

from typing import Any
from typing import List
from typing import Sequence
from typing import Tuple
from typing import cast

import numpy as np
from dafpy.julia_import import DEFAULT
from dafpy.julia_import import DefaultValue
from ipywidgets import HBox  # type: ignore
from ipywidgets import Label  # type: ignore
from ipywidgets import VBox  # type: ignore
from ipywidgets import Widget  # type: ignore
from metacellsgraphspy import Entries
from plotly.callbacks import BoxSelector  # type: ignore
from plotly.callbacks import LassoSelector  # type: ignore
from somegraphspy import Graph
from somegraphspy import HeatmapGraph
from somegraphspy import PointsGraph

from .editors import AxisPicker
from .editors import GeneChoices
from .editors import GenePicker
from .editors import ListEditor
from .editors import PropertyPicker
from .editors import ShownProperties
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
from .selections import _box_of
from .selections import _lasso_of
from .selections import _selected_names
from .selections import _selection_data
from .sources import SourceWidgets
from .tweaks import Tweak

__all__: List[str] = [
    "GeneGene",
    "GenesHeatmap",
]


# Fail if one of the ``hovers`` shows the same data as another one, or as one of the properties the ``side`` already
# shows (regardless of their look arguments).
def _check_hovers(hovers: Sequence[Property] | None, shown: Sequence[Property | None], side: str) -> None:
    seen = [shown_property for shown_property in shown if shown_property is not None]
    for hover in hovers or []:
        if any(hover.has_same_content(seen_property) for seen_property in seen):
            raise ValueError(f"the hover {hover!r} is already shown on the {side}")
        seen.append(hover)


class GeneGene(GraphForm):  # pylint: disable=too-many-instance-attributes
    """
    The expression of ``x_gene`` against ``y_gene``, a point per entry of the ``axis``, on log scale. The points may be
    colored by the ``colors`` property, and sized by the ``sizes`` property. The ``hovers`` properties add lines to the
    hover of each point (left out, there are none).

    Some of the points may be selected, by the ``selected_box`` (the minimal X, maximal X, minimal Y and maximal Y) or
    the ``selected_lasso`` (its vertices), in the units of the data (e.g. gene fractions). At most one of them may be
    given. :py:meth:`selected_names` gives the names of the selected entries.
    """

    graph_type = PointsGraph
    _selection_arguments = frozenset(["selected_box", "selected_lasso"])

    def __init__(
        self,
        source: SourceWidgets,
        *,
        axis: str = "metacell",
        x_gene: str,
        y_gene: str,
        colors: Property | None = None,
        sizes: Property | None = None,
        hovers: Sequence[Property] | None = None,
        selected_box: Tuple[float, float, float, float] | None = None,
        selected_lasso: Sequence[Tuple[float, float]] | None = None,
        tweaks: Sequence[Tweak] | None = None,
    ) -> None:
        super().__init__(source, tweaks)
        self.axis = axis
        # While editing, a gene may not be picked yet.
        self.x_gene: str | None = x_gene
        self.y_gene: str | None = y_gene
        self.colors = colors
        self.sizes = sizes
        self.hovers = None if hovers is None else list(hovers)
        _check_hovers(self.hovers, [colors, sizes], "points")
        if selected_box is not None and selected_lasso is not None:
            raise ValueError("at most one of selected_box and selected_lasso may be given")
        self.selected_box: Tuple[float, float, float, float] | None = (
            None if selected_box is None else (selected_box[0], selected_box[1], selected_box[2], selected_box[3])
        )
        self.selected_lasso: List[Tuple[float, float]] | None = None if selected_lasso is None else list(selected_lasso)

    def selected_names(self) -> List[str]:
        """
        The names of the entries whose points are inside the selection (``selected_box`` or ``selected_lasso``), in the
        order of the points, or an empty list if there is no selection. This uses the graph last shown, unless an
        argument other than the selection changed since, and then it builds the graph again.
        """
        if self.selected_box is None and self.selected_lasso is None:
            return []
        graph = self._selection_graph()
        assert isinstance(graph, PointsGraph)
        return _selected_names(graph, self.selected_box, self.selected_lasso)

    def _on_selection(self, selector: Any) -> None:
        graph = self._kept_graph
        if not isinstance(graph, PointsGraph):
            return
        if isinstance(selector, BoxSelector):
            self.selected_box = _box_of(graph, selector.xrange, selector.yrange)
            self.selected_lasso = None
        elif isinstance(selector, LassoSelector):
            self.selected_lasso = _lasso_of(graph, selector.xs, selector.ys)
            self.selected_box = None

    def _on_deselect(self) -> None:
        self.selected_box = None
        self.selected_lasso = None

    def editor(self) -> Widget:
        # Every kind of data source offering this graph has genes to pick from.
        genes = cast(GeneChoices, self.source)
        axis = AxisPicker(self.source, ["metacell", "block"], self.axis)
        x_gene = GenePicker(genes, self.x_gene)
        y_gene = GenePicker(genes, self.y_gene)
        colors = PropertyPicker(self.source, Slot.COLORS, axis, self.colors)
        sizes = PropertyPicker(self.source, Slot.SIZES, axis, self.sizes)
        points_shown = ShownProperties()
        hovers: ListEditor[Property] = ListEditor(
            lambda current: PropertyPicker(self.source, Slot.HOVERS, axis, current, shown=points_shown),
            self.hovers,
            title="Hovers",
        )
        points_shown.watch([colors, sizes], hovers, axis)
        self.bind(axis=axis, x_gene=x_gene, y_gene=y_gene, colors=colors, sizes=sizes, hovers=hovers)
        return VBox(
            [
                HBox([Label("Axis"), axis, Label("X"), x_gene, Label("Y"), y_gene]),
                HBox([Label("Colors"), colors]),
                HBox([Label("Sizes"), sizes]),
                hovers,
            ]
        )

    def fill_slots(self, graph: Graph) -> None:
        assert isinstance(graph, PointsGraph)
        if self.colors is not None:
            self.colors.fill(self.source, graph.points_colors_vector_fields(), self.axis)
        if self.sizes is not None:
            self.sizes.fill(self.source, graph.points_sizes_vector_fields(), self.axis)
        for hover_property in self.hovers or []:
            hover_property.fill(self.source, graph.points_entities(), self.axis)
        if self.selected_box is not None or self.selected_lasso is not None:
            graph.data.selection = _selection_data(self.selected_box, self.selected_lasso)


class GenesHeatmap(GraphForm):
    """
    The expression of the ``genes`` in each of the ``entries`` of the ``axis``, as the fold factor of each gene from
    its median across the entries. The rows (the genes) and the columns (the entries) may be annotated by properties.

    Left out, the ``genes`` are the strongest markers (:py:class:`~metacellswidgets.entries.TopMarkers`), the
    ``entries`` are all of them, and each side's annotations are its defaults: whether each gene is lateral, and the
    type of each entry, each only if the data has it. These are what ``add_genes_heatmap_default_rows_annotations``
    and ``add_genes_heatmap_default_columns_annotations`` of ``metacellsgraphspy`` add.

    An annotation also adds a line to the hover of each cell. The ``row_hovers`` and ``column_hovers`` properties add
    more lines, without annotating (left out, there are none).
    """

    graph_type = HeatmapGraph

    def __init__(
        self,
        source: SourceWidgets,
        *,
        axis: str = "metacell",
        genes: GeneSelection | DefaultValue = DEFAULT,
        entries: Sequence[EntryFilter] | None = None,
        row_annotations: Sequence[Property] | DefaultValue = DEFAULT,
        column_annotations: Sequence[Property] | DefaultValue = DEFAULT,
        row_hovers: Sequence[Property] | None = None,
        column_hovers: Sequence[Property] | None = None,
        tweaks: Sequence[Tweak] | None = None,
    ) -> None:
        super().__init__(source, tweaks)
        self.axis = axis
        self.genes = genes
        self.entries = None if entries is None else list(entries)
        self.row_annotations = row_annotations if isinstance(row_annotations, DefaultValue) else list(row_annotations)
        self.column_annotations = (
            column_annotations if isinstance(column_annotations, DefaultValue) else list(column_annotations)
        )
        self.row_hovers = None if row_hovers is None else list(row_hovers)
        self.column_hovers = None if column_hovers is None else list(column_hovers)
        _check_hovers(self.row_hovers, self._row_annotations(), "rows")
        _check_hovers(self.column_hovers, self._column_annotations(), "columns")

    def _row_annotations(self) -> List[Property]:
        # The annotations of the rows: the given ones, or else the default ones.
        if isinstance(self.row_annotations, DefaultValue):
            return self.default_row_annotations()
        return self.row_annotations

    def _column_annotations(self) -> List[Property]:
        # The annotations of the columns: the given ones, or else the default ones.
        if isinstance(self.column_annotations, DefaultValue):
            return self.default_column_annotations()
        return self.column_annotations

    def default_row_annotations(self) -> List[Property]:
        """
        The annotations of the rows (the genes) when ``row_annotations`` is left out: whether each gene is lateral, if
        the data has it.
        """
        return [property_class() for property_class in (IsLateral,) if property_class.exists(self.source, "gene")]

    def default_column_annotations(self, axis: str | DefaultValue = DEFAULT) -> List[Property]:
        """
        The annotations of the columns (the entries) when ``column_annotations`` is left out: the type of each entry,
        if the data has it. The entries are of the ``axis`` (by default, the form's).
        """
        axis = self.axis if isinstance(axis, DefaultValue) else axis
        return [property_class() for property_class in (Type,) if property_class.exists(self.source, axis)]

    def selected_genes(self) -> Entries:
        """
        The genes the ``genes`` select (by default, the strongest markers).
        """
        return (TopMarkers() if isinstance(self.genes, DefaultValue) else self.genes).genes(self.source)

    def selected_entries(self) -> np.ndarray | None:
        """
        The mask of the entries which pass all the ``entries`` filters, or ``None`` for all of them.
        """
        mask: np.ndarray | None = None
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
        rows_shown = ShownProperties()
        row_hovers: ListEditor[Property] = ListEditor(
            lambda current: PropertyPicker(self.source, Slot.HOVERS, "gene", current, shown=rows_shown),
            self.row_hovers,
            title="Row hovers",
        )
        rows_shown.watch([row_annotations], row_hovers)
        columns_shown = ShownProperties()
        column_hovers: ListEditor[Property] = ListEditor(
            lambda current: PropertyPicker(self.source, Slot.HOVERS, axis, current, shown=columns_shown),
            self.column_hovers,
            title="Column hovers",
        )
        columns_shown.watch([column_annotations], column_hovers, axis)
        self.bind(
            axis=axis,
            genes=genes,
            entries=entries,
            row_annotations=row_annotations,
            column_annotations=column_annotations,
            row_hovers=row_hovers,
            column_hovers=column_hovers,
        )
        return VBox(
            [
                HBox([Label("Axis"), axis, Label("Genes"), genes]),
                entries,
                row_annotations,
                column_annotations,
                row_hovers,
                column_hovers,
            ]
        )

    def fill_slots(self, graph: Graph) -> None:
        assert isinstance(graph, HeatmapGraph)
        for row_property in self._row_annotations():
            row_property.fill(
                self.source, graph.rows_annotations_colors_vector_fields(graph.add_rows_annotation()), "gene"
            )
        for column_property in self._column_annotations():
            column_property.fill(
                self.source, graph.columns_annotations_colors_vector_fields(graph.add_columns_annotation()), self.axis
            )
        for row_hover_property in self.row_hovers or []:
            row_hover_property.fill(self.source, graph.rows_entities(), "gene")
        for column_hover_property in self.column_hovers or []:
            column_hover_property.fill(self.source, graph.columns_entities(), self.axis)
