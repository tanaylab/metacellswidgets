"""
Test writing the state of a form back into the code of a cell.

Each test runs a cell's code with ``exec``. The code calls a recorder, which captures the positions of its calls from
the running frames, the same way the forms do.
"""

import sys
from typing import Any
from typing import Dict

import numpy as np
import pytest
from dafpy.julia_import import DEFAULT

import metacellswidgets
from metacellswidgets.rewrite import _call_position
from metacellswidgets.rewrite import _Position
from metacellswidgets.rewrite import _python_code
from metacellswidgets.rewrite import _rewritten_cell
from metacellswidgets.rewrite import _rewritten_menu_cell
from metacellswidgets.rewrite import _split_cell_magic

# Non-ASCII text for a cell: a Hebrew string, a Hebrew variable name, and an accented gene name.
_GENE = "\N{HEBREW LETTER GIMEL}\N{HEBREW LETTER FINAL NUN}"  # NOT F-STRING
_CHECK = (
    "\N{HEBREW LETTER LAMED}\N{HEBREW LETTER BET}\N{HEBREW LETTER DALET}"  # NOT F-STRING
    "\N{HEBREW LETTER YOD}\N{HEBREW LETTER QOF}\N{HEBREW LETTER HE}"  # NOT F-STRING
)
_ACCENTED = "\N{LATIN SMALL LETTER E WITH ACUTE}"  # NOT F-STRING


class _Recorder:
    """
    Stands for a form: records where it was created and where it was edited, and where a menu was shown.
    """

    #: Stands for a format of the form's graph, which a cell may name after editing it.
    svg: Any = None

    def __init__(self) -> None:
        self.form_position: _Position | None = None
        self.edit_position: _Position | None = None
        self.menu_position: _Position | None = None

    def menu(self) -> "_Recorder":
        """
        Record the position of this call, as a menu method does.
        """
        self.menu_position = _call_position(sys._getframe(1))  # pylint: disable=protected-access
        return self

    def form(self, *_arguments: Any, **_keywords: Any) -> "_Recorder":
        """
        Record the position of this call, as a form function does.
        """
        self.form_position = _call_position(sys._getframe(1))  # pylint: disable=protected-access
        return self

    def edit(self) -> "_Recorder":
        """
        Record the position of this call, as a form's ``edit`` does.
        """
        self.edit_position = _call_position(sys._getframe(1))  # pylint: disable=protected-access
        return self


class _Shell:
    """
    Stands for IPython, which the code of a line magic calls.
    """

    def run_line_magic(self, *_arguments: Any) -> None:
        """
        Do nothing, as the magics of the tests don't matter.
        """


def _run(source: str, recorder: _Recorder) -> None:
    """
    Run the cell's code as IPython does: a cell magic runs the rest of the cell, and line magics are calls.
    """
    python = _python_code(_split_cell_magic(source)[1])
    globals_of_cell = {"mw": recorder, "daf": None, "get_ipython": _Shell}
    exec(compile(python, "<cell>", "exec"), globals_of_cell)  # pylint: disable=exec-used


def _rewrite(source: str, keywords: Dict[str, Any], **options: Any) -> str:
    """
    Run the cell, then rewrite it with the recorded positions.
    """
    recorder = _Recorder()
    _run(source, recorder)
    assert recorder.form_position is not None
    assert recorder.edit_position is not None
    return _rewritten_cell(
        source,
        form_position=recorder.form_position,
        form_keywords=keywords,
        edit_position=recorder.edit_position,
        **options,
    )


def test_two_lines() -> None:
    """
    The form call and the edit call on separate lines; the rest of the cell, comments included, is kept.
    """
    source = "# The genes.\nform = mw.form(daf, x_gene='A')  # the form\nform.edit()  # show it\nprint(form)\n"
    assert _rewrite(source, {"x_gene": "C", "y_gene": "D"}) == (
        "# The genes.\nform = mw.form(daf, x_gene='C', y_gene='D')  # the form\nform  # show it\nprint(form)\n"
    )


