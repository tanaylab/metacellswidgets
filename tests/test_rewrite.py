"""
Test writing the state of a form back into the code of a cell.

Each test runs a cell's code with ``exec``. The code calls a recorder, which captures the positions of its calls from
the running frames, the same way the forms do.
"""

import sys
from typing import Any
from typing import Dict
from typing import Optional

import numpy as np
import pytest

import metacellswidgets
from metacellswidgets.rewrite import _call_position
from metacellswidgets.rewrite import _Position
from metacellswidgets.rewrite import _rewritten_cell


class _Recorder:
    """
    Stands for a form: records where it was created and where it was displayed.
    """

    def __init__(self) -> None:
        self.form_position: Optional[_Position] = None
        self.display_position: Optional[_Position] = None

    def form(self, *_arguments: Any, **_keywords: Any) -> "_Recorder":
        """
        Record the position of this call, as a form function does.
        """
        self.form_position = _call_position(sys._getframe(1))  # pylint: disable=protected-access
        return self

    def display(self, **_keywords: Any) -> "_Recorder":
        """
        Record the position of this call, as a form's ``display`` does.
        """
        self.display_position = _call_position(sys._getframe(1))  # pylint: disable=protected-access
        return self


def _rewrite(source: str, keywords: Dict[str, Any], *, is_interactive: bool = False, **options: Any) -> str:
    """
    Run the cell, then rewrite it with the recorded positions.
    """
    recorder = _Recorder()
    exec(compile(source, "<cell>", "exec"), {"mw": recorder, "daf": None})  # pylint: disable=exec-used
    assert recorder.form_position is not None
    assert recorder.display_position is not None
    return _rewritten_cell(
        source,
        form_position=recorder.form_position,
        form_keywords=keywords,
        display_position=recorder.display_position,
        is_interactive=is_interactive,
        **options,
    )


def test_two_lines() -> None:
    """
    The form call and the display call on separate lines; the rest of the cell, comments included, is kept.
    """
    source = (
        "# The genes.\n"
        "form = mw.form(daf, x_gene='A')  # the form\n"
        "form.display(interactive=True)  # show it\n"
        "print(form)\n"
    )
    assert _rewrite(source, {"x_gene": "C", "y_gene": "D"}) == (
        "# The genes.\n"
        "form = mw.form(daf, x_gene='C', y_gene='D')  # the form\n"
        "form.display(interactive=False)  # show it\n"
        "print(form)\n"
    )


def test_chained() -> None:
    """
    The display call chained to the form call.
    """
    source = "form = mw.form(daf).display(interactive=True)\n"
    assert _rewrite(source, {"x_gene": "C"}) == "form = mw.form(daf, x_gene='C').display(interactive=False)\n"


def test_multi_line_call() -> None:
    """
    A form call spread over several lines becomes a single line.
    """
    source = "form = mw.form(\n    daf,\n    x_gene='A',\n)\nform.display(interactive=True)\n"
    assert _rewrite(source, {"x_gene": "B"}) == "form = mw.form(daf, x_gene='B')\nform.display(interactive=False)\n"


def test_in_if() -> None:
    """
    Only the calls which ran are rewritten.
    """
    source = (
        "if True:\n"
        "    form = mw.form(daf)\n"
        "    form.display(interactive=True)\n"
        "else:\n"
        "    form = mw.form(daf, x_gene='Z')\n"
        "    form.display(interactive=True)\n"
    )
    assert _rewrite(source, {"x_gene": "C"}) == (
        "if True:\n"
        "    form = mw.form(daf, x_gene='C')\n"
        "    form.display(interactive=False)\n"
        "else:\n"
        "    form = mw.form(daf, x_gene='Z')\n"
        "    form.display(interactive=True)\n"
    )


def test_non_ascii() -> None:
    """
    Positions are in UTF-8 bytes, so text before the calls on the same line doesn't shift them.
    """
    source = "name = 'גן'; form = mw.form(daf)\nלבדיקה = form.display(interactive=True)\n"
    assert _rewrite(source, {"x_gene": "é"}) == (
        "name = 'גן'; form = mw.form(daf, x_gene='é')\nלבדיקה = form.display(interactive=False)\n"
    )


def test_none_values_are_left_out() -> None:
    """
    A keyword whose value is ``None`` is left to its default.
    """
    source = "form = mw.form(daf, selected_box=(1, 2, 3, 4))\nform.display(interactive=True)\n"
    assert _rewrite(source, {"x_gene": "C", "selected_box": None}) == (
        "form = mw.form(daf, x_gene='C')\nform.display(interactive=False)\n"
    )


