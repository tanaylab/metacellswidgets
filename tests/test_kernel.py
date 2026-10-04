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
from typing import Dict
from typing import Iterator
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
def kernel_fixture() -> Iterator[Tuple[Any, Any]]:
    """
    A kernel running this Python, which sees this checkout, and a client connected to it.
    """
    manager = KernelManager(kernel_name="python3")
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
