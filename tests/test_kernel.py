"""
Test letting an editor block its cell while its widgets keep working.

The jobs queue is tested in this process. The rest needs a real kernel, which is started for these tests, with this
checkout first in its ``PYTHONPATH``. Messages are sent to it the way a browser does, but without naming any subshell,
so only the routing done by the package can deliver them to its subshell.
"""

import os
import sys
import threading
import time
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterator
from typing import List
from typing import Tuple

import pytest
from jupyter_client.manager import KernelManager  # type: ignore

from metacellswidgets.kernel import _MainThreadJobs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_main_thread_jobs_run_on_the_main_thread() -> None:
    """
    A job handed from another thread runs on the main thread, and its result comes back.
    """
    jobs = _MainThreadJobs()
    is_done = threading.Event()
    results: Dict[str, Any] = {}

    def other_thread() -> None:
        results["value"] = jobs.run(lambda: threading.current_thread().name)
        is_done.set()
        jobs.wake()

    threading.Thread(target=other_thread).start()
    jobs.serve(is_done)
    assert results["value"] == "MainThread"


def test_main_thread_jobs_pass_errors_back() -> None:
    """
    An error raised by a job is raised in the thread which handed it.
    """
    jobs = _MainThreadJobs()
    is_done = threading.Event()
    results: Dict[str, Any] = {}

    def fail() -> None:
        raise ValueError("job failed")

    def other_thread() -> None:
        try:
            jobs.run(fail)
        except ValueError as error:
            results["error"] = str(error)
        is_done.set()
        jobs.wake()

    threading.Thread(target=other_thread).start()
    jobs.serve(is_done)
    assert results["error"] == "job failed"


def test_main_thread_jobs_run_directly_on_the_main_thread() -> None:
    """
    A job handed on the main thread runs at once, with no ``serve``.
    """
    assert _MainThreadJobs().run(lambda: 1 + 1) == 2


@pytest.fixture(name="kernel", scope="module")
def kernel_fixture(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Tuple[Any, Any]]:
    """
    A kernel running this Python, which sees this checkout, and a client connected to it. They talk over local (IPC)
    sockets in a temporary directory, since the kernel warns about unencrypted TCP.
    """
    sockets = tmp_path_factory.mktemp("kernel") / "sockets"
    manager = KernelManager(kernel_name="python3", transport="ipc", ip=str(sockets))
    kernel_spec = manager.kernel_spec
    assert kernel_spec is not None
    kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]  # NOT F-STRING
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ROOT + os.pathsep + environment.get("PYTHONPATH", "")
    manager.start_kernel(env=environment)
    client = manager.client()
    client.start_channels()
    client.wait_for_ready(timeout=60)
    try:
        yield manager, client
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)


def _execute(client: Any, code: str, timeout: float = 300) -> str:
    # Run the code in the kernel, wait for it to finish, and return what it printed.
    message_id = client.execute(code)
    return _outputs(client, message_id, timeout)


def _outputs(client: Any, message_id: str, timeout: float) -> str:
    # What the execution printed, once the kernel is idle again. Raise if it failed.
    texts = []
    deadline = time.time() + timeout
    while True:
        message = client.get_iopub_msg(timeout=max(deadline - time.time(), 0.1))
        if message["parent_header"].get("msg_id") != message_id:
            continue
        kind = message["msg_type"]
        if kind == "stream":
            texts.append(message["content"]["text"])
        elif kind == "error":
            raise AssertionError(message["content"]["ename"] + ": " + message["content"]["evalue"])
        elif kind == "status" and message["content"]["execution_state"] == "idle":
            return "".join(texts)


def test_import_wraps_the_julia_flush_hook(kernel: Tuple[Any, Any]) -> None:
    """
    Importing the package replaces ``juliacall``'s raw flush hook.
    """
    _, client = kernel
    output = _execute(
        client,
        "import metacellswidgets\n"
        "from dafpy.julia_import import jl\n"
        "print(hasattr(jl.PythonCall, '_ipython'))\n"
        "print(jl.PythonCall._ipython._flush_stdio in get_ipython().events.callbacks['post_execute'])\n",
    )
    # Starting Julia prints its own messages first.
    assert output.split()[-2:] == ["True", "False"]


