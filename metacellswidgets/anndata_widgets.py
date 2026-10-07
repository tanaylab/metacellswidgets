"""
The ``AnnData`` kind of data source: a metacells ``AnnData`` (e.g., read from an ``h5ad`` file).

Each ``obs`` entry is a metacell, and ``X`` holds the fraction of the UMIs of each metacell in each gene. This kind
is an example for now; it offers only a few properties, of the metacells.
"""

from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import metacellsgraphspy as mg
import numpy as np
from anndata import AnnData  # type: ignore
from somegraphspy import PointsGraph
from somegraphspy import VectorDataSinks

from .editors import ArgumentEditor
from .editors import GenePicker
from .graphs import GeneGene
from .properties import GeneExpression
from .properties import Type
from .properties import implements
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

    def __init__(self, adata: AnnData, *, type_property: str, type_colors_csv: str) -> None:
        self.adata = adata
        self.type_property = type_property
        self.type_colors_csv = type_colors_csv
        self._gene_choices: Dict[bool, List[Tuple[str, str]]] = {}

    def has_axis(self, axis: str) -> bool:
        return axis == "metacell"

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

    def _var_mask(self, column: str) -> np.ndarray:
        # The Boolean ``column`` of ``var``, or all false if there is no such column.
        if column not in self.adata.var:
            return np.zeros(self.adata.n_vars, dtype="bool")
        return np.asarray(self.adata.var[column], dtype="bool")


@implements(Type.exists, AnnDataWidgets)
def _has_type(_cls: type, source: AnnDataWidgets, axis: str) -> bool:
    return axis == "metacell" and source.type_property in source.adata.obs


@implements(Type.fill, AnnDataWidgets)
def _fill_type(_self: Type, source: AnnDataWidgets, sinks: VectorDataSinks, _axis: str) -> None:
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
) -> ArgumentEditor:
    return ArgumentEditor(GenePicker(source, None if current is None else current.gene), GeneExpression)


@implements(GeneGene.exists, AnnDataWidgets)
def _has_gene_gene(_cls: type, _source: AnnDataWidgets) -> bool:
    return True


@implements(GeneGene.base_graph, AnnDataWidgets)
def _gene_gene_base_graph(self: GeneGene, source: AnnDataWidgets) -> PointsGraph:
    assert self.x_gene is not None and self.y_gene is not None
    return mg.ad_gene_gene_graph(source.adata, x_gene=self.x_gene, y_gene=self.y_gene)


AnnDataWidgets.register_properties(axis="metacell", properties=[Type, GeneExpression])
