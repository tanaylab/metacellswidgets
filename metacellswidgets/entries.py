"""
Selections of entries: which entries each side of a graph shows, such as the genes of the rows of a heatmap and the
metacells of its columns.

A gene selection (e.g., ``TopMarkers(count=100)``) picks the genes. An entry filter (e.g., ``OfTypes(types=["T1"])``)
picks some of the entries of an axis; a list of filters picks the entries which pass all of them. Like a property,
each holds the values of its arguments, so a form can write it back into the code of its cell. Whether a data source
has it, and its value, are implemented separately for each kind of data source. Each is a thin wrapper over a data
source of ``metacellsgraphspy`` (e.g., ``get_is_in_categories_vector``), so a graph shown with them is the same as a
script calling these data sources.
"""

from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Protocol
from typing import Sequence
from typing import Type
from typing import Union
from typing import cast

import metacellsgraphspy as mg
import numpy as np
from dafpy.julia_import import DEFAULT
from dafpy.julia_import import DefaultValue
from ipywidgets import IntText  # type: ignore
from ipywidgets import Layout  # type: ignore
from ipywidgets import Widget  # type: ignore

from .common import Arguments
from .common import _give_own_dispatchers
from .editors import ArgumentsEditor
from .editors import AxisPicker
from .editors import ClassPicker
from .editors import ComboPicker
from .editors import GeneChoices
from .editors import GenePicker
from .editors import ListEditor
from .editors import PickerEditor
from .editors import PickerRow
from .sources import SourceWidgets

__all__: List[str] = [
    "BlockNames",
    "EntryFilter",
    "EntryFilterPicker",
    "GeneList",
    "GeneSelection",
    "GeneSelectionPicker",
    "InEnvironment",
    "InNeighborhood",
    "OfTypes",
    "SkeletonGenes",
    "TopMarkers",
    "TypeNames",
]


class TypeNames(Protocol):  # pylint: disable=too-few-public-methods
    """
    A data source which can list the names of its types, for picking some of them.
    """

    def type_names(self) -> List[str]:
        """
        The names of the types, sorted.
        """


class BlockNames(Protocol):  # pylint: disable=too-few-public-methods
    """
    A data source which can list the names of its blocks, for picking one of them.
    """

    def block_names(self) -> List[str]:
        """
        The names of the blocks, in the order of the block axis.
        """


class GeneSelection(Arguments):
    """
    The base class of the selections of genes. Its instance holds the values of its arguments (see
    :py:class:`~metacellswidgets.common.Arguments`). A selection class must derive directly from this class.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, GeneSelection, ("exists", "genes"))

    @classmethod
    def exists(cls, source: SourceWidgets) -> bool:  # pylint: disable=unused-argument
        """
        Whether the ``source`` has the data of the selection. Each kind of data source implements this for the
        selections it supports; for any other, the selection does not exist.
        """
        return False

    @classmethod
    def editor(
        cls, source: SourceWidgets, current: Optional["GeneSelection"]  # pylint: disable=unused-argument
    ) -> Optional[Widget]:
        """
        A widget for editing the selection's arguments, starting from the ``current`` selection (if any). Its ``value``
        is the selection, or ``None`` while the arguments are incomplete. A selection without arguments has no editor.
        """
        return None

    def genes(self, source: SourceWidgets) -> mg.Entries:
        """
        The selected genes of the ``source``, to pass as the ``genes`` of a data source. Each kind of data source
        implements this for the selections it supports; for any other, this is an error.
        """
        raise TypeError(f"{type(self).__name__}.genes is not implemented for: {type(source).__name__}")


class EntryFilter(Arguments):
    """
    The base class of the filters of the entries of an axis. Its instance holds the values of its arguments (see
    :py:class:`~metacellswidgets.common.Arguments`). A filter class must derive directly from this class.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _give_own_dispatchers(cls, EntryFilter, ("exists", "mask"))

    @classmethod
    def exists(cls, source: SourceWidgets, axis: str) -> bool:  # pylint: disable=unused-argument
        """
        Whether the ``source`` has the data of the filter for the entries of the ``axis``. Each kind of data source
        implements this for the filters it supports; for any other, the filter does not exist.
        """
        return False

    @classmethod
    def editor(
        cls, source: SourceWidgets, current: Optional["EntryFilter"]  # pylint: disable=unused-argument
    ) -> Optional[Widget]:
        """
        A widget for editing the filter's arguments, starting from the ``current`` filter (if any). Its ``value`` is the
        filter, or ``None`` while the arguments are incomplete. A filter without arguments has no editor.
        """
        return None

    def mask(self, source: SourceWidgets, axis: str) -> np.ndarray:
        """
        Whether each entry of the ``axis`` of the ``source`` passes the filter, to combine with other filters (by
        ``&``) and pass as the ``entries`` of a data source. Each kind of data source implements this for the filters
        it supports; for any other, this is an error.
        """
        raise TypeError(f"{type(self).__name__}.mask is not implemented for: {type(source).__name__}")

    def on_axis(self, source: SourceWidgets, axis: str) -> Optional["EntryFilter"]:
        """
        What the filter becomes for the entries of another ``axis`` of the ``source``: by default, itself if it exists
        there, and nothing otherwise.
        """
        return self if type(self).exists(source, axis) else None


