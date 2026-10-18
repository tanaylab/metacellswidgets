"""
Test the look arguments of the properties, which change only how a property is shown (``show_legend``, ``log_base``).
"""

import pytest

import metacellswidgets as mw
from metacellswidgets.editors import PropertyPicker
from metacellswidgets.properties import Slot
from metacellswidgets.rewrite import _literal_text

from .test_daf_widgets import _full_daf


def test_look_arguments() -> None:
    """
    A property gives the values of its look arguments, and compares to another by its other arguments only.
    """
    total_umis = mw.TotalUMIs(show_legend=False, log_base=mw.LogBase.Log2Base)
    assert total_umis.look_arguments() == {"log_base": mw.LogBase.Log2Base, "show_legend": False}
    assert mw.Type().look_arguments() == {"show_legend": None}
    assert not mw.UMAP("x").look_arguments()
    assert total_umis.has_same_content(mw.TotalUMIs())
    assert total_umis != mw.TotalUMIs()
    assert not mw.GeneExpression("A", show_legend=False).has_same_content(mw.GeneExpression("B", show_legend=False))
    assert not mw.Type().has_same_content(mw.Block())


def test_written_look_arguments() -> None:
    """
    A look argument which is ``None`` isn't written; an enum value is written through the notebook's name for its class.
    """
    assert repr(mw.Type()) == "Type()"
    assert repr(mw.GeneExpression("A")) == "GeneExpression(gene='A')"
    namespace = {"mw": mw}
    assert _literal_text("log_base", mw.LogBase.Log10Base, namespace) == "mw.LogBase.Log10Base"
    assert (
        mw.TotalUMIs(show_legend=False, log_base=mw.LogBase.Log2Base).code("mw.TotalUMIs", namespace)
        == "mw.TotalUMIs(show_legend=False, log_base=mw.LogBase.Log2Base)"
    )


def test_fill_passes_the_look_arguments() -> None:
    """
    The look arguments of a property reach its data source.
    """
    form = mw.DafWidgets(_full_daf()).gene_gene(
        x_gene="A", y_gene="B", colors=mw.TotalUMIs(show_legend=False, log_base=mw.LogBase.Log2Base)
    )
    colors = form.graph().configuration.points.colors
    assert not colors.show_legend
    assert colors.scale.log_base == mw.LogBase.Log2Base


def test_picker_keeps_the_look_arguments() -> None:
    """
    A property picker keeps the look arguments of the property it starts with.
    """
    picker = PropertyPicker(mw.DafWidgets(_full_daf()), Slot.COLORS, "metacell", mw.Type(show_legend=False))
    assert picker.value == mw.Type(show_legend=False)


def test_look_defaults() -> None:
    """
    The defaults of the look arguments are those of the properties' data sources.
    """
    assert mw.Type.look_default("show_legend") is True
    assert mw.IsLateral.look_default("show_legend") is False
    assert mw.TotalUMIs.look_default("log_base") == mw.LogBase.Log10Base
    assert mw.GeneExpression.look_default("log_base") == mw.LogBase.Log2Base


def test_picker_look_widgets() -> None:
    """
    In a colors slot, a property picker shows the look arguments, with their defaults while they are ``None``.
    Changing one sets it. A hover slot has no look widgets.
    """
    source = mw.DafWidgets(_full_daf())
    picker = PropertyPicker(source, Slot.COLORS, "metacell", mw.TotalUMIs())
    checkbox, dropdown = picker._look_box.children
    assert checkbox.value is True
    assert dropdown.value == mw.LogBase.Log10Base
    assert picker.value == mw.TotalUMIs()

    dropdown.value = mw.LogBase.Log2Base
    assert picker.value == mw.TotalUMIs(log_base=mw.LogBase.Log2Base)
    checkbox.value = False
    assert picker.value == mw.TotalUMIs(show_legend=False, log_base=mw.LogBase.Log2Base)

    assert not PropertyPicker(source, Slot.HOVERS, "metacell", mw.TotalUMIs())._look_box.children


def test_picker_look_of_a_default() -> None:
    """
    Changing the look of a shown default makes it the value.
    """
    picker = PropertyPicker(mw.DafWidgets(_full_daf()), Slot.COLORS, "metacell", default=mw.Type())
    assert picker.value is None
    picker._look_box.children[0].value = False
    assert picker.value == mw.Type(show_legend=False)


def test_hovers_compare_content() -> None:
    """
    A hover showing the same data as the colors is an error, whatever their look arguments.
    """
    with pytest.raises(ValueError):
        mw.DafWidgets(_full_daf()).gene_gene(
            x_gene="A", y_gene="B", colors=mw.Type(show_legend=False), hovers=[mw.Type()]
        )
