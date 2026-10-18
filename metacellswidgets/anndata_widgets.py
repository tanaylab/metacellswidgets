"""
The ``AnnData`` kind of data source: a metacells ``AnnData`` (e.g., read from an ``h5ad`` file).

Each ``obs`` entry is a metacell, and ``X`` holds the expression level of each gene in each metacell (typically a
geometric mean, used as it is stored). This kind offers only a few properties, of the metacells and of the genes.
"""

from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

import metacellsgraphspy as mg
import numpy as np
from anndata import AnnData  # type: ignore
from somegraphspy import HeatmapGraph
from somegraphspy import PointsGraph
from somegraphspy import VectorDataSinks

from .common import implements
from .editors import GenePicker
from .editors import NamePicker
from .editors import PickerEditor
from .entries import GeneList
from .entries import OfTypes
from .entries import TopMarkers
from .forms import Branch
from .forms import graph_menu
from .graphs import GeneGene
from .graphs import GenesHeatmap
from .properties import UMAP
from .properties import GeneExpression
from .properties import IsLateral
from .properties import IsMarker
from .properties import Property
from .properties import TotalUMIs
from .properties import Type
from .sources import SourceWidgets
from .sources import graph_constructor

__all__: List[str] = [
    "AnnDataWidgets",
]


class AnnDataWidgets(SourceWidgets):
    """
    Interactive graphs of a metacells ``AnnData``. The types of the metacells are in the ``type_property`` of its
    ``obs``, and their colors are in the ``type_colors_csv`` file (see ``metacellsgraphspy.ad_get_type_colors``).
    """

    gene_gene = graph_constructor(GeneGene)
    genes_heatmap = graph_constructor(GenesHeatmap)

    #: The tree of the graphs offered, as shown in the menus.
    graphs = Branch("Graphs", [GeneGene, GenesHeatmap])

    menu = graph_menu(graphs)

    def __init__(self, adata: AnnData, *, type_property: str, type_colors_csv: str) -> None:
        self.adata = adata
        self.type_property = type_property
        self.type_colors_csv = type_colors_csv
        self._gene_choices: Dict[bool, List[Tuple[str, str]]] = {}

    def has_axis(self, axis: str) -> bool:
        return axis in ("metacell", "gene")

    def gene_choices(self, *, markers_only: bool = False) -> List[Tuple[str, str]]:
        """
        The (label, name) of each gene, in the order of the ``var`` entries. The label is the name. Genes marked in the
        ``excluded_gene`` column of ``var`` (if there is one) are never included. If ``markers_only``, only the genes
        marked in the ``marker_gene`` column of ``var`` are included (none, if there is no such column).
        """
        if markers_only not in self._gene_choices:
            is_included = ~self._var_mask("excluded_gene")
            if markers_only:
                is_included &= self._var_mask("marker_gene")
            names = self.adata.var_names
            self._gene_choices[markers_only] = [
                (str(names[index]), str(names[index])) for index in np.flatnonzero(is_included)
            ]
        return self._gene_choices[markers_only]

    def type_names(self) -> List[str]:
        """
        The names of the types (the distinct values of the ``type_property`` of the ``obs``, without missing ones),
        sorted.
        """
        return sorted({str(name) for name in self.adata.obs[self.type_property].dropna()})

    def _var_mask(self, column: str) -> np.ndarray:
        # The Boolean ``column`` of ``var``, or all false if there is no such column.
        if column not in self.adata.var:
            return np.zeros(self.adata.n_vars, dtype="bool")
        return np.asarray(self.adata.var[column], dtype="bool")


# A table line of the properties of a bucket: the property, the axis it is offered for, its column (of the ``obs`` for
# the metacells, of the ``var`` for the genes), and its ``metacellsgraphspy`` fill.
_BucketLine = Tuple[type[Property], str, str, Callable[..., None]]

# The properties which are counts.
_SIZE_PROPERTIES: Sequence[_BucketLine] = ((TotalUMIs, "metacell", "total_umis", mg.ad_fill_total_UMIs),)

# The properties which are Boolean flags.
_BOOLEAN_PROPERTIES: Sequence[_BucketLine] = (
    (IsLateral, "gene", "lateral_gene", mg.ad_fill_is_lateral),
    (IsMarker, "gene", "marker_gene", mg.ad_fill_is_marker),
)

# The other properties of the metacells, which need more than a column (e.g., the type colors) or take arguments. Each
# is implemented below on its own.
_OTHER_PROPERTIES: Sequence[type[Property]] = (Type, GeneExpression, UMAP)


# The implementation of ``exists`` for a table line, which checks for the line's ``column`` on the line's
# ``line_axis``.
def _line_exists(line_axis: str, column: str) -> Callable[[type[Property], AnnDataWidgets, str], bool]:
    def exists_line(_cls: type[Property], source: AnnDataWidgets, axis: str) -> bool:
        frame = source.adata.obs if line_axis == "metacell" else source.adata.var
        return axis == line_axis and column in frame

    return exists_line


