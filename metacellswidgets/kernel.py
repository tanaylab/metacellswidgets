"""
Let an editor block its cell while its widgets keep working.

An interactive form blocks the cell that displays it until the user clicks "Done". Three things make that work:

* The editor's widgets are routed to a kernel subshell this module owns. The subshell's thread handles their messages
  while the cell blocks the main thread. ``ipykernel`` would otherwise send them to the main shell, where they would
  wait behind the blocked cell.

* Julia only runs on the main thread, which started it. A Julia call from another thread can hang, e.g. when Julia
  needs every thread to stop for garbage collection. So widget callbacks hand Julia work to the blocked cell, which
  runs it and returns the result.

* ``juliacall``'s IPython extension flushes Julia's output after every comm message, on whatever thread handles it. That
  flush never returns on a subshell thread, so it is wrapped to only run on the main thread. This happens when this
  module is imported.

All of this uses internals of ``ipykernel`` 7, which is why the package requires ``ipykernel>=7.3,<8``.
"""

import queue
import threading
from contextlib import contextmanager
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import TypeVar

from dafpy.julia_import import jl
from IPython import get_ipython
from ipywidgets import Widget  # type: ignore

__all__: List[str] = []

T = TypeVar("T")


def _wrap_julia_flush_hook() -> None:
    # Replace ``juliacall``'s ``post_execute`` hook with one which only flushes on the main thread. Does nothing outside
    # IPython, or if the ``juliacall`` extension wasn't loaded.
    shell = get_ipython()
    if shell is None or not hasattr(jl.PythonCall, "_ipython"):
        return
    flush_stdio = jl.PythonCall._ipython._flush_stdio  # pylint: disable=protected-access
    if flush_stdio not in shell.events.callbacks["post_execute"]:
        return

    def flush_stdio_on_main_thread() -> None:
        if threading.current_thread() is threading.main_thread():
            flush_stdio()

    shell.events.unregister("post_execute", flush_stdio)
    shell.events.register("post_execute", flush_stdio_on_main_thread)


_wrap_julia_flush_hook()

_OWNED_SUBSHELL_ID: Optional[str] = None


def _owned_subshell_id() -> str:
    # The id of the kernel subshell this module owns, created on first use. Subshells are created on the shell channel
    # thread, so the creation is scheduled there.
    global _OWNED_SUBSHELL_ID  # pylint: disable=global-statement
    if _OWNED_SUBSHELL_ID is None:
        manager = get_ipython().kernel.shell_channel_thread.manager
        created: Dict[str, Any] = {}
        is_created = threading.Event()

        def create() -> None:
            try:
                created["id"] = manager._create_subshell()  # pylint: disable=protected-access
            except BaseException as error:  # pylint: disable=broad-except
                created["error"] = error
            is_created.set()

        manager._shell_channel_io_loop.add_callback(create)  # pylint: disable=protected-access
        if not is_created.wait(10):
            raise RuntimeError("timed out creating a kernel subshell")
        if "error" in created:
            raise created["error"]
        _OWNED_SUBSHELL_ID = created["id"]
    return _OWNED_SUBSHELL_ID


def _route_to_subshell(widget: Any, subshell_id: str) -> None:
    # Route the frontend messages of the widget, and of all the widgets it contains, to the subshell. A widget without a
    # comm yet is skipped; it is routed when it gets one (see ``_routing_new_widgets``).
    if widget.comm is not None:
        widget.comm._reply_subshell_for = lambda _data, _default: subshell_id  # pylint: disable=protected-access
    for child in getattr(widget, "children", ()):
        _route_to_subshell(child, subshell_id)


@contextmanager
def _routing_new_widgets(subshell_id: str) -> Iterator[None]:
    # Route the frontend messages of every widget constructed in this context to the subshell. An editor creates widgets
    # while its cell blocks (e.g. the editor of a property picked from a list), whose messages would otherwise wait for
    # the blocked cell. ``ipywidgets`` has a single construction callback; any previous one is called too, and restored.
    previous = Widget._widget_construction_callback  # pylint: disable=protected-access

    def route(widget: Any) -> None:
        if previous is not None:
            previous(widget)
        # A widget may be constructed before its comm is opened. It is routed once it has one.
        if widget.comm is not None:
            _route_to_subshell(widget, subshell_id)
        else:
            widget.observe(lambda _change: _route_to_subshell(widget, subshell_id), names="comm")

    Widget.on_widget_constructed(route)
    try:
        yield
    finally:
        Widget.on_widget_constructed(previous)


# pylint: disable=missing-function-docstring


class _MainThreadJobs:
    # Jobs handed to the main thread while it blocks in ``serve``.

    def __init__(self) -> None:
        self._jobs: "queue.Queue[Callable[[], None]]" = queue.Queue()

    def run(self, job: Callable[[], T]) -> T:
        # Run the job on the main thread and return its result. On the main thread, run it directly. On any other
        # thread, hand it to ``serve`` and wait for it to finish.
        if threading.current_thread() is threading.main_thread():
            return job()
        result: Dict[str, Any] = {}
        is_finished = threading.Event()

        def run_job() -> None:
            try:
                result["value"] = job()
            except BaseException as error:  # pylint: disable=broad-except
                result["error"] = error
            is_finished.set()

        self._jobs.put(run_job)
        is_finished.wait()
        if "error" in result:
            raise result["error"]
        return result["value"]

    def wake(self) -> None:
        # Make ``serve`` check its condition now, rather than at its next poll.
        self._jobs.put(lambda: None)

    def serve(self, is_done: threading.Event, on_poll: Optional[Callable[[], None]] = None) -> None:
        # Run handed jobs on the main thread until ``is_done`` is set. Call ``on_poll`` between jobs, about every 0.1
        # seconds. While serving, these are the jobs ``_on_main_thread`` hands work to.
        global _SERVING_JOBS  # pylint: disable=global-statement
        assert threading.current_thread() is threading.main_thread()
        _SERVING_JOBS = self
        try:
            while not is_done.is_set():
                if on_poll is not None:
                    on_poll()
                try:
                    job = self._jobs.get(timeout=0.1)
                except queue.Empty:
                    continue
                job()
        finally:
            _SERVING_JOBS = None


# pylint: enable=missing-function-docstring

_SERVING_JOBS: Optional[_MainThreadJobs] = None


def _on_main_thread(function: Callable[[], T]) -> T:
    # Run the function on the main thread and return its result. A widget callback which may call Julia (e.g. through a
    # data source) runs its work through this, since widget callbacks run on the subshell thread while an interactive
    # display serves its jobs. When no display is serving (e.g. in tests), run it directly.
    jobs = _SERVING_JOBS
    if jobs is None:
        return function()
    return jobs.run(function)
