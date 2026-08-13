"""Garde-fous sur le validateur de migration.

Le défaut corrigé ici : chaque vérification d'import était un bloc ``try:``
sans aucun import, qui affichait donc ``OK`` en toute circonstance.
``check_imports()`` ne pouvait renvoyer ``False`` pour aucune entrée -- il
annonçait « SQLAlchemy pool OK » deux lignes après « SQLAlchemy NOT
INSTALLED ». Les tests ci-dessous verrouillent les deux propriétés que cela
violait : une sonde importe vraiment, et un échec requis se propage.
"""

from __future__ import annotations

import dis

import pytest

from fpdb_3_legacy import validate_migration


def test_every_probe_actually_imports() -> None:
    """Une sonde sans import est le bug d'origine : elle validerait le vide."""
    for label, probe, _optional in validate_migration.IMPORT_CHECKS:
        opnames = {instruction.opname for instruction in dis.get_instructions(probe)}
        assert "IMPORT_NAME" in opnames, f"la sonde {label!r} n'importe rien"


def test_check_import_reports_success() -> None:
    assert validate_migration.check_import("ok", lambda: object()) is True


def test_check_import_reports_a_required_failure() -> None:
    def missing() -> object:
        msg = "No module named 'absent'"
        raise ImportError(msg)

    assert validate_migration.check_import("absent", missing) is False


def test_check_import_tolerates_an_optional_failure() -> None:
    """SQLAlchemy est sondé derrière un try/except dans Database.py.

    Le rapporter comme une erreur ferait échouer une installation conforme.
    """

    def missing() -> object:
        msg = "No module named 'sqlalchemy'"
        raise ImportError(msg)

    assert validate_migration.check_import("sqlalchemy", missing, optional=True) is True


def test_check_imports_fails_when_a_required_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """La régression : aucune entrée ne pouvait faire échouer check_imports()."""

    def missing() -> object:
        msg = "No module named 'absent'"
        raise ImportError(msg)

    monkeypatch.setattr(validate_migration, "IMPORT_CHECKS", [("absent", missing, False)])
    assert validate_migration.check_imports() is False


def test_check_imports_survives_an_optional_probe_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> object:
        msg = "No module named 'absent'"
        raise ImportError(msg)

    monkeypatch.setattr(validate_migration, "IMPORT_CHECKS", [("absent", missing, True)])
    assert validate_migration.check_imports() is True


def test_only_declared_dependencies_are_probed() -> None:
    """Sonder un paquet non déclaré faisait échouer une installation saine.

    ``sqlalchemy``, ``fastapi`` et ``pydantic`` n'apparaissent nulle part dans
    ``pyproject.toml`` ; ``matplotlib`` et ``mplfinance`` y figurent encore mais
    aucun code applicatif ne les importe depuis la migration PyQtGraph (#228).
    """
    required = {label for label, _probe, optional in validate_migration.IMPORT_CHECKS if not optional}
    assert "SQLAlchemy" not in required
    assert not {"FastAPI", "Pydantic", "matplotlib", "mplfinance"} & required


def test_check_version_flags_a_missing_package() -> None:
    assert validate_migration.check_version("paquet-absent-volontairement", "1.0.0") is False
