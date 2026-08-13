#!/usr/bin/env python3
"""Script de validation de la migration Python 3.13/3.14 + PySide6.

Ce script vérifie que les bibliothèques dont l'application dépend réellement
sont installées, importables, et dans une version compatible.

Deux règles tirées d'un échec de ce script :

* Une vérification d'import passe par :func:`check_import`, qui exécute une
  sonde. Les blocs ``try:`` écrits à la main ne contenaient aucun import et
  affichaient donc ``OK`` quoi qu'il arrive -- y compris pour des paquets
  absents de l'environnement.
* Seules les dépendances déclarées dans ``pyproject.toml`` comptent dans le
  verdict. Vérifier un paquet non déclaré faisait échouer le script sur une
  installation saine.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from importlib import metadata

VALIDATION_VERSION_ERRORS = (TypeError, ValueError)
VALIDATION_IMPORT_ERRORS = (AttributeError, ImportError, OSError, RuntimeError)
VALIDATION_NUMPY_ERRORS = (AssertionError, AttributeError, ImportError, TypeError, ValueError)


def check_version(package: str, min_version: str, name: str | None = None) -> bool:
    """Vérifie qu'un package est installé avec la version minimale requise.

    Args:
        package: Nom du package à vérifier
        min_version: Version minimale requise
        name: Nom d'affichage (optionnel)

    Returns:
        True si OK, False sinon
    """
    display_name = name or package
    try:
        installed_version = metadata.version(package)

        # Parse versions, handling beta/alpha/rc suffixes
        def parse_version_part(part: str) -> int:
            """Parse a version part, stripping non-numeric suffixes."""
            # Extract numeric part only (e.g., "10b0" -> 10)
            numeric = ""
            for char in part:
                if char.isdigit():
                    numeric += char
                else:
                    break
            return int(numeric) if numeric else 0

        inst_parts = [parse_version_part(x) for x in installed_version.split(".")[:3]]
        min_parts = [parse_version_part(x) for x in min_version.split(".")[:3]]

        # Pad to same length
        while len(inst_parts) < 3:
            inst_parts.append(0)
        while len(min_parts) < 3:
            min_parts.append(0)

        if inst_parts >= min_parts:
            print(f"✅ {display_name:20s} {installed_version:15s} (min: {min_version})")
            return True
        else:
            print(f"❌ {display_name:20s} {installed_version:15s} < {min_version} REQUIRED")
            return False
    except metadata.PackageNotFoundError:
        print(f"❌ {display_name:20s} NOT INSTALLED")
        return False
    except VALIDATION_VERSION_ERRORS as e:
        print(f"⚠️  {display_name:20s} ERROR: {e}")
        return False


def _probe_numpy() -> object:
    """Importe NumPy et exerce l'API 2.x utilisée par l'application."""
    import numpy as np

    return np.array([1, 2, 3]).sum()


def _probe_pyside6() -> object:
    """Importe les modules Qt dont dépendent la fenêtre principale et le HUD."""
    from PySide6 import QtCore, QtWidgets

    return QtCore.qVersion(), QtWidgets.QWidget


def _probe_pyqtgraph() -> object:
    """Importe le moteur de rendu des graphiques (remplace Matplotlib, cf. #228)."""
    import pyqtgraph as pg

    return pg.PlotWidget


def _probe_pandas() -> object:
    """Importe pandas."""
    import pandas as pd

    return pd.DataFrame


def _probe_aiohttp() -> object:
    """Importe aiohttp, utilisé par les captures HTTP."""
    import aiohttp

    return aiohttp.ClientSession


def _probe_sqlalchemy() -> object:
    """Importe SQLAlchemy.

    Optionnel : ``Database.py`` le sonde derrière un ``try``/``except`` et
    bascule sur ``use_sqlalchemy = False`` s'il manque. Le rapporter comme une
    erreur ferait échouer une installation parfaitement valide.
    """
    import sqlalchemy

    return sqlalchemy.__version__


#: Sondes exécutées par :func:`check_imports`, sous la forme
#: ``(libellé, sonde, optionnel)``. Chaque sonde doit réellement importer :
#: c'est ce qu'un test de régression vérifie.
IMPORT_CHECKS: list[tuple[str, Callable[[], object], bool]] = [
    ("NumPy", _probe_numpy, False),
    ("PySide6", _probe_pyside6, False),
    ("pyqtgraph", _probe_pyqtgraph, False),
    ("pandas", _probe_pandas, False),
    ("aiohttp", _probe_aiohttp, False),
    ("SQLAlchemy", _probe_sqlalchemy, True),
]


def check_import(label: str, probe: Callable[[], object], *, optional: bool = False) -> bool:
    """Exécute une sonde d'import et rapporte son résultat.

    Args:
        label: Nom affiché
        probe: Appelable qui effectue l'import à valider
        optional: Si True, un échec est signalé sans invalider la migration

    Returns:
        True si l'import a réussi, ou s'il a échoué mais que la dépendance est
        optionnelle.
    """
    try:
        probe()
    except VALIDATION_IMPORT_ERRORS as e:
        if optional:
            print(f"⚠️  {label:20s} OPTIONAL: {e}")
            return True
        print(f"❌ {label:20s} FAILED: {e}")
        return False
    print(f"✅ {label:20s} OK")
    return True


def check_imports() -> bool:
    """Vérifie que les imports critiques fonctionnent."""
    print("\n=== Vérification des Imports ===\n")

    results = [check_import(label, probe, optional=optional) for label, probe, optional in IMPORT_CHECKS]
    return all(results)


def check_numpy_functionality() -> bool:
    """Vérifie que les fonctionnalités NumPy 2.x fonctionnent."""
    print("\n=== Test Fonctionnalités NumPy ===\n")

    try:
        import numpy as np
        from numpy import cumsum

        # Test cumsum (compatible)
        arr = [1, 2, 3, 4, 5]
        result: np.ndarray = cumsum(arr)
        expected = np.array([1, 3, 6, 10, 15])
        assert np.array_equal(result, expected), "cumsum failed"
        print(f"✅ cumsum()            OK: {list(result)}")

        # Test array methods (NumPy 2.x style)
        test_array = np.array([1, 5, 3, 9, 2])

        max_val = test_array.max()
        assert max_val == 9, "array.max() failed"
        print(f"✅ array.max()         OK: {max_val}")

        min_val = test_array.min()
        assert min_val == 1, "array.min() failed"
        print(f"✅ array.min()         OK: {min_val}")

        sum_val = test_array.sum()
        assert sum_val == 20, "array.sum() failed"
        print(f"✅ array.sum()         OK: {sum_val}")

        # Test var (doit toujours fonctionner)
        from numpy import var

        variance = var([1, 2, 3, 4, 5])
        print(f"✅ var()               OK: {variance:.2f}")

        return True
    except VALIDATION_NUMPY_ERRORS as e:
        print(f"❌ NumPy functionality FAILED: {e}")
        return False


def main():
    """Fonction principale."""
    print("=" * 60)
    print(" Validation Migration Python 3.13/3.14 + PySide6")
    print("=" * 60)

    print(f"\nPython version: {sys.version}")
    print(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n")

    # Vérifier compatibilité Python
    if sys.version_info >= (3, 13):
        print(f"✅ Python 3.{sys.version_info.minor} compatible avec migration\n")
    else:
        print(f"⚠️  Python 3.{sys.version_info.minor} - Migration ciblée pour 3.13+\n")

    print("=== Vérification des Versions ===\n")

    # Dépendances déclarées dans pyproject.toml. Les minima suivent cette
    # déclaration : un écart ici ferait échouer une installation conforme.
    all_ok = True
    all_ok &= check_version("numpy", "2.1.0", "NumPy")
    all_ok &= check_version("PySide6", "6.8.1", "PySide6")
    all_ok &= check_version("pyqtgraph", "0.13.0", "pyqtgraph")
    all_ok &= check_version("pandas", "2.2.2", "pandas")
    all_ok &= check_version("aiohttp", "3.13.2", "aiohttp")

    # Test imports
    imports_ok = check_imports()
    all_ok &= imports_ok

    # Test fonctionnalités NumPy
    numpy_ok = check_numpy_functionality()
    all_ok &= numpy_ok

    # Résumé
    print("\n" + "=" * 60)
    if all_ok:
        print("✅ VALIDATION RÉUSSIE - Migration compatible")
        print("=" * 60)
        return 0
    else:
        print("❌ VALIDATION ÉCHOUÉE - Vérifier les erreurs ci-dessus")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
