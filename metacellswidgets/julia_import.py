"""
Import the Julia environment (for internal use).

The Julia run-time is obtained by ``dafpy``, which this package depends on. See it for how Julia is chosen and
configured. This only loads the Julia package ``MetacellsWidgetsPy``, which caches the code our calls compile.
"""

import builtins
import os
import tomllib
from typing import Any

from dafpy.julia_import import jl as _dafpy_jl

__all__: list[str] = []

# The Julia package ``MetacellsWidgetsPy``, in ``julia/MetacellsWidgetsPy`` beside this file, caches the code our calls
# compile. Its ``Project.toml`` lists the Julia packages we use. Like ``metacellsgraphspy``, this package needs no Julia
# code of its own.
_GLUE_PROJECT_PATH = os.path.join(os.path.dirname(__file__), "julia", "MetacellsWidgetsPy", "Project.toml")

# While ``MetacellsWidgetsPy`` itself is precompiled, Julia may not import anything into ``Main``, so
# ``MetacellsWidgetsPy`` hands itself over instead, and it binds the same names.
_METACELLSWIDGETS_GLUE: Any = getattr(builtins, "_metacellswidgets_glue", None)

# The interface to the Julia run-time. This is Julia's ``Main``, as in ``dafpy``, except while ``MetacellsWidgetsPy``
# itself is precompiled.
jl = _dafpy_jl if _METACELLSWIDGETS_GLUE is None else _METACELLSWIDGETS_GLUE

if _METACELLSWIDGETS_GLUE is None:
    with open(_GLUE_PROJECT_PATH, "rb") as glue_project_file:
        _GLUE_PACKAGES = tomllib.load(glue_project_file)["deps"]
    # Everything is imported rather than ``using``, so no package's exports leak into Julia's ``Main``. This keeps
    # ``Main`` clear for other Python packages that wrap Julia packages and are used in the same session.
    for package in ["MetacellsWidgetsPy"] + sorted(_GLUE_PACKAGES):
        if package != "PrecompileTools":
            jl.seval("import " + package)