def test_selection_values() -> None:
    """
    Tuples and lists of numbers are written as literals.
    """
    source = "form = mw.form(daf)\nform.display(interactive=True)\n"
    keywords = {"selected_box": (-9.0, -7.0, -9.0, -7.0), "selected_lasso": [(1.0, 2.0), (3.0, 4.0)]}
    assert _rewrite(source, keywords) == (
        "form = mw.form(daf, selected_box=(-9.0, -7.0, -9.0, -7.0), selected_lasso=[(1.0, 2.0), (3.0, 4.0)])\n"
        "form.display(interactive=False)\n"
    )


def test_back_to_interactive() -> None:
    """
    The same rewrite turns a static display into an interactive one, which is what "Edit" does.
    """
    source = "form = mw.form(daf, x_gene='C')\nform.display(interactive=False)\n"
    assert _rewrite(source, {"x_gene": "C"}, is_interactive=True) == (
        "form = mw.form(daf, x_gene='C')\nform.display(interactive=True)\n"
    )


def test_other_display_keywords_are_kept() -> None:
    """
    Keyword arguments of the display call other than ``interactive`` are kept as written.
    """
    source = "form = mw.form(daf)\nform.display(format = 'svg', interactive=True)\n"
    assert (
        _rewrite(source, {"x_gene": "C"})
        == "form = mw.form(daf, x_gene='C')\nform.display(format='svg', interactive=False)\n"
    )


def test_new_callee() -> None:
    """
    The form call's callee can be replaced, when a menu picked another graph.
    """
    source = "form = mw.form(daf)\nform.display(interactive=True)\n"
    assert _rewrite(source, {"x_gene": "C"}, form_callee="mw.other_form") == (
        "form = mw.other_form(daf, x_gene='C')\nform.display(interactive=False)\n"
    )


def test_loop_is_refused() -> None:
    """
    A call inside a loop may run more than once, so it can't be rewritten.
    """
    source = "for gene in ['A']:\n    form = mw.form(daf, x_gene=gene)\n    form.display(interactive=True)\n"
    with pytest.raises(RuntimeError, match="must not be inside a For"):
        _rewrite(source, {"x_gene": "C"})


def test_comprehension_is_refused() -> None:
    """
    A call inside a comprehension may run more than once, so it can't be rewritten.
    """
    source = "forms = [mw.form(daf, x_gene=gene).display(interactive=True) for gene in ['A']]\n"
    with pytest.raises(RuntimeError, match="must not be inside a ListComp"):
        _rewrite(source, {"x_gene": "C"})


def test_non_literal_value_is_refused() -> None:
    """
    A value whose code doesn't read back as the same value can't be written into the cell.
    """
    source = "form = mw.form(daf)\nform.display(interactive=True)\n"
    with pytest.raises(TypeError, match="can't be written as a Python literal"):
        _rewrite(source, {"x_gene": np.float32(1.5)})


def test_properties_through_module() -> None:
    """
    Properties are written by their code, naming their classes through the name the notebook bound to their module.
    """
    source = "form = mw.form(daf)\nform.display(interactive=True)\n"
    keywords = {"colors": metacellswidgets.GeneExpression("A"), "sizes": metacellswidgets.NCells()}
    namespace = {"_": metacellswidgets.GeneExpression, "mw": metacellswidgets}
    assert _rewrite(source, keywords, namespace=namespace) == (
        "form = mw.form(daf, colors=mw.GeneExpression(gene='A'), sizes=mw.NCells())\nform.display(interactive=False)\n"
    )


def test_properties_through_class() -> None:
    """
    A class the notebook bound to a name is written by that name.
    """
    source = "form = mw.form(daf)\nform.display(interactive=True)\n"
    namespace = {"GeneExpression": metacellswidgets.GeneExpression, "mw": metacellswidgets}
    assert _rewrite(source, {"colors": metacellswidgets.GeneExpression("A")}, namespace=namespace) == (
        "form = mw.form(daf, colors=GeneExpression(gene='A'))\nform.display(interactive=False)\n"
    )


def test_lists() -> None:
    """
    A list is written item by item, so it may hold objects written by their code (e.g. tweaks).
    """
    source = "form = mw.form(daf)\nform.display(interactive=True)\n"
    keywords = {
        "genes": ["A", "B"],
        "tweaks": [metacellswidgets.NCells(), metacellswidgets.GeneExpression("A")],
        "empty": [],
    }
    assert _rewrite(source, keywords, namespace={"mw": metacellswidgets}) == (
        "form = mw.form(daf, genes=['A', 'B'], tweaks=[mw.NCells(), mw.GeneExpression(gene='A')], empty=[])\n"
        "form.display(interactive=False)\n"
    )


def test_properties_without_name() -> None:
    """
    A property whose class the notebook has no name for can't be written into the cell.
    """
    source = "form = mw.form(daf)\nform.display(interactive=True)\n"
    with pytest.raises(RuntimeError, match="no name for it .e.g. use: import metacellswidgets as"):
        _rewrite(source, {"colors": metacellswidgets.Type()}, namespace={"_": metacellswidgets})
