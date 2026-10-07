"""
The ``Daf`` kind of data source: a single ``Daf`` data set of metacells.
"""

from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import metacellsgraphspy as mg
import numpy as np
from dafpy import DafReader
from somegraphspy import PointsGraph
from somegraphspy import VectorDataSinks

from .editors import ArgumentEditor
from .editors import GenePicker
from .editors import NamePicker
from .forms import Branch
from .graphs import GeneGene
from .properties import Block
from .properties import BooleanMask
from .properties import GeneExpression
from .properties import GlobalFlowOrder
from .properties import MeanCellsPerMetacell
from .properties import MeanTotalUMIsPerCell
from .properties import MeanTotalUMIsPerMetacell
from .properties import NCells
from .properties import NMetacells
from .properties import TotalUMIs
from .properties import Type
from .properties import implements
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

    def _gene_mask(self, name: str) -> np.ndarray:
        # The Boolean gene property with the ``name``, or all false if the data set doesn't have it.
        if not self.daf.has_vector("gene", name):
            return np.zeros(len(self.daf.axis_np_vector("gene")), dtype="bool")
        return np.asarray(self.daf.get_np_vector("gene", name), dtype="bool")

    def _has_vectors(self, axis: str, *names: str) -> bool:
        # Whether the ``axis`` exists and has all the vectors with the ``names``.
        return self.daf.has_axis(axis) and all(self.daf.has_vector(axis, name) for name in names)


@implements(Type.exists, DafWidgets)
def _has_type(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "type") and source._has_vectors("type", "color")


@implements(Type.fill, DafWidgets)
def _fill_type(_self: Type, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_type(sinks, source.daf, axis=axis)


@implements(Block.exists, DafWidgets)
def _has_block(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "block")


@implements(Block.fill, DafWidgets)
def _fill_block(_self: Block, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_block(sinks, source.daf, axis=axis)


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
) -> ArgumentEditor:
    return ArgumentEditor(GenePicker(source, None if current is None else current.gene), GeneExpression)


@implements(TotalUMIs.exists, DafWidgets)
def _has_total_umis(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "total_UMIs")


@implements(TotalUMIs.fill, DafWidgets)
def _fill_total_umis(_self: TotalUMIs, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_total_UMIs(sinks, source.daf, axis=axis)


@implements(NCells.exists, DafWidgets)
def _has_n_cells(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "n_cells")


@implements(NCells.fill, DafWidgets)
def _fill_n_cells(_self: NCells, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_n_cells(sinks, source.daf, axis=axis)


@implements(NMetacells.exists, DafWidgets)
def _has_n_metacells(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "n_metacells")


@implements(NMetacells.fill, DafWidgets)
def _fill_n_metacells(_self: NMetacells, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_n_metacells(sinks, source.daf, axis=axis)


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
    mg.fill_boolean_annotation(sinks, source.daf, axis=axis, property=self.name)


@implements(BooleanMask.editor, DafWidgets)
def _boolean_mask_editor(_cls: type, source: DafWidgets, axis: str, current: Optional[BooleanMask]) -> ArgumentEditor:
    current_name = None if current is None else current.name
    return ArgumentEditor(NamePicker(source.boolean_vectors(axis), current_name), BooleanMask)


@implements(GlobalFlowOrder.exists, DafWidgets)
def _has_global_flow_order(_cls: type, source: DafWidgets, axis: str) -> bool:
    return source._has_vectors(axis, "type") and source._has_vectors("type", "global_flow_order")


@implements(GlobalFlowOrder.fill, DafWidgets)
def _fill_global_flow_order(_self: GlobalFlowOrder, source: DafWidgets, sinks: VectorDataSinks, axis: str) -> None:
    mg.fill_global_flow_order(sinks, source.daf, axis=axis)


@implements(GeneGene.exists, DafWidgets)
def _has_gene_gene(_cls: type, source: DafWidgets) -> bool:
    return any(GeneExpression.exists(source, axis) for axis in ("metacell", "block"))


@implements(GeneGene.base_graph, DafWidgets)
def _gene_gene_base_graph(self: GeneGene, source: DafWidgets) -> PointsGraph:
    assert self.x_gene is not None and self.y_gene is not None
    return mg.gene_gene_graph(source.daf, axis=self.axis, x_gene=self.x_gene, y_gene=self.y_gene)


DafWidgets.register_properties(
    axis="metacell",
    properties=[Type, Block, GeneExpression, TotalUMIs, NCells, MeanTotalUMIsPerCell, BooleanMask, GlobalFlowOrder],
)

DafWidgets.register_properties(
    axis="block",
    properties=[
        Type,
        GeneExpression,
        TotalUMIs,
        NCells,
        NMetacells,
        MeanCellsPerMetacell,
        MeanTotalUMIsPerMetacell,
        MeanTotalUMIsPerCell,
        BooleanMask,
        GlobalFlowOrder,
    ],
)