def test_widget_messages_reach_a_blocked_cell(kernel: Tuple[Any, Any]) -> None:
    """
    While a cell blocks serving jobs, a click is handled on the owned subshell, and its job runs on the main thread.
    """
    _, client = kernel
    model_id = _execute(
        client,
        "import threading\n"
        "import ipywidgets\n"
        "from metacellswidgets.kernel import _MainThreadJobs, _owned_subshell_id, _route_to_subshell\n"
        "button = ipywidgets.Button()\n"
        "jobs = _MainThreadJobs()\n"
        "is_done = threading.Event()\n"
        "threads = {}\n"  # NOT F-STRING
        "def on_click(_button):\n"
        "    threads['callback'] = threading.current_thread().name\n"
        "    threads['job'] = jobs.run(lambda: threading.current_thread().name)\n"
        "    is_done.set()\n"
        "    jobs.wake()\n"
        "button.on_click(on_click)\n"
        "_route_to_subshell(button, _owned_subshell_id())\n"
        "print(button.model_id)\n",
    ).strip()

    message_id = client.execute("jobs.serve(is_done)\nprint(threads['callback'], threads['job'])\n")
    time.sleep(1)
    click = client.session.msg(
        "comm_msg", {"comm_id": model_id, "data": {"method": "custom", "content": {"event": "click"}}}
    )
    client.shell_channel.send(click)

    callback_thread, job_thread = _outputs(client, message_id, timeout=60).split()
    assert callback_thread.startswith("subshell-")
    assert job_thread == "MainThread"


def test_callback_errors_are_reported(kernel: Tuple[Any, Any]) -> None:
    """
    While reporting, an exception raised in a widget callback is shown in the given output.
    """
    _, client = kernel
    model_id = _execute(
        client,
        "import threading\n"
        "import ipywidgets\n"
        "from metacellswidgets.kernel import _MainThreadJobs, _owned_subshell_id, _reporting_callback_errors\n"
        "from metacellswidgets.kernel import _route_to_subshell\n"
        "output = ipywidgets.Output()\n"
        "text = ipywidgets.Text()\n"
        "jobs = _MainThreadJobs()\n"
        "is_done = threading.Event()\n"
        "def fail(_change):\n"
        "    raise ValueError('callback failed')\n"
        "text.observe(fail, names='value')\n"
        "_route_to_subshell(text, _owned_subshell_id())\n"
        "print(text.model_id)\n",
    ).strip()

    # Serving ends once the output shows the exception, so it is reported before the reporting stops.
    message_id = client.execute(
        "with _reporting_callback_errors(output):\n"
        "    jobs.serve(is_done, lambda: is_done.set() if output.outputs else None)\n"
        "print('callback failed' in ''.join(entry.get('text', '') for entry in output.outputs))\n"
    )
    time.sleep(1)
    _send_state(client, {"comm_id": model_id}, {"value": "x"})
    assert _outputs(client, message_id, timeout=60).split()[-1] == "True"


def _is_gene_picker(state: Dict[str, Any]) -> bool:
    # Whether the widget state is of the combobox of a gene picker.
    return state.get("_model_name") == "ComboboxModel" and state.get("placeholder") == "Gene"


def _is_done_button(state: Dict[str, Any]) -> bool:
    # Whether the widget state is of the "Done" button.
    return state.get("_model_name") == "ButtonModel" and state.get("description") == "Done"


def _is_class_choice(state: Dict[str, Any]) -> bool:
    # Whether the widget state is of the dropdown of a picker of a property or of a tweak. It is opened with no options,
    # which are set right after (unlike the axis picker's dropdown).
    return state.get("_model_name") == "DropdownModel" and not state.get("_options_labels")


def _opened_widgets(
    client: Any, is_wanted: Callable[[Dict[str, Any]], bool], count: int, timeout: float = 300
) -> List[Dict[str, Any]]:
    # The states (with their comm ids) of the next ``count`` widgets the kernel opens which are wanted, in the order they
    # are opened. Widgets an editor creates while its cell blocks are opened by the main thread on behalf of a widget
    # message, so the message which opened them isn't checked.
    widgets: List[Dict[str, Any]] = []
    deadline = time.time() + timeout
    while len(widgets) < count:
        message = client.get_iopub_msg(timeout=max(deadline - time.time(), 0.1))
        if message["msg_type"] == "error":
            raise AssertionError(message["content"]["ename"] + ": " + message["content"]["evalue"])
        if message["msg_type"] == "comm_open":
            state = message["content"]["data"].get("state", {})
            if is_wanted(state):
                widgets.append(dict(state, comm_id=message["content"]["comm_id"]))
    return widgets


