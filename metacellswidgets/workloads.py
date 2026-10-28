"""
Make the calls of a typical session (for internal use).

The Julia package ``MetacellsWidgetsPy`` runs this while it is precompiled, so the code these calls compile is cached,
and a session does not compile it again. It is not part of the API, so the package does not import it.
"""

import os
from tempfile import TemporaryDirectory

import dafpy as dp
import metacellsgraphspy as mg
import numpy as np
import pandas as pd
from anndata import AnnData  # type: ignore

from .anndata_widgets import AnnDataWidgets
from .daf_widgets import DafWidgets
from .forms import GraphForm

__all__ = ["run_workload"]


def run_workload() -> None:
    """
    Make the calls of a typical session, showing each graph form of a small fixed ``daf`` chain and ``AnnData``, on
    each of its axes, and its editor (for internal use).
    """
    with TemporaryDirectory() as directory:
        _run_daf_workload(directory)
        _run_anndata_workload(directory)


def _show(form: GraphForm) -> None:
    # What displaying a form does, and what displaying it interactively adds.
    _ = form.graph().figure
    form.editor()


def _run_daf_workload(directory: str) -> None:
    # The repositories of ``MetacellsGraphs``' own workload, opened as a notebook opens them.
    mg.jl.MetacellsGraphs.Workloads.write_workload_daf(directory)
    source = DafWidgets(dp.complete_daf(os.path.join(directory, "top")))
    for axis in ("metacell", "block"):
        _show(source.gene_gene(axis=axis, x_gene="A", y_gene="B"))
        _show(source.genes_heatmap(axis=axis))


def _run_anndata_workload(directory: str) -> None:
    # A metacells ``AnnData`` in the Python metacells layout, with a metacell of no type.
    adata = AnnData(
        X=np.array(
            [[0.1, 0.4, 0.0, 0.2], [0.2, 0.3, 0.1, 0.2], [0.3, 0.2, 0.0, 0.2], [0.4, 0.1, 0.1, 0.2]], dtype="float32"
        ),
        obs=pd.DataFrame(
            {
                "cell_type": pd.Categorical(["T1", "T1", "T2", None]),
                "total_umis": np.array([100, 200, 300, 400], dtype="float32"),
                "x": np.array([0, 1, 2, 3], dtype="float32"),
                "y": np.array([3, 2, 1, 0], dtype="float32"),
            },
            index=["M1", "M2", "M3", "M4"],
        ),
        var=pd.DataFrame(
            {
                "lateral_gene": [False, True, False, False],
                "excluded_gene": [False, False, False, True],
                "marker_gene": [True, True, True, False],
            },
            index=["A", "B", "C", "D"],
        ),
    )
    type_colors_csv = os.path.join(directory, "type_colors.csv")
    with open(type_colors_csv, "w", encoding="utf8") as file:
        file.write("type,color\nT1,red\nT2,blue\n")

    source = AnnDataWidgets(adata, type_property="cell_type", type_colors_csv=type_colors_csv)
    _show(source.gene_gene(x_gene="A", y_gene="B"))
    _show(source.genes_heatmap())
