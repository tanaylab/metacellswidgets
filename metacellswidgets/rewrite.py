"""
Write the state of a form back into the code of the cell that runs it.

A form records where in its cell it was created. When an interactive display is done, the cell's code is rewritten: the
form call gets the form's state as keyword arguments, and the display call gets ``interactive=False``. The rest of the
cell is kept as written. The new code reaches the notebook through IPython's ``set_next_input(..., replace=True)``,
which only works while the cell runs.

Calls are found by their position, which Python reports for the running code of the cell. So the functions may be
called under any name. Positions are (line, end line, column, end column), with 1-based lines and 0-based columns in
UTF-8 bytes, as both ``ast`` and ``co_positions`` report them.
"""

import ast
from dataclasses import dataclass
from types import FrameType
from types import ModuleType
from typing import Any
from typing import List
from typing import Mapping
from typing import Optional
from typing import Tuple

from IPython import get_ipython

__all__: List[str] = []

_Position = Tuple[int, int, int, int]


@dataclass(frozen=True)
class _CallSite:
    # Where a call was made: which run of which cell (``_current_cell_token``), and its position in the cell's code.
    cell_token: int
    position: _Position


def _current_cell_token() -> int:
    # Identifies the running cell. This is the length of IPython's input history, which grows by one for each cell run.
    return len(get_ipython().user_ns["In"])


def _current_cell_source() -> str:
    # The code of the running cell.
    return get_ipython().user_ns["In"][-1]


def _call_position(frame: FrameType) -> _Position:
    # The position of the call running in the frame.
    positions = list(frame.f_code.co_positions())
    line, end_line, column, end_column = positions[frame.f_lasti // 2]
    assert line is not None and end_line is not None and column is not None and end_column is not None
    return (line, end_line, column, end_column)


def _cell_site(frame: FrameType) -> Optional[_CallSite]:
    # Where the call running in the frame was made, if the frame is the top level code of the running cell. Otherwise
    # (outside IPython, or in a function the cell calls), ``None``.
    shell = get_ipython()
    if shell is None or frame.f_code.co_name != "<module>" or frame.f_globals is not shell.user_ns:
        return None
    return _CallSite(cell_token=_current_cell_token(), position=_call_position(frame))


_REWRITTEN_CELL_TOKEN: Optional[int] = None


def _claim_cell_rewrite() -> None:
    # Claim the rewrite of the running cell. A cell run can rewrite its code once, because only the last
    # ``set_next_input`` of a run takes effect.
    global _REWRITTEN_CELL_TOKEN  # pylint: disable=global-statement
    cell_token = _current_cell_token()
    if _REWRITTEN_CELL_TOKEN == cell_token:
        raise RuntimeError("a cell can display only one form interactively each time it runs")
    _REWRITTEN_CELL_TOKEN = cell_token


def _node_position(node: ast.AST) -> _Position:
    # The position of an ``ast`` node.
    assert isinstance(node, (ast.expr, ast.stmt))
    assert node.end_lineno is not None and node.end_col_offset is not None
    return (node.lineno, node.end_lineno, node.col_offset, node.end_col_offset)


# Code under these nodes may run more than once, or not directly from the cell, so its arguments can't be replaced by
# the values of a single run.
_REPEATED_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
)


def _top_level_call(tree: ast.Module, position: _Position, what: str) -> ast.Call:
    # The call at the position, which must not be inside a loop, comprehension, function, lambda or class.
    path = _path_to_call(tree, position)
    if path is None:
        raise RuntimeError(f"can't find the {what} call in the cell's code")
    for node in path:
        if isinstance(node, _REPEATED_NODES):
            raise RuntimeError(
                f"an interactive form's {what} call must not be inside a {type(node).__name__} (it may run more than once)"
            )
    call = path[-1]
    assert isinstance(call, ast.Call)
    return call


def _path_to_call(node: ast.AST, position: _Position) -> Optional[List[ast.AST]]:
    # The nodes from ``node`` down to the call at the position.
    if isinstance(node, ast.Call) and _node_position(node) == position:
        return [node]
    for child in ast.iter_child_nodes(node):
        path = _path_to_call(child, position)
        if path is not None:
            return [node] + path
    return None


