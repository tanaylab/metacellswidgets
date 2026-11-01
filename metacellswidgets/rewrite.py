"""
Write the state of a form back into the code of the cell that runs it.

A form records where in its cell it was created. When editing it is done, the cell's code is rewritten: the form call
gets the form's state as keyword arguments, and the edit call is removed (``form.edit()`` becomes ``form``). A menu call
is replaced by the call of the chosen form. The rest of the cell is kept as written.
The new code reaches the notebook through IPython's ``set_next_input(..., replace=True)``, which only works while the
cell runs.

Calls are found by their position, which Python reports for the running code of the cell. So the functions may be
called under any name. Positions are (line, end line, column, end column), with 1-based lines and 0-based columns in
UTF-8 bytes, as both ``ast`` and ``co_positions`` report them.

The cell's magics are kept as written. A cell may start with the ``%%time`` or ``%%capture`` magic, which runs the rest
of the cell once; the positions are then in the rest. Any other cell magic, or a line magic around a form's call, is an
error which names the magic, since the cell's code can't be rewritten under it.
"""

import ast
import re
from dataclasses import dataclass
from enum import Enum
from types import FrameType
from types import ModuleType
from typing import Any
from typing import List
from typing import Mapping
from typing import Tuple

from dafpy.julia_import import DefaultValue
from IPython import get_ipython
from IPython.core.inputtransformer2 import TransformerManager

__all__: List[str] = []

_Position = Tuple[int, int, int, int]


@dataclass(frozen=True)
class _CallSite:
    # Where a call was made: which run of which cell (``_current_cell_token``), and its position in the cell's code.
    # Whether the code was compiled by a magic (e.g. ``%%time``), rather than as the cell itself.
    cell_token: int
    position: _Position
    is_in_magic: bool


# The cell magics an interactive form may run under. Each runs the rest of the cell once, in the notebook's namespace.
_SUPPORTED_CELL_MAGICS = frozenset(["capture", "time"])


def _current_cell_token() -> int:
    # Identifies the running cell. This is the length of IPython's input history, which grows by one for each cell run.
    return len(get_ipython().user_ns["In"])


def _current_cell_source() -> str:
    # The code of the running cell, as written, with its magics.
    return get_ipython().history_manager.input_hist_raw[-1]


def _split_cell_magic(source: str) -> Tuple[str, str]:
    # The cell magic line of the code of a cell, with its line break (or "" if it has none), and the rest of the code.
    # The positions of the calls are in the rest.
    if source.startswith("%%"):
        magic_line, _, code = source.partition("\n")
        return magic_line + "\n", code
    return "", source


def _python_code(code: str) -> str:
    # The code as Python runs it. IPython replaces each line magic by a call on the same line, so every other line is
    # as written.
    return TransformerManager().transform_cell(code)


def _check_cell_rewrite(*call_sites: _CallSite | None) -> None:
    # Raise an error naming the magic, if a magic prevents rewriting the running cell's code at the call sites. Outside
    # IPython there is no cell, and so no magic.
    if get_ipython() is None:
        return
    magic_line, code = _split_cell_magic(_current_cell_source())
    if magic_line:
        name = magic_line[2:].split(maxsplit=1)[0]
        if name == "timeit":
            raise RuntimeError(
                "an interactive form can't be used in a cell run by the %%timeit magic, "
                "because that magic runs the cell more than once"
            )
        if name not in _SUPPORTED_CELL_MAGICS:
            raise RuntimeError(
                f"an interactive form can't be used in a cell run by the %%{name} magic, which isn't supported"
            )
    elif any(call_site is not None and call_site.is_in_magic for call_site in call_sites):
        names = " or ".join(f"%{name}" for name in sorted(set(re.findall(r"^\s*%(\w+)", code, re.MULTILINE))))
        raise RuntimeError(
            f"an interactive form can't be created inside the {names} line magic, "
            "because the cell's code then can't be rewritten"
        )


