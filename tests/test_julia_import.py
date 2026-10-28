"""
Test the Julia package ``MetacellsWidgetsPy``, which ships inside this package and caches the code our calls compile.
"""

import json
import os
import tomllib
from typing import Any
from typing import Collection

import metacellswidgets as mw
from metacellswidgets.julia_import import _GLUE_PROJECT_PATH
from metacellswidgets.julia_import import jl


def test_glue_is_loaded() -> None:
    """
    Importing the package loads ``MetacellsWidgetsPy``, so its cache is used.
    """
    assert jl.seval("isdefined(Main, :MetacellsWidgetsPy)")


def _glue_project() -> dict[str, Any]:
    """
    The ``Project.toml`` of ``MetacellsWidgetsPy``.
    """
    with open(_GLUE_PROJECT_PATH, "rb") as file:
        return tomllib.load(file)


def test_glue_version_is_the_package_version() -> None:
    """
    ``MetacellsWidgetsPy`` ships inside this package, so their versions are the same.
    """
    assert _glue_project()["version"] == mw.__version__


def _dependencies_of(package: str) -> Collection[str]:
    """
    The dependencies a Julia package's own ``Project.toml`` lists, if it is loaded in ``Main``.
    """
    if not jl.seval(f"isdefined(Main, :{package})"):
        return ()
    directory = jl.seval(f"pkgdir({package})")
    if directory is None:
        return ()
    with open(os.path.join(str(directory), "Project.toml"), "rb") as file:
        return tomllib.load(file).get("deps", {})


def test_url_packages_are_glue_dependencies() -> None:
    """
    A package comes by URL when it is not registered. It is a dependency of ``MetacellsWidgetsPy``, or of one of
    ``MetacellsWidgetsPy``'s dependencies.
    """
    with open(os.path.join(os.path.dirname(mw.__file__), "juliapkg.json"), encoding="utf8") as file:
        packages = json.load(file)["packages"]
    glue_packages = _glue_project()["deps"]
    for name, package in packages.items():
        if "url" in package and name != "MetacellsWidgetsPy":
            assert name in glue_packages or any(
                name in _dependencies_of(glue_package) for glue_package in glue_packages
            ), f"the URL package {name} of juliapkg.json is not a dependency of MetacellsWidgetsPy, nor of its dependencies"
