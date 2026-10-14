"""
The ``Daf`` kind of data source: a single ``Daf`` data set of metacells.
"""

from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Tuple

import metacellsgraphspy as mg
import numpy as np
from dafpy import DafReader
from somegraphspy import PointsGraph
from somegraphspy import VectorDataSinks

from .common import implements
from .editors import GenePicker
from .editors import NamePicker
from .editors import PickerEditor
from .entries import GeneList
from .entries import InEnvironment
from .entries import InNeighborhood
from .entries import OfTypes
from .entries import SkeletonGenes
from .entries import TopMarkers
from .forms import Branch
from .graphs import GeneGene
from .properties import UMAP
from .properties import Block
from .properties import BooleanMask
from .properties import GeneExpression
from .properties import GlobalFlowOrder
from .properties import IsLateral
from .properties import IsMarker
from .properties import MeanCellsPerMetacell
from .properties import MeanTotalUMIsPerCell
from .properties import MeanTotalUMIsPerMetacell
from .properties import NCells
from .properties import NMetacells
from .properties import Property
from .properties import TotalUMIs
from .properties import Type
from .sources import SourceWidgets
from .sources import graph_constructor

__all__: List[str] = [
    "DafWidgets",
]

# The flags shown after the name of a gene, in this order, and the Boolean gene property each stands for.
_GENE_FLAGS = (
    ("L", "is_lateral"),
    ("M", "is_marker"),
    ("T", "is_transcription_factor"),
    ("R", "is_regulator"),
    ("F", "is_forbidden"),
    ("S", "is_skeleton"),
)


class DafWidgets(SourceWidgets):
    """
    Interactive graphs of a single ``Daf`` data set of metacells.
    """

    gene_gene = graph_constructor(GeneGene)

    #: The tree of the graphs offered, as shown in the menus.
    graphs = Branch("Graphs", [GeneGene])

    def __init__(self, daf: DafReader) -> None:
        self.daf = daf
        self._gene_choices: Dict[bool, List[Tuple[str, str]]] = {}
        self._boolean_vectors: Dict[str, List[str]] = {}

    def has_axis(self, axis: str) -> bool:
        return self.daf.has_axis(axis)

    def gene_choices(self, *, markers_only: bool = False) -> List[Tuple[str, str]]:
        """
        The (label, name) of each gene, in the order of the gene axis. Excluded genes are never included. If
        ``markers_only``, only the marker genes are included. The label is the name followed by the flags of the gene:
        ``L`` (lateral), ``M`` (marker), ``T`` (transcription factor), ``R`` (regulator), ``F`` (forbidden), ``S``
        (skeleton), e.g. ``Foxa1 M T R``. A flag the data set doesn't have is never shown.
        """
        if markers_only not in self._gene_choices:
            names = self.daf.axis_np_vector("gene")
            is_included = ~self._gene_mask("is_excluded")
            if markers_only:
                is_included &= self._gene_mask("is_marker")
            flags = [(flag, self._gene_mask(name)) for flag, name in _GENE_FLAGS if self.daf.has_vector("gene", name)]
            choices: List[Tuple[str, str]] = []
            for index in np.flatnonzero(is_included):
                name = str(names[index])
                letters = [flag for flag, mask in flags if mask[index]]
                choices.append((" ".join([name] + letters), name))
            self._gene_choices[markers_only] = choices
        return self._gene_choices[markers_only]

    def boolean_vectors(self, axis: str) -> List[str]:
        """
        The names of the Boolean vector properties of the ``axis``, sorted.
        """
        if axis not in self._boolean_vectors:
            self._boolean_vectors[axis] = sorted(
                name for name in self.daf.vectors_set(axis) if self.daf.get_np_vector(axis, name).dtype == np.bool_
            )
        return self._boolean_vectors[axis]

    def type_names(self) -> List[str]:
        """
        The names of the types, sorted.
        """
        return sorted(str(name) for name in self.daf.axis_np_vector("type"))

    def block_names(self) -> List[str]:
        """
        The names of the blocks, in the order of the block axis.
        """
        return [str(name) for name in self.daf.axis_np_vector("block")]

    def _gene_mask(self, name: str) -> np.ndarray:
        # The Boolean gene property with the ``name``, or all false if the data set doesn't have it.
        if not self.daf.has_vector("gene", name):
            return np.zeros(len(self.daf.axis_np_vector("gene")), dtype="bool")
        return np.asarray(self.daf.get_np_vector("gene", name), dtype="bool")

    def _has_vectors(self, axis: str, *names: str) -> bool:
        # Whether the ``axis`` exists and has all the vectors with the ``names``.
        return self.daf.has_axis(axis) and all(self.daf.has_vector(axis, name) for name in names)


# A table line of the properties of a bucket: the property, its ``metacellsgraphspy`` fill, and the axes it is offered
# for.
_BucketLine = Tuple[type[Property], Callable[..., None], Tuple[str, ...]]