def _call_position(frame: FrameType) -> _Position:
    # The position of the call running in the frame.
    positions = list(frame.f_code.co_positions())
    line, end_line, column, end_column = positions[frame.f_lasti // 2]
    assert line is not None and end_line is not None and column is not None and end_column is not None
    return (line, end_line, column, end_column)


def _cell_site(frame: FrameType) -> _CallSite | None:
    # Where the call running in the frame was made, if the frame is the top level code of the running cell. Otherwise
    # (outside IPython, or in a function the cell calls), ``None``.
    shell = get_ipython()
    if shell is None or frame.f_code.co_name != "<module>" or frame.f_globals is not shell.user_ns:
        return None
    return _CallSite(
        cell_token=_current_cell_token(),
        position=_call_position(frame),
        is_in_magic=frame.f_code.co_filename.startswith("<"),
    )


_REWRITTEN_CELL_TOKEN: int | None = None


def _claim_cell_rewrite() -> None:
    # Claim the rewrite of the running cell. A cell run can rewrite its code once, because only the last
    # ``set_next_input`` of a run takes effect.
    global _REWRITTEN_CELL_TOKEN  # pylint: disable=global-statement
    cell_token = _current_cell_token()
    if _REWRITTEN_CELL_TOKEN == cell_token:
        raise RuntimeError("a cell can edit only one form each time it runs")
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


def _path_to_call(node: ast.AST, position: _Position) -> List[ast.AST] | None:
    # The nodes from ``node`` down to the call at the position. Only the ends are compared. Python starts a method call
    # spread over several lines at its method's name (e.g. ``.edit()`` after a multi-line form call), but ``ast`` starts
    # it at its receiver. No two calls end at the same place, since a call ends after any call inside it.
    if isinstance(node, ast.Call):
        _, node_end_line, _, node_end_column = _node_position(node)
        _, end_line, _, end_column = position
        if (node_end_line, node_end_column) == (end_line, end_column):
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


def _literal_text(name: str, value: Any, namespace: Mapping[str, Any] | None = None) -> str:
    # The code of a value, which must read back as the same value. An object with a ``code`` method (e.g. a property)
    # is written by it, naming its class as the namespace does, or by its bare name if there is no namespace (e.g. for
    # its ``repr``). An enum value is written as its class (named the same way) and its member's name, e.g.
    # ``mw.LogBase.Log2Base``. A list is written item by item, so it may hold such objects (e.g. tweaks).
    if isinstance(value, list):
        return f"[{', '.join(_literal_text(name, item, namespace) for item in value)}]"
    if isinstance(value, Enum):
        enum_class = type(value).__name__ if namespace is None else _callee_of(type(value), namespace)
        return f"{enum_class}.{value.name}"
    code = getattr(value, "code", None)
    if callable(code):
        callee = type(value).__name__ if namespace is None else _callee_of(type(value), namespace)
        return code(callee, namespace)
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
    edit_position: _Position,
    form_method: str | None = None,
    namespace: Mapping[str, Any] | None = None,
) -> str:
    # The code of the cell with the form call's keyword arguments set to ``form_keywords`` (leaving out those which are
    # ``None`` or ``DEFAULT``), its method replaced by ``form_method`` on the same receiver (if given), and the edit call
    # removed (``form.edit()`` becomes ``form``). The form call may be on another line than the edit call, or chained
    # to it. Values with a ``code`` method (e.g. properties) name their classes as the cell's ``namespace`` does. The
    # ``source`` is the cell as written, and its magics are kept as written.
    magic_line, code = _split_cell_magic(source)
    python = _python_code(code)
    tree = ast.parse(python)
    namespace = _cell_namespace(tree, namespace)
    form_call = _top_level_call(tree, form_position, "form")
    edit_call = _top_level_call(tree, edit_position, "edit")
    assert isinstance(edit_call.func, ast.Attribute)

    if form_method is None:
        form_callee = _segment(python, form_call.func)
    else:
        assert isinstance(form_call.func, ast.Attribute)
        form_callee = f"{_segment(python, form_call.func.value)}.{form_method}"
    form_text = _call_text(python, form_call, form_callee, form_keywords, namespace)

    # The edit call is removed from the end of the form it is called on, which is after the whole form call even when
    # the two are chained.
    _, receiver_end_line, _, receiver_end_column = _node_position(edit_call.func.value)
    _, edit_end_line, _, edit_end_column = _node_position(edit_call)
    return magic_line + _replaced(
        code,
        [
            ((receiver_end_line, receiver_end_column, edit_end_line, edit_end_column), ""),
            (_span(form_call), form_text),
        ],
    )