class TopMarkers(GeneSelection):
    """
    The ``count`` strongest marker genes. This is the default selection of the genes.
    """

    def __init__(self, count: int = mg.TOP_MARKERS_COUNT_FOR_GRAPHS) -> None:
        self.count = count

    @classmethod
    def editor(cls, source: SourceWidgets, current: Optional[GeneSelection]) -> Widget:
        assert current is None or isinstance(current, TopMarkers)
        return _CountEditor(TopMarkers() if current is None else current)


class _CountEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    # The editor of a ``TopMarkers``: the number of genes. A number below one is incomplete.

    def __init__(self, current: TopMarkers) -> None:
        super().__init__()
        self._count = IntText(
            value=current.count,
            description="Count",
            style={"description_width": "initial"},
            layout=Layout(width="10em"),
        )
        self.children = [self._count]
        self._update_value()
        self._count.observe(self._on_change, names="value")

    def _on_change(self, _change: Dict) -> None:
        self._update_value()

    def _update_value(self) -> None:
        count = int(self._count.value)
        self.value = TopMarkers(count) if count > 0 else None
        self.is_blank = False


class SkeletonGenes(GeneSelection):
    """
    The skeleton genes, which the blocks were computed from.
    """


class GeneList(GeneSelection):
    """
    The genes with the ``names``, in this order.
    """

    def __init__(self, names: Sequence[str]) -> None:
        self.names = list(names)

    @classmethod
    def editor(cls, source: SourceWidgets, current: Optional[GeneSelection]) -> Widget:
        assert current is None or isinstance(current, GeneList)
        genes = cast(GeneChoices, source)
        return _NamesEditor(
            lambda name: PickerRow(GenePicker(genes, name)),
            None if current is None else current.names,
            GeneList,
            title="Genes",
        )


class _NamesEditor(ArgumentsEditor):  # pylint: disable=too-many-ancestors,abstract-method
    # The editor of a selection or a filter whose argument is a list of names: a list of rows, each picking a name. An
    # empty list is incomplete.

    def __init__(
        self,
        make_row: Callable[[Optional[str]], ArgumentsEditor],
        current: Optional[Sequence[str]],
        build: Callable[[List[str]], Arguments],
        *,
        title: str,
    ) -> None:
        super().__init__()
        self._build = build
        self._names = ListEditor(make_row, list(current or []), title=title)
        self.children = [self._names]
        self._update_value()
        self._names.observe(self._on_change, names="value")

    def _on_change(self, _change: Dict) -> None:
        self._update_value()

    def _update_value(self) -> None:
        names = self._names.value or []
        self.value = self._build(names) if names else None
        self.is_blank = False


class OfTypes(EntryFilter):
    """
    The entries whose type is one of the ``types``.
    """

    def __init__(self, types: Sequence[str]) -> None:
        self.types = list(types)

    @classmethod
    def editor(cls, source: SourceWidgets, current: Optional[EntryFilter]) -> Widget:
        assert current is None or isinstance(current, OfTypes)
        type_names = cast(TypeNames, source).type_names()
        return _NamesEditor(
            lambda name: PickerRow(ComboPicker(type_names, name, placeholder="Type")),
            None if current is None else current.types,
            OfTypes,
            title="Types",
        )


