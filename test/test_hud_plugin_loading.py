"""Runtime plugin lookup for HUD aux windows and popups.

The config names these by bare module/class name. Packaged builds only expose
the ``fpdb_3_legacy`` package, so a lookup that assumes a flat sys.path silently
loses the HUD overlay (aux modules) or falls back to the default popup.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import Hud, Popup

pytestmark = pytest.mark.qt


@pytest.fixture
def aux_package(tmp_path, monkeypatch):
    """A package holding an aux module that is not importable by bare name."""
    package = tmp_path / "auxpkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "Aux_Probe.py").write_text("class ProbeHud:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(Hud, "LEGACY_PACKAGE", "auxpkg")
    _forget_probe_modules()
    yield package
    # The modules point at a tmp_path that is about to disappear.
    _forget_probe_modules()


def _forget_probe_modules() -> None:
    for name in [n for n in sys.modules if n == "auxpkg" or n.startswith("auxpkg.")]:
        del sys.modules[name]


def test_aux_module_resolves_through_the_package(aux_package) -> None:
    """A bare name that only exists inside the package still loads."""
    with pytest.raises(ImportError):
        __import__("Aux_Probe")

    assert Hud.importName("Aux_Probe", "ProbeHud").__name__ == "ProbeHud"


def test_unknown_aux_module_reports_every_candidate(aux_package, caplog) -> None:
    assert Hud.importName("Aux_Missing", "Nothing") is None
    assert "auxpkg.Aux_Missing" in caplog.text


def test_missing_class_in_a_loadable_module_is_not_retried(aux_package) -> None:
    assert Hud.importName("Aux_Probe", "NoSuchClass") is None


def test_qualified_module_name_is_used_as_is(aux_package) -> None:
    assert Hud.importName("auxpkg.Aux_Probe", "ProbeHud").__name__ == "ProbeHud"


@pytest.mark.parametrize("pu_class", ["Submenu", "Multicol", "default"])
def test_classic_popup_classes_resolve_from_the_popup_module(pu_class) -> None:
    """Popup is imported as fpdb_3_legacy.Popup; its own classes must be found."""
    assert Popup.resolve_popup_class(pu_class) is getattr(Popup, pu_class)


def test_unknown_popup_class_resolves_to_nothing() -> None:
    assert Popup.resolve_popup_class("NotAPopupClass") is None


def test_popup_factory_falls_back_to_default_for_unknown_class(monkeypatch) -> None:
    built = SimpleNamespace()
    monkeypatch.setattr(Popup, "default", lambda *args: built)

    assert Popup.popup_factory(pop=SimpleNamespace(pu_class="NotAPopupClass")) is built
