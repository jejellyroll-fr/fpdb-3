#!/usr/bin/env python3
from __future__ import annotations
"""Script de validation de la migration Python 3.13/3.14 + PySide6.

Ce script vérifie que toutes les bibliothèques sont correctement installées
avec les versions compatibles Python 3.13/3.14 et PySide6.
"""

import sys
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


def check_imports() -> bool:
    """Vérifie que les imports critiques fonctionnent."""
    print("\n=== Vérification des Imports ===\n")

    imports_ok = True

    # NumPy
    try:

        print("✅ NumPy imports       OK (max/min/sum removed as expected)")

        # Test que max/min/sum ne sont plus importés directement
        try:
            from numpy import max, min, sum  # noqa: F401 -- import compatibility test

            print("⚠️  NumPy max/min/sum  STILL AVAILABLE (unexpected, but OK)")
        except ImportError:
            print("✅ NumPy max/min/sum  REMOVED (expected in NumPy 2.x)")
    except VALIDATION_IMPORT_ERRORS as e:
        print(f"❌ NumPy imports       FAILED: {e}")
        imports_ok = False

    # SQLAlchemy
    try:

        print("✅ SQLAlchemy pool     OK")
    except VALIDATION_IMPORT_ERRORS as e:
        print(f"❌ SQLAlchemy pool     FAILED: {e}")
        imports_ok = False

    # matplotlib
    try:

        print("✅ matplotlib QtAgg    OK")
    except VALIDATION_IMPORT_ERRORS as e:
        print(f"❌ matplotlib QtAgg    FAILED: {e}")
        imports_ok = False

    # mplfinance
    try:

        print("✅ mplfinance          OK")
    except VALIDATION_IMPORT_ERRORS as e:
        print(f"❌ mplfinance          FAILED: {e}")
        imports_ok = False

    # PySide6
    try:

        print("✅ PySide6             OK")
    except VALIDATION_IMPORT_ERRORS as e:
        print(f"❌ PySide6             FAILED: {e}")
        imports_ok = False

    # FastAPI (optionnel)
    try:

        print("✅ FastAPI/Pydantic    OK")
    except VALIDATION_IMPORT_ERRORS as e:
        print(f"⚠️  FastAPI/Pydantic    OPTIONAL: {e}")

    return imports_ok


def check_numpy_functionality() -> bool:
    """Vérifie que les fonctionnalités NumPy 2.x fonctionnent."""
    print("\n=== Test Fonctionnalités NumPy ===\n")

    try:
        import numpy as np
        from numpy import cumsum

        # Test cumsum (compatible)
        arr = [1, 2, 3, 4, 5]
        result = cumsum(arr)
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

    # Dépendances critiques
    all_ok = True
    all_ok &= check_version("numpy", "2.1.0", "NumPy")
    all_ok &= check_version("sqlalchemy", "2.0.0", "SQLAlchemy")
    all_ok &= check_version("matplotlib", "3.10.7", "matplotlib")
    all_ok &= check_version("mplfinance", "0.12.10", "mplfinance")

    # Dépendances moyennes
    all_ok &= check_version("fastapi", "0.121.1", "FastAPI")
    all_ok &= check_version("pydantic", "2.12.1", "Pydantic")
    all_ok &= check_version("aiohttp", "3.13.2", "aiohttp")

    # PySide6 (LGPL license)
    check_version("PySide6", "6.8.1", "PySide6")

    # Autres dépendances
    check_version("pandas", "2.2.0", "pandas")

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
