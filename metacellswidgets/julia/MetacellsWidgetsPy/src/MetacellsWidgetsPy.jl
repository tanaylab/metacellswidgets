# The Julia side of `metacellswidgets`: the Julia packages it uses, and the precompilation of the calls Python makes.
#
# Python always loads `PythonCall` before anything else, so this loads it first too, and is precompiled the same way.
# Its workload runs `metacellswidgets.workloads.run_workload()` from Python, so this package caches the code those calls
# compile, and a session does not compile it again.
module MetacellsWidgetsPy

using PythonCall
using PrecompileTools

import DafPy
import MetacellsGraphsPy
import MetacellsPy
import SomeGraphsPy

# The code this caches depends on the Python code of `metacellswidgets`, which runs the workload. Julia only knows of its
# own sources, so this tells it to compile again when any of those files changes.
const METACELLSWIDGETS_DIRECTORY = joinpath(@__DIR__, "..", "..", "..")
for name in readdir(METACELLSWIDGETS_DIRECTORY)
    if endswith(name, ".py")
        include_dependency(joinpath(METACELLSWIDGETS_DIRECTORY, name); track_content = true)
    end
end

# Whether the Python that `PythonCall` runs imports the `metacellswidgets` this package belongs to. A precompilation
# started from plain Julia gets whatever Python `PythonCall` finds, which may lack `metacellswidgets`, or have a version
# of it without this package beside it. A directory named `metacellswidgets` in the working directory is also found, as
# a namespace with no origin.
function is_matching_metacellswidgets()::Bool
    spec = pyimport("importlib.util").find_spec("metacellswidgets")
    if pyis(spec, pybuiltins.None) || pyis(spec.origin, pybuiltins.None)
        return false
    end
    project_path = joinpath(dirname(pyconvert(String, spec.origin)), "julia", "MetacellsWidgetsPy", "Project.toml")
    return isfile(project_path) &&
           occursin("uuid = \"$(Base.PkgId(MetacellsWidgetsPy).uuid)\"", read(project_path, String))
end

@compile_workload begin
    if !is_matching_metacellswidgets()
        error(
            "MetacellsWidgetsPy could not be precompiled: the Python that PythonCall runs " *
            "($(PythonCall.C.CTX.exe_path)) does not import the metacellswidgets that MetacellsWidgetsPy belongs to.\n" *
            "This is harmless: MetacellsWidgetsPy will be precompiled the first time you import metacellswidgets " *
            "from Python.\n" *
            "To do it now, run: python -c \"import metacellswidgets\" " *
            "(with the Python where metacellswidgets is installed).",
        )
    end
    # While this is precompiled, neither `metacellswidgets` nor the Python packages below it can import anything into
    # Julia's `Main`, so their Julia packages are handed over here instead.
    pysetattr(pyimport("builtins"), "_dafpy_glue", Py(DafPy))
    pysetattr(pyimport("builtins"), "_somegraphspy_glue", Py(SomeGraphsPy))
    pysetattr(pyimport("builtins"), "_metacellspy_glue", Py(MetacellsPy))
    pysetattr(pyimport("builtins"), "_metacellsgraphspy_glue", Py(MetacellsGraphsPy))
    pysetattr(pyimport("builtins"), "_metacellswidgets_glue", Py(MetacellsWidgetsPy))
    pyexec("from metacellswidgets.workloads import run_workload\nrun_workload()", pydict())
end

end  # module