def _rewritten_menu_cell(
    source: str,
    *,
    menu_position: _Position,
    method: str,
    form_keywords: Mapping[str, Any],
    namespace: Mapping[str, Any] | None = None,
) -> str:
    # The code of the cell with the menu call replaced by a call of the ``method`` on the same receiver, with the
    # ``form_keywords`` (leaving out those which are ``None`` or ``DEFAULT``). The ``source`` is the cell as written, and
    # its magics are kept as written.
    magic_line, code = _split_cell_magic(source)
    python = _python_code(code)
    tree = ast.parse(python)
    namespace = _cell_namespace(tree, namespace)
    menu_call = _top_level_call(tree, menu_position, "menu")
    assert isinstance(menu_call.func, ast.Attribute)
    form_callee = f"{_segment(python, menu_call.func.value)}.{method}"
    form_text = _call_text(python, None, form_callee, form_keywords, namespace)
    return magic_line + _replaced(code, [(_span(menu_call), form_text)])


def _cell_namespace(tree: ast.Module, namespace: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    # The ``namespace``, with the names the cell itself uses (e.g. ``mw``) first, so they are preferred for naming
    # classes over other names for the same things.
    if namespace is None:
        return None
    names_in_cell = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    return {**{name: namespace[name] for name in namespace if name in names_in_cell}, **namespace}


def _call_text(
    source: str,
    call: ast.Call | None,
    callee: str,
    keywords: Mapping[str, Any],
    namespace: Mapping[str, Any] | None,
) -> str:
    # The code calling the ``callee`` with the positional arguments of the ``call`` (if any) as written, and the
    # ``keywords`` (leaving out those which are ``None`` or ``DEFAULT``).
    arguments = [] if call is None else [_segment(source, argument) for argument in call.args]
    arguments += [
        f"{name}={_literal_text(name, value, namespace)}"
        for name, value in keywords.items()
        if value is not None and not isinstance(value, DefaultValue)
    ]
    return f"{callee}({', '.join(arguments)})"


def _span(node: ast.AST) -> Tuple[int, int, int, int]:
    # The (line, column, end line, end column) of an ``ast`` node.
    line, end_line, column, end_column = _node_position(node)
    return (line, column, end_line, end_column)


def _replaced(source: str, replacements: List[Tuple[Tuple[int, int, int, int], str]]) -> str:
    # The ``source`` with each span, given as (line, column, end line, end column), replaced by its text. The spans
    # must not overlap. The later ones are replaced first, so the offsets of the earlier ones stay valid.
    source_bytes = source.encode("utf-8")
    line_offsets = [0]
    for line_bytes in source_bytes.split(b"\n")[:-1]:
        line_offsets.append(line_offsets[-1] + len(line_bytes) + 1)
    spans = []
    for (line, column, end_line, end_column), text in replacements:
        spans.append((line_offsets[line - 1] + column, line_offsets[end_line - 1] + end_column, text))
    for start, end, text in sorted(spans, reverse=True):
        source_bytes = source_bytes[:start] + text.encode("utf-8") + source_bytes[end:]
    return source_bytes.decode("utf-8")
