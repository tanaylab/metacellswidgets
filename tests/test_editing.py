"""
Test editing a form, without a kernel: its widgets change its arguments, and the graph is redrawn once per poll.
"""

import time
from typing import Any
from typing import List

from plotly.graph_objects import FigureWidget  # type: ignore

import metacellswidgets as mw
from metacellswidgets.forms import _EditSession
from metacellswidgets.forms import _replace_figure

from .test_daf_widgets import _full_daf


def test_figure_follows_its_width() -> None:
    """
    The editor starts without the form's editors and figure, which its first poll makes and draws (showing its spinner
    first). A shown figure waits for its width watcher to report a width (the editor shows its spinner meanwhile). Each
    width it reports makes the figure measure its box again. If none arrives in time, the editor reports that the
    watcher failed and stops waiting.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B")
    session = _EditSession(form.source, form)
    assert session._spinner.layout.visibility is None
    assert not session._body.children
    assert not session._poll_width()
    session._show_form()
    assert session._body.children
    assert form._is_redraw_due()
    form._poll_redraw(session._redraw)
    assert session._poll_width()
    assert session._figure is not None
    session._figure.layout.autosize = None
    session._width_watcher.width = 1000
    assert not session._poll_width()
    assert session._figure.layout.autosize is True

    session = _EditSession(form.source, form)
    session._show_form()
    form._poll_redraw(session._redraw)
    assert session._poll_width()
    session._unmeasured_since = time.monotonic() - 60
    assert not session._poll_width()
    assert session._has_width_failed
    assert not session._poll_width()


def test_redraw_keeps_the_full_width() -> None:
    """
    Redrawing the figure keeps it as wide as the cell: replacing its layout doesn't drop its ``autosize``.
    """
    widget = FigureWidget()
    widget.layout.autosize = True
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B")
    _replace_figure(widget, form.fig)
    assert widget.layout.autosize is True


def _form_and_redraws() -> Any:
    """
    A gene-gene form with its editor, and a list collecting its redrawn graphs.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(x_gene="A", y_gene="B", colors=mw.GeneExpression("D"))
    form.editor()
    redraws: List[Any] = []
    return form, redraws


def test_edit() -> None:
    """
    Changing a widget changes its argument, and the next poll redraws the graph once.
    """
    form, redraws = _form_and_redraws()
    form._poll_redraw(redraws.append)
    assert not redraws

    form._bound["y_gene"]._combobox.value = "D M"
    # Gene B isn't a marker, so it is offered only once the choices aren't restricted to the markers.
    form._bound["x_gene"]._markers_only._dropdown.index = 1
    form._bound["x_gene"]._combobox.value = "B L"
    assert form.y_gene == "D"
    assert form.x_gene == "B"
    form._poll_redraw(redraws.append)
    assert len(redraws) == 1
    form._poll_redraw(redraws.append)
    assert len(redraws) == 1


def test_hold_redraw() -> None:
    """
    While held, the graph is not redrawn; once released, the pending request redraws it.
    """
    form, redraws = _form_and_redraws()
    with form.hold_redraw():
        form._bound["x_gene"]._combobox.value = "D M"
        form._poll_redraw(redraws.append)
        assert not redraws
    form._poll_redraw(redraws.append)
    assert len(redraws) == 1


def test_incomplete() -> None:
    """
    A missing gene leaves the graph undrawn; missing sizes don't.
    """
    form, redraws = _form_and_redraws()
    assert form.sizes is None
    assert form.is_complete()

    form._bound["x_gene"]._combobox.value = ""
    assert form.x_gene is None
    assert not form.is_complete()
    # A redraw isn't due while the form is incomplete, so the editor shows no busy spinner either.
    assert not form._is_redraw_due()
    form._poll_redraw(redraws.append)
    assert not redraws

    form._bound["x_gene"]._combobox.value = "A M R"
    assert form._is_redraw_due()
    form._poll_redraw(redraws.append)
    assert len(redraws) == 1
    assert not form._is_redraw_due()


def test_axis() -> None:
    """
    Switching the axis keeps the colors of the gene expression, and the graph is of the new axis.
    """
    form, redraws = _form_and_redraws()
    form._bound["axis"]._dropdown.value = "block"
    assert form.axis == "block"
    assert form.colors == mw.GeneExpression("D")
    form._poll_redraw(redraws.append)
    assert len(redraws) == 1
    assert list(redraws[0].data.points.entities.names) == ["B1", "B2"]