# The implementation of ``fill`` for a table line, which calls the line's ``fill`` function.
def _line_fill(fill: Callable[..., None]) -> Callable[[Property, AnnDataWidgets, VectorDataSinks, str], None]:
    def fill_line(_self: Property, source: AnnDataWidgets, sinks: VectorDataSinks, _axis: str) -> None:
        fill(sinks, source.adata)

    return fill_line


for _property_class, _axis, _column, _fill in (*_SIZE_PROPERTIES, *_BOOLEAN_PROPERTIES):
    implements(_property_class.exists, AnnDataWidgets)(_line_exists(_axis, _column))
    implements(_property_class.fill, AnnDataWidgets)(_line_fill(_fill))


@implements(Type.exists, AnnDataWidgets)
def _has_type(_cls: type, source: AnnDataWidgets, axis: str) -> bool:
    return axis == "metacell" and source.type_property in source.adata.obs


@implements(Type.fill, AnnDataWidgets)
def _fill_type(_self: Property, source: AnnDataWidgets, sinks: VectorDataSinks, _axis: str) -> None:
    mg.ad_fill_type(sinks, source.adata, type_property=source.type_property, type_colors_csv=source.type_colors_csv)


@implements(GeneExpression.exists, AnnDataWidgets)
def _has_gene_expression(_cls: type, _source: AnnDataWidgets, axis: str) -> bool:
    return axis == "metacell"


@implements(GeneExpression.fill, AnnDataWidgets)
def _fill_gene_expression(self: GeneExpression, source: AnnDataWidgets, sinks: VectorDataSinks, _axis: str) -> None:
    mg.ad_fill_gene_expression(sinks, source.adata, gene=self.gene)


@implements(GeneExpression.editor, AnnDataWidgets)
def _gene_expression_editor(
    _cls: type, source: AnnDataWidgets, _axis: str, current: Optional[GeneExpression]
) -> PickerEditor:
    return PickerEditor(GenePicker(source, None if current is None else current.gene), GeneExpression)


@implements(UMAP.exists, AnnDataWidgets)
def _has_umap(_cls: type, source: AnnDataWidgets, axis: str) -> bool:
    return axis == "metacell" and "x" in source.adata.obs and "y" in source.adata.obs


@implements(UMAP.fill, AnnDataWidgets)
def _fill_umap(self: UMAP, source: AnnDataWidgets, sinks: VectorDataSinks, _axis: str) -> None:
    mg.ad_fill_umap(sinks, source.adata, coordinate=self.coordinate)


@implements(UMAP.editor, AnnDataWidgets)
def _umap_editor(_cls: type, _source: AnnDataWidgets, _axis: str, current: Optional[UMAP]) -> PickerEditor:
    return PickerEditor(NamePicker(["x", "y"], None if current is None else current.coordinate), UMAP)


@implements(GeneGene.exists, AnnDataWidgets)
def _has_gene_gene(_cls: type, _source: AnnDataWidgets) -> bool:
    return True


@implements(GeneGene.base_graph, AnnDataWidgets)
def _gene_gene_base_graph(self: GeneGene, source: AnnDataWidgets) -> PointsGraph:
    assert self.x_gene is not None and self.y_gene is not None
    return mg.ad_gene_gene_graph(source.adata, x_gene=self.x_gene, y_gene=self.y_gene)


@implements(GenesHeatmap.exists, AnnDataWidgets)
def _has_genes_heatmap(_cls: type, _source: AnnDataWidgets) -> bool:
    return True


@implements(GenesHeatmap.base_graph, AnnDataWidgets)
def _genes_heatmap_base_graph(self: GenesHeatmap, source: AnnDataWidgets) -> HeatmapGraph:
    return mg.ad_genes_heatmap_graph(source.adata, genes=self.selected_genes(), entries=self.selected_entries())


@implements(TopMarkers.exists, AnnDataWidgets)
def _has_top_markers(_cls: type, source: AnnDataWidgets) -> bool:
    return "marker_gene" in source.adata.var


@implements(TopMarkers.genes, AnnDataWidgets)
def _top_markers_genes(self: TopMarkers, source: AnnDataWidgets) -> mg.Entries:
    return mg.ad_get_top_marker_gene_indices(source.adata, markers_count=self.count)


@implements(GeneList.exists, AnnDataWidgets)
def _has_gene_list(_cls: type, _source: AnnDataWidgets) -> bool:
    return True


@implements(GeneList.genes, AnnDataWidgets)
def _gene_list_genes(self: GeneList, _source: AnnDataWidgets) -> mg.Entries:
    return self.names


@implements(OfTypes.exists, AnnDataWidgets)
def _has_of_types(_cls: type, source: AnnDataWidgets, axis: str) -> bool:
    return axis == "metacell" and source.type_property in source.adata.obs


@implements(OfTypes.mask, AnnDataWidgets)
def _of_types_mask(self: OfTypes, source: AnnDataWidgets, _axis: str) -> np.ndarray:
    return mg.ad_get_is_in_categories_vector(source.adata, property=source.type_property, categories=self.types)


for _property_class, _axis, _column, _fill in (*_SIZE_PROPERTIES, *_BOOLEAN_PROPERTIES):
    AnnDataWidgets.register_properties(axis=_axis, properties=[_property_class])

AnnDataWidgets.register_properties(axis="metacell", properties=_OTHER_PROPERTIES)