class InNeighborhood(EntryFilter):
    """
    The entries in the neighborhood of the ``block``: its blocks, or the metacells of its blocks.
    """

    def __init__(self, block: str) -> None:
        self.block = block

    @classmethod
    def editor(cls, source: SourceWidgets, current: Optional[EntryFilter]) -> Widget:
        assert current is None or isinstance(current, InNeighborhood)
        block_names = cast(BlockNames, source).block_names()
        return PickerEditor(
            ComboPicker(block_names, None if current is None else current.block, placeholder="Block"), InNeighborhood
        )


class InEnvironment(EntryFilter):
    """
    The metacells in the environment of the ``block``. On the block axis, this becomes the neighborhood of the
    ``block`` (see :py:class:`InNeighborhood`), since an environment is a set of metacells.
    """

    def __init__(self, block: str) -> None:
        self.block = block

    @classmethod
    def editor(cls, source: SourceWidgets, current: Optional[EntryFilter]) -> Widget:
        assert current is None or isinstance(current, InEnvironment)
        block_names = cast(BlockNames, source).block_names()
        return PickerEditor(
            ComboPicker(block_names, None if current is None else current.block, placeholder="Block"), InEnvironment
        )

    def on_axis(self, source: SourceWidgets, axis: str) -> Optional[EntryFilter]:
        if axis == "block":
            return InNeighborhood(self.block).on_axis(source, axis)
        return super().on_axis(source, axis)


# The selections of genes and the filters of entries, in the order they are offered.
_GENE_SELECTIONS: Sequence[Type[GeneSelection]] = (GeneList, SkeletonGenes, TopMarkers)
_ENTRY_FILTERS: Sequence[Type[EntryFilter]] = (InEnvironment, InNeighborhood, OfTypes)


class GeneSelectionPicker(ClassPicker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick a selection of the genes of the ``source``, starting with the ``current`` one. The choices are the selections
    the source has. While the ``current`` one is ``DEFAULT`` and nothing is picked, the default
    (:py:class:`TopMarkers`) is shown, and the ``value`` is ``DEFAULT``.
    """

    def __init__(self, source: SourceWidgets, current: Union[None, GeneSelection, DefaultValue] = DEFAULT) -> None:
        super().__init__(default=TopMarkers())
        self._source = source
        self._show([choice for choice in _GENE_SELECTIONS if choice.exists(source)], current)

    def _editor_of(self, choice: Type[Arguments], current: Optional[Arguments]) -> Optional[ArgumentsEditor]:
        assert issubclass(choice, GeneSelection)
        assert current is None or isinstance(current, GeneSelection)
        return choice.editor(self._source, current)


class EntryFilterPicker(ClassPicker):  # pylint: disable=too-many-ancestors,abstract-method
    """
    Pick a filter of the entries of the ``axis`` of the ``source``, starting with the ``current`` one (if any). The
    choices are the filters the source has for the axis. The ``axis`` may be an :py:class:`AxisPicker` to follow. When
    its axis changes, the filter becomes what :py:meth:`EntryFilter.on_axis` says (e.g., an environment becomes a
    neighborhood on the block axis).
    """

    def __init__(
        self, source: SourceWidgets, axis: Union[str, AxisPicker], current: Optional[EntryFilter] = None
    ) -> None:
        super().__init__(axis=axis)
        self._source = source
        self._show(self._choices(), current)

    def _choices(self) -> List[Type[EntryFilter]]:
        # The filters which may be picked for the current axis.
        assert self._axis is not None
        return [choice for choice in _ENTRY_FILTERS if choice.exists(self._source, self._axis)]

    def _editor_of(self, choice: Type[Arguments], current: Optional[Arguments]) -> Optional[ArgumentsEditor]:
        assert issubclass(choice, EntryFilter)
        assert current is None or isinstance(current, EntryFilter)
        return choice.editor(self._source, current)

    def _on_axis(  # pylint: disable=unused-argument
        self, old_axis: str, new_axis: str, current: Optional[Arguments]
    ) -> Optional[Arguments]:
        assert current is None or isinstance(current, EntryFilter)
        if current is None:
            return None
        return current.on_axis(self._source, new_axis)