# The properties which are counts.
_SIZE_PROPERTIES: Sequence[_BucketLine] = (
    (TotalUMIs, mg.fill_total_UMIs, ("metacell", "block")),
    (NCells, mg.fill_n_cells, ("metacell", "block")),
    (NMetacells, mg.fill_n_metacells, ("block",)),
)

# The properties which name a category.
_CATEGORY_PROPERTIES: Sequence[_BucketLine] = (
    (Type, mg.fill_type, ("metacell", "block")),
    (Block, mg.fill_block, ("metacell",)),
)

# The properties which are Boolean flags.
_BOOLEAN_PROPERTIES: Sequence[_BucketLine] = (
    (IsLateral, mg.fill_is_lateral, ("gene",)),
    (IsMarker, mg.fill_is_marker, ("gene",)),
)

# The other properties, which are derived or take arguments, and the axes each is offered for. Each is implemented
# below on its own.
_OTHER_PROPERTIES: Sequence[Tuple[type[Property], Tuple[str, ...]]] = (
    (GeneExpression, ("metacell", "block")),
    (MeanCellsPerMetacell, ("block",)),
    (MeanTotalUMIsPerMetacell, ("block",)),
    (MeanTotalUMIsPerCell, ("metacell", "block")),
    (BooleanMask, ("metacell", "block")),
    (GlobalFlowOrder, ("metacell", "block")),
    (UMAP, ("metacell", "block")),
)


def _has_vector(cls: type[Property], source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, cls.property_name)


def _has_category(cls: type[Property], source: DafWidgets, axis: str) -> bool:
    # The palette of a category comes from the axis of the same name (e.g., the ``type`` axis of the types).
    return source._has_vectors(axis, cls.property_name) and source.daf.has_axis(cls.property_name)