def _segment(source: str, node: ast.AST) -> str:
    # The code of an ``ast`` node, as written in the source.
    text = ast.get_source_segment(source, node)
    assert text is not None
    return text


def _callee_of(cls: type, namespace: Mapping[str, Any]) -> str:
    # The code naming the class in the namespace of the cell: a name bound to the class, or to a module which has it
    # (e.g. ``mw.GeneExpression``). Names starting with ``_`` are skipped, since IPython binds them to recent outputs.
    names = [name for name in namespace if not name.startswith("_")]
    for name in names:
        if namespace[name] is cls:
            return name
    for name in names:
        value = namespace[name]
        if isinstance(value, ModuleType) and getattr(value, cls.__name__, None) is cls:
            return f"{name}.{cls.__name__}"
    package = cls.__module__.split(".")[0]
    raise RuntimeError(
        f"can't write the class: {cls.__name__} into the code of the cell, "
        f"because the notebook has no name for it (e.g. use: import {package} as ...)"
    )


def _literal_text(name: str, value: Any, namespace: Optional[Mapping[str, Any]] = None) -> str:
    # The code of a value, which must read back as the same value. An object with a ``code`` method (e.g. a property)
    # is written by it, naming its class as the namespace does.
    code = getattr(value, "code", None)
    if callable(code) and namespace is not None:
        return code(_callee_of(type(value), namespace), namespace)
    text = repr(value)
    try:
        is_literal = ast.literal_eval(text) == value
    except (ValueError, SyntaxError):
        is_literal = False
    if not is_literal:
        raise TypeError(f"the value of {name} can't be written as a Python literal: {text}")
    return text


def _rewritten_cell(
    source: str,
    *,
    form_position: _Position,
    form_keywords: Mapping[str, Any],
    display_position: _Position,
    is_interactive: bool,
    form_callee: Optional[str] = None,
    namespace: Optional[Mapping[str, Any]] = None,
) -> str:
    # The code of the cell with the form call's keyword arguments set to ``form_keywords`` (leaving out those which are
    # ``None``), its callee replaced by ``form_callee`` (if given), and the display call's ``interactive`` set to
    # ``is_interactive``. The form call may be on another line than the display call, or chained to it. Values with a
    # ``code`` method (e.g. properties) name their classes as the cell's ``namespace`` does.
    tree = ast.parse(source)
    form_call = _top_level_call(tree, form_position, "form")
    display_call = _top_level_call(tree, display_position, "display")

    if form_callee is None:
        form_callee = _segment(source, form_call.func)
    form_arguments = [_segment(source, argument) for argument in form_call.args]
    form_arguments += [
        f"{name}={_literal_text(name, value, namespace)}" for name, value in form_keywords.items() if value is not None
    ]
    form_text = f"{form_callee}({', '.join(form_arguments)})"

    display_arguments = [_segment(source, argument) for argument in display_call.args]
    display_arguments += [
        f"{keyword.arg}={_segment(source, keyword.value)}"
        for keyword in display_call.keywords
        if keyword.arg != "interactive"
    ]
    display_arguments.append(f"interactive={is_interactive}")
    display_arguments_text = f"({', '.join(display_arguments)})"

    # Replace the later span first, so the earlier span's offsets stay valid. The display call's arguments come after the
    # whole form call, even when the two are chained.
    source_bytes = source.encode("utf-8")
    line_offsets = [0]
    for line in source_bytes.split(b"\n")[:-1]:
        line_offsets.append(line_offsets[-1] + len(line) + 1)

    def offset(line: int, column: int) -> int:
        return line_offsets[line - 1] + column

    _, display_end_line, _, display_end_column = _node_position(display_call)
    _, func_end_line, _, func_end_column = _node_position(display_call.func)
    form_line, form_end_line, form_column, form_end_column = _node_position(form_call)
    replacements = [
        (
            offset(func_end_line, func_end_column),
            offset(display_end_line, display_end_column),
            display_arguments_text,
        ),
        (offset(form_line, form_column), offset(form_end_line, form_end_column), form_text),
    ]
    for start, end, text in sorted(replacements, reverse=True):
        source_bytes = source_bytes[:start] + text.encode("utf-8") + source_bytes[end:]
    return source_bytes.decode("utf-8")
