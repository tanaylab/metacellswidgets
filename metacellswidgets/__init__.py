"""
Interactive figures of a metacells repository in Jupyter notebooks.

A form holds the parameters of one of the figures of ``metacellsgraphspy``, and the points selected in it. Displaying
it shows the figure. Displaying it interactively shows an editor instead: controls for the parameters, the figure, and
a "Done" button. When you click "Done", the form writes its parameters and selection back into the code of the cell,
so running the notebook again gives the same figure and the same selection.
"""

__author__ = "Oren Ben-Kiki"
__email__ = "oren@ben-kiki.org"
__version__ = "0.1.0"

# pylint: disable=wildcard-import,unused-wildcard-import

import os as _os

from .anndata_widgets import *
from .common import *
from .daf_widgets import *
from .editors import *
from .entries import *
from .forms import *
from .graphs import *
from .julia_import import *
from .kernel import *
from .properties import *
from .rewrite import *
from .selections import *
from .sources import *
from .tweaks import *

# If ``METACELLS_TRACE_COMPILE`` is set, each public function records what Julia compiles while it runs (see
# ``dafpy.compile_tracing``).
if _os.environ.get("METACELLS_TRACE_COMPILE"):
    from dafpy.compile_tracing import wrap_package as _wrap_package

    _wrap_package(__name__)