def _send_state(client: Any, widget: Dict[str, Any], state: Dict[str, Any]) -> None:
    # Change the state of a widget, as the browser does.
    message = {"comm_id": widget["comm_id"], "data": {"method": "update", "state": state, "buffer_paths": []}}
    client.shell_channel.send(client.session.msg("comm_msg", message))
    time.sleep(1)


# Makes a small ``daf`` of the expression of three genes in two metacells, for the interactive forms to show. The marker
# ranks and the log fractions are for the genes heatmap.
_DAF_SETUP = (
    "import numpy as np\n"
    "import dafpy as dp\n"
    "import metacellswidgets as mw\n"
    "daf = dp.memory_daf(name='genes')\n"
    "daf.add_axis('gene', ['A', 'B', 'D'])\n"
    "daf.add_axis('metacell', ['M1', 'M2'])\n"
    "daf.set_vector('gene', 'marker_rank', np.array([1, 2, 3], dtype='uint32'))\n"
    "daf.set_matrix('gene', 'metacell', 'linear_fraction', "
    "np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], dtype='float32', order='F'))\n"
    "daf.set_matrix('gene', 'metacell', 'log_linear_fraction', "
    "np.array([[-3.0, -2.0], [-1.5, -1.0], [-0.5, -0.2]], dtype='float32', order='F'))\n"
)


def _click(client: Any, widget: Dict[str, Any]) -> None:
    # Click a button, as the browser does.
    message = {"comm_id": widget["comm_id"], "data": {"method": "custom", "content": {"event": "click"}}}
    client.shell_channel.send(client.session.msg("comm_msg", message))


def _rewritten_text(client: Any, message_id: str) -> str:
    # The code the execution rewrote its cell to, once it is done.
    deadline = time.time() + 120
    while True:
        reply = client.get_shell_msg(timeout=max(deadline - time.time(), 0.1))
        if reply["parent_header"].get("msg_id") == message_id:
            break
    assert reply["content"]["status"] == "ok"
    payloads = [payload for payload in reply["content"]["payload"] if payload["source"] == "set_next_input"]
    assert payloads[-1]["replace"]
    return payloads[-1]["text"]


def test_interactive_display_rewrites_the_cell(kernel: Tuple[Any, Any]) -> None:
    """
    An interactive form blocks its cell; after editing a gene, coloring by the expression of another gene (whose picker
    is created while the cell blocks), and clicking "Done", the cell is rewritten with the edited arguments, keeping
    the receiver of the form's call.
    """
    _, client = kernel
    _execute(client, _DAF_SETUP)

    cell = "form = mw.DafWidgets(daf).gene_gene(x_gene='A', y_gene='B')\nform.display(interactive=True)\n"
    message_id = client.execute(cell)
    widgets = _opened_widgets(
        client, lambda state: _is_done_button(state) or _is_gene_picker(state) or _is_class_choice(state), 5
    )
    done = next(widget for widget in widgets if _is_done_button(widget))
    _x_gene, y_gene = [widget for widget in widgets if _is_gene_picker(widget)]
    colors, _sizes = [widget for widget in widgets if _is_class_choice(widget)]

    time.sleep(1)
    _send_state(client, y_gene, {"value": "D"})
    # The only property of the metacells which may color them is the gene expression, after the empty choice.
    _send_state(client, colors, {"index": 1})
    colors_gene = _opened_widgets(client, _is_gene_picker, 1)[0]
    _send_state(client, colors_gene, {"value": "D"})
    _click(client, done)
    assert _rewritten_text(client, message_id) == (
        "form = mw.DafWidgets(daf).gene_gene(axis='metacell', x_gene='A', y_gene='D', "
        "colors=mw.GeneExpression(gene='D'))\n"
        "form.display(interactive=False)"
    )


def _is_graph_menu(state: Dict[str, Any]) -> bool:
    # Whether the widget state is of the dropdown of the first level of the menu of the graphs.
    return state.get("_model_name") == "DropdownModel" and (state.get("_options_labels") or [None])[0] == "Choose..."


