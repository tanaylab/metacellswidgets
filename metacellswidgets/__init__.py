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

from .anndata_widgets import *
from .daf_widgets import *
from .editors import *
from .kernel import *
from .properties import *
from .rewrite import *
from .sources import *