def test_two_lines_with_format() -> None:
    """
    The edit call on its own line, followed by a format, which is kept.
    """
    source = "form = mw.form(daf)\nform.edit().svg\n"
    assert _rewrite(source, {"x_gene": "C"}) == "form = mw.form(daf, x_gene='C')\nform.svg\n"


def test_chained() -> None:
    """
    The edit call chained to the form call, followed by a format, which is kept.
    """
    source = "form = mw.form(daf).edit().svg\n"
    assert _rewrite(source, {"x_gene": "C"}) == "form = mw.form(daf, x_gene='C').svg\n"


def test_multi_line_call() -> None:
    """
    A form call spread over several lines becomes a single line.
    """
    source = "form = mw.form(\n    daf,\n    x_gene='A',\n).edit()\n"
    assert _rewrite(source, {"x_gene": "B"}) == "form = mw.form(daf, x_gene='B')\n"


def test_in_if() -> None:
    """
    Only the calls which ran are rewritten.
    """
    source = (
        "if True:\n"
        "    form = mw.form(daf)\n"
        "    form.edit()\n"
        "else:\n"
        "    form = mw.form(daf, x_gene='Z')\n"
        "    form.edit()\n"
    )
    assert _rewrite(source, {"x_gene": "C"}) == (
        "if True:\n"
        "    form = mw.form(daf, x_gene='C')\n"
        "    form\n"
        "else:\n"
        "    form = mw.form(daf, x_gene='Z')\n"
        "    form.edit()\n"
    )


def test_non_ascii() -> None:
    """
    Positions are in UTF-8 bytes, so text before the calls on the same line doesn't shift them.
    """
    source = f"name = '{_GENE}'; form = mw.form(daf)\n{_CHECK} = form.edit()\n"
    assert _rewrite(source, {"x_gene": _ACCENTED}) == (
        f"name = '{_GENE}'; form = mw.form(daf, x_gene='{_ACCENTED}')\n{_CHECK} = form\n"
    )


def test_cell_magic_is_kept() -> None:
    """
    A cell magic which runs the rest of the cell is kept, and the calls are found in the rest of the cell.
    """
    source = "%%time\nform = mw.form(daf)\nform.edit()\n"
    assert _rewrite(source, {"x_gene": "C"}) == "%%time\nform = mw.form(daf, x_gene='C')\nform\n"


def test_line_magics_are_kept() -> None:
    """
    Line magics on other lines are kept as written, not as the calls IPython runs them as.
    """
    source = "%env SOME_VARIABLE=1\nform = mw.form(daf)\nform.edit()\n"
    assert _rewrite(source, {"x_gene": "C"}) == "%env SOME_VARIABLE=1\nform = mw.form(daf, x_gene='C')\nform\n"


def test_menu() -> None:
    """
    A menu call becomes the call of the chosen form on the same receiver, and the format after it is kept.
    """
    source = "# The menu.\nform = mw.form(daf).menu().svg  # chosen\n"
    recorder = _Recorder()
    exec(compile(source, "<cell>", "exec"), {"mw": recorder, "daf": None})  # pylint: disable=exec-used
    assert recorder.menu_position is not None
    rewritten = _rewritten_menu_cell(
        source,
        menu_position=recorder.menu_position,
        method="gene_gene",
        form_keywords={"x_gene": "A", "colors": DEFAULT},
    )
    assert rewritten == "# The menu.\nform = mw.form(daf).gene_gene(x_gene='A').svg  # chosen\n"


def test_default_values_are_left_out() -> None:
    """
    A keyword whose value is ``DEFAULT`` is left to its default, and one whose value is ``None`` is written (the form
    leaves out a ``None`` which is its parameter's default).
    """
    source = "form = mw.form(daf, selected_box=(1, 2, 3, 4))\nform.edit()\n"
    keywords = {"x_gene": "C", "selected_box": DEFAULT, "log_base": None}
    assert _rewrite(source, keywords) == "form = mw.form(daf, x_gene='C', log_base=None)\nform\n"