# The implementation of ``fill`` for a table line, which calls the line's ``fill`` function.
def _line_fill(fill: Callable[..., None]) -> Callable[[Property, DafWidgets, VectorDataSinks, str], None]:
    def fill_line(_self: Property, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
        fill(sinks, source.daf, axis=axis)

    return fill_line


for _property_class, _fill, _axes in (*_SIZE_PROPERTIES, *_BOOLEAN_PROPERTIES):
    implements(_property_class.exists, DafWidgets)(_has_vector)
    implements(_property_class.fill, DafWidgets)(_line_fill(_fill))

for _property_class, _fill, _axes in _CATEGORY_PROPERTIES:
    implements(_property_class.exists, DafWidgets)(_has_category)
    implements(_property_class.fill, DafWidgets)(_line_fill(_fill))


@implements(GeneExpression.exists, DafWidgets)
def _has_gene_expression(_cls: type, source: DafWidgets, axis: str) -> bool:
    return (
        source.daf.has_axis(axis)
        and source.daf.has_axis("gene")
        and source.daf.has_matrix("gene", axis, "linear_fraction")
    )


@implements(GeneExpression.fill, DafWidgets)
def _fill_gene_expression(self: GeneExpression, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_gene_expression(sinks, source.daf, axis=axis, gene=self.gene)


@implements(GeneExpression.editor, DafWidgets)
def _gene_expression_editor(
    _cls: type, source: DafWidgets, _axis: str, current: Optional[GeneExpression]
) -> PickerEditor:
    return PickerEditor(GenePicker(source, None if current is None else current.gene), GeneExpression)


@implements(MeanCellsPerMetacell.exists, DafWidgets)
def _has_mean_cells_per_metacell(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "n_cells", "n_metacells")


@implements(MeanCellsPerMetacell.fill, DafWidgets)
def _fill_mean_cells_per_metacell(
    _self: MeanCellsPerMetacell, source: DafWidgets, sinks: VectorDataSinks, axis: str
) -> None:
    mg.fill_mean_cells_per_metacell(sinks, source.daf, axis=axis)


@implements(MeanTotalUMIsPerMetacell.exists, DafWidgets)
def _has_mean_total_umis_per_metacell(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "total_UMIs", "n_metacells")


@implements(MeanTotalUMIsPerMetacell.fill, DafWidgets)
def _fill_mean_total_umis_per_metacell(
    _self: MeanTotalUMIsPerMetacell, source: DafWidgets, sinks: VectorDataSinks, axis: str
) -> None:
    mg.fill_mean_total_UMIs_per_metacell(sinks, source.daf, axis=axis)


@implements(MeanTotalUMIsPerCell.exists, DafWidgets)
def _has_mean_total_umis_per_cell(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "total_UMIs", "n_cells")


@implements(MeanTotalUMIsPerCell.fill, DafWidgets)
def _fill_mean_total_umis_per_cell(
    _self: MeanTotalUMIsPerCell, source: DafWidgets, sinks: VectorDataSinks, axis: str
) -> None:
    mg.fill_mean_total_UMIs_per_cell(sinks, source.daf, axis=axis)


@implements(BooleanMask.exists, DafWidgets)
def _has_boolean_mask(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source.daf.has_axis(axis) and len(source.boolean_vectors(axis)) > 0


@implements(BooleanMask.fill, DafWidgets)
def _fill_boolean_mask(self: BooleanMask, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_boolean(sinks, source.daf, axis=axis, property=self.name)


@implements(BooleanMask.editor, DafWidgets)
def _boolean_mask_editor(_cls: type, source: DafWidgets, axis: str, current: Optional[BooleanMask]) -> PickerEditor:
    current_name = None if current is None else current.name
    return PickerEditor(NamePicker(source.boolean_vectors(axis), current_name), BooleanMask)


@implements(GlobalFlowOrder.exists, DafWidgets)
def _has_global_flow_order(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "type") and source._has_vectors("type", "global_flow_order")


@implements(GlobalFlowOrder.fill, DafWidgets)
def _fill_global_flow_order(_self: GlobalFlowOrder, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_global_flow_order(sinks, source.daf, axis=axis)


@implements(UMAP.exists, DafWidgets)
def _has_umap(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "umap_x", "umap_y")


@implements(UMAP.fill, DafWidgets)
def _fill_umap(self: UMAP, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_umap(sinks, source.daf, axis=axis, coordinate=self.coordinate)


@implements(UMAP.editor, DafWidgets)
def _umap_editor(_cls: type, _source: DafWidgets, _axis: str, current: Optional[UMAP]) -> PickerEditor:
    return PickerEditor(NamePicker(["x", "y"], None if current is None else current.coordinate), UMAP)


@implements(GeneGene.exists, DafWidgets)
def _has_gene_gene(_cls: type, source: DafWidgets) -> bool:
    return any(GeneExpression.exists(source, axis) for axis in ("metacell", "block"))


@implements(GeneGene.base_graph, DafWidgets)
def _gene_gene_base_graph(self: GeneGene, source: DafWidgets) -> PointsGraph:
    assert self.x_gene is not None and self.y_gene is not None
    return mg.gene_gene_graph(source.daf, axis=self.axis, x_gene=self.x_gene, y_gene=self.y_gene)


@implements(TopMarkers.exists, DafWidgets)
def _has_top_markers(_cls: type, source: DafWidgets) -> bool:
    return source._has_vectors("gene", "marker_rank")


@implements(TopMarkers.genes, DafWidgets)
def _top_markers_genes(self: TopMarkers, source: DafWidgets) -> mg.Entries:
    return mg.get_top_marker_gene_indices(source.daf, markers_count=self.count)


@implements(SkeletonGenes.exists, DafWidgets)
def _has_skeleton_genes(_cls: type, source: DafWidgets) -> bool:
    return source._has_vectors("gene", "is_skeleton")


@implements(SkeletonGenes.genes, DafWidgets)
def _skeleton_genes_genes(_self: SkeletonGenes, source: DafWidgets) -> mg.Entries:
    return mg.get_skeleton_gene_indices(source.daf)


@implements(GeneList.exists, DafWidgets)
def _has_gene_list(_cls: type, source: DafWidgets) -> bool:
    return source.daf.has_axis("gene")


@implements(GeneList.genes, DafWidgets)
def _gene_list_genes(self: GeneList, _source: DafWidgets) -> mg.Entries:
    return self.names


@implements(OfTypes.exists, DafWidgets)
def _has_of_types(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "type") and source.daf.has_axis("type")


@implements(OfTypes.mask, DafWidgets)
def _of_types_mask(self: OfTypes, source: DafWidgets, axis: str) -> np.ndarray:
    return mg.get_is_in_categories_vector(source.daf, axis=axis, property="type", categories=self.types)


@implements(InNeighborhood.exists, DafWidgets)
def _has_in_neighborhood(_cls: type, source: DafWidgets, axis: str) -> bool:
    return (
        source.daf.has_axis("block")
        and source.daf.has_matrix("block", "block", "is_in_neighborhood")
        and (axis == "block" or source._has_vectors(axis, "block"))
    )


@implements(InNeighborhood.mask, DafWidgets)
def _in_neighborhood_mask(self: InNeighborhood, source: DafWidgets, axis: str) -> np.ndarray:
    return mg.get_is_in_neighborhood_vector(source.daf, axis=axis, block=self.block)


@implements(InEnvironment.exists, DafWidgets)
def _has_in_environment(_cls: type, source: DafWidgets, axis: str) -> bool:
    return (
        axis == "metacell"
        and source.daf.has_axis("metacell")
        and source.daf.has_axis("block")
        and source.daf.has_matrix("metacell", "block", "is_in_environment")
    )


@implements(InEnvironment.mask, DafWidgets)
def _in_environment_mask(self: InEnvironment, source: DafWidgets, axis: str) -> np.ndarray:
    return mg.get_is_in_environment_vector(source.daf, axis=axis, block=self.block)


for _property_class, _fill, _axes in (*_SIZE_PROPERTIES, *_CATEGORY_PROPERTIES, *_BOOLEAN_PROPERTIES):
    for _axis in _axes:
        DafWidgets.register_properties(axis=_axis, properties=[_property_class])

for _property_class, _axes in _OTHER_PROPERTIES:
    for _axis in _axes:
        DafWidgets.register_properties(axis=_axis, properties=[_property_class])