def test_menu_rewrites_the_cell(kernel: Tuple[Any, Any]) -> None:
    """
    A menu blocks its cell; after choosing a graph (whose editor is created while the cell blocks), picking its genes,
    and clicking "Done", the menu call is rewritten into the chosen graph's call, displayed with ``interactive=False``.
    """
    _, client = kernel
    _execute(client, _DAF_SETUP)

    message_id = client.execute("form = mw.DafWidgets(daf).menu()\n")
    widgets = _opened_widgets(client, lambda state: _is_done_button(state) or _is_graph_menu(state), 2)
    done = next(widget for widget in widgets if _is_done_button(widget))
    menu = next(widget for widget in widgets if _is_graph_menu(widget))

    time.sleep(1)
    _send_state(client, menu, {"index": menu["_options_labels"].index("GeneGene")})
    genes = _opened_widgets(client, _is_gene_picker, 2)
    x_gene, y_gene = genes[0], genes[1]
    _send_state(client, x_gene, {"value": "A"})
    _send_state(client, y_gene, {"value": "D"})
    _click(client, done)
    assert _rewritten_text(client, message_id) == (
        "form = mw.DafWidgets(daf).gene_gene(axis='metacell', x_gene='A', y_gene='D').display(interactive=False)"
    )


def _is_graphs_button(state: Dict[str, Any]) -> bool:
    # Whether the widget state is of the "Graphs" button.
    return state.get("_model_name") == "ButtonModel" and state.get("description") == "Graphs"


def test_graphs_button_switches_the_graph(kernel: Tuple[Any, Any]) -> None:
    """
    In an interactive form, the "Graphs" button shows the menu; choosing another graph there and clicking "Done"
    rewrites the form call into the chosen graph's, on the same receiver, keeping the arguments they share.
    """
    _, client = kernel
    _execute(client, _DAF_SETUP)

    cell = "form = mw.DafWidgets(daf).gene_gene(x_gene='A', y_gene='B')\nform.display(interactive=True)\n"
    message_id = client.execute(cell)
    widgets = _opened_widgets(
        client, lambda state: _is_done_button(state) or _is_graphs_button(state) or _is_graph_menu(state), 3
    )
    done = next(widget for widget in widgets if _is_done_button(widget))
    graphs = next(widget for widget in widgets if _is_graphs_button(widget))
    menu = next(widget for widget in widgets if _is_graph_menu(widget))

    time.sleep(1)
    _click(client, graphs)
    _send_state(client, menu, {"index": menu["_options_labels"].index("GenesHeatmap")})
    time.sleep(2)
    _click(client, done)
    assert _rewritten_text(client, message_id) == (
        "form = mw.DafWidgets(daf).genes_heatmap(axis='metacell')\nform.display(interactive=False)"
    )


def _is_show_legends(state: Dict[str, Any]) -> bool:
    # Whether the widget state is of the "Show legends" checkbox of a legends tweak.
    return state.get("_model_name") == "CheckboxModel" and state.get("description") == "Show legends"


def test_interactive_tweaks_rewrite_the_cell(kernel: Tuple[Any, Any]) -> None:
    """
    Picking a tweak in the blank row of the tweaks while editing (whose editor is created while the cell blocks), and
    clicking "Done", writes the tweak into the cell.
    """
    _, client = kernel
    _execute(client, _DAF_SETUP)

    cell = "form = mw.DafWidgets(daf).gene_gene(x_gene='A', y_gene='B')\nform.display(interactive=True)\n"
    message_id = client.execute(cell)
    # The class choices are those of the colors, the sizes, the blank row of the hovers, and the blank row of the
    # tweaks, in this order.
    widgets = _opened_widgets(client, lambda state: _is_done_button(state) or _is_class_choice(state), 5)
    done = next(widget for widget in widgets if _is_done_button(widget))
    tweak_choice = [widget for widget in widgets if _is_class_choice(widget)][3]

    time.sleep(1)
    # The choices of the blank row are: "", Size, Title, Legends, ...
    _send_state(client, tweak_choice, {"index": 3})
    show_legends = _opened_widgets(client, _is_show_legends, 1)[0]
    _send_state(client, show_legends, {"value": False})
    _click(client, done)
    assert _rewritten_text(client, message_id) == (
        "form = mw.DafWidgets(daf).gene_gene(axis='metacell', x_gene='A', y_gene='B', "
        "tweaks=[mw.Legends(is_shown=False)])\n"
        "form.display(interactive=False)"
    )