def test_selection_values() -> None:
    """
    Tuples and lists of numbers are written as literals.
    """
    source = "form = mw.form(daf)\nform.edit()\n"
    keywords = {"selected_box": (-9.0, -7.0, -9.0, -7.0), "selected_lasso": [(1.0, 2.0), (3.0, 4.0)]}
    assert _rewrite(source, keywords) == (
        "form = mw.form(daf, selected_box=(-9.0, -7.0, -9.0, -7.0), selected_lasso=[(1.0, 2.0), (3.0, 4.0)])\n" "form\n"
    )


def test_new_method() -> None:
    """
    The form call's method can be replaced on the same receiver, when the editor switched to another graph.
    """
    source = "form = mw.form(daf)\nform.edit()\n"
    assert _rewrite(source, {"x_gene": "C"}, form_method="other_form") == (
        "form = mw.other_form(daf, x_gene='C')\nform\n"
    )


def test_loop_is_refused() -> None:
    """
    A call inside a loop may run more than once, so it can't be rewritten.
    """
    source = "for gene in ['A']:\n    form = mw.form(daf, x_gene=gene)\n    form.edit()\n"
    with pytest.raises(RuntimeError, match="must not be inside a For"):
        _rewrite(source, {"x_gene": "C"})


def test_comprehension_is_refused() -> None:
    """
    A call inside a comprehension may run more than once, so it can't be rewritten.
    """
    source = "forms = [mw.form(daf, x_gene=gene).edit() for gene in ['A']]\n"
    with pytest.raises(RuntimeError, match="must not be inside a ListComp"):
        _rewrite(source, {"x_gene": "C"})


def test_non_literal_value_is_refused() -> None:
    """
    A value whose code doesn't read back as the same value can't be written into the cell.
    """
    source = "form = mw.form(daf)\nform.edit()\n"
    with pytest.raises(TypeError, match="can't be written as a Python literal"):
        _rewrite(source, {"x_gene": np.float32(1.5)})


def test_properties_through_module() -> None:
    """
    Properties are written by their code, naming their classes through the name the notebook bound to their module.
    """
    source = "form = mw.form(daf)\nform.edit()\n"
    keywords = {"colors": metacellswidgets.GeneExpression("A"), "sizes": metacellswidgets.NCells()}
    namespace = {"_": metacellswidgets.GeneExpression, "mw": metacellswidgets}
    assert _rewrite(source, keywords, namespace=namespace) == (
        "form = mw.form(daf, colors=mw.GeneExpression(gene='A'), sizes=mw.NCells())\nform\n"
    )


def test_properties_through_class() -> None:
    """
    A class the notebook bound to a name is written by that name.
    """
    source = "form = mw.form(daf)\nform.edit()\n"
    namespace = {"GeneExpression": metacellswidgets.GeneExpression, "mw": metacellswidgets}
    assert _rewrite(source, {"colors": metacellswidgets.GeneExpression("A")}, namespace=namespace) == (
        "form = mw.form(daf, colors=GeneExpression(gene='A'))\nform\n"
    )


def test_lists() -> None:
    """
    A list is written item by item, so it may hold objects written by their code (e.g. tweaks).
    """
    source = "form = mw.form(daf)\nform.edit()\n"
    keywords = {
        "genes": ["A", "B"],
        "tweaks": [metacellswidgets.NCells(), metacellswidgets.GeneExpression("A")],
        "empty": [],
    }
    assert _rewrite(source, keywords, namespace={"mw": metacellswidgets}) == (
        "form = mw.form(daf, genes=['A', 'B'], tweaks=[mw.NCells(), mw.GeneExpression(gene='A')], empty=[])\nform\n"
    )


def test_properties_without_name() -> None:
    """
    A property whose class the notebook has no name for can't be written into the cell.
    """
    source = "form = mw.form(daf)\nform.edit()\n"
    with pytest.raises(RuntimeError, match="no name for it .e.g. use: import metacellswidgets as"):
        _rewrite(source, {"colors": metacellswidgets.Type()}, namespace={"_": metacellswidgets})
