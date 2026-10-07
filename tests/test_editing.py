"""
Test editing a form, without a kernel: its widgets change its arguments, and the graph is redrawn once per poll.
"""

from typing import Any
from typing import List

import metacellswidgets as mw

from .test_daf_widgets import _full_daf


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
    form._poll_redraw(redraws.append)
    assert not redraws

    form._bound["x_gene"]._combobox.value = "A M R"
    form._poll_redraw(redraws.append)
    assert len(redraws) == 1


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
