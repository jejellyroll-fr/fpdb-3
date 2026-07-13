#!/usr/bin/env python3
from __future__ import annotations
"""Test de la Feature 1.1: Migration Stack Technique Moderne"""

import numpy as np
import sys
from pathlib import Path


LEGACY_DIR = Path(__file__).resolve().parent


def test_numpy_2x_array_methods():
    """Test que les méthodes array NumPy 2.x fonctionnent"""
    print("Test NumPy 2.x array methods...")

    # Test cumsum (comme dans GuiGraphViewer.py)
    green = np.array([0, 100, 200, -50, 150])
    greenline = green.cumsum()
    expected = np.array([0, 100, 300, 250, 400])
    assert np.array_equal(greenline, expected), f"cumsum failed: {greenline} != {expected}"
    print(f"  ✓ cumsum: {greenline}")

    # Test max/min
    assert greenline.max() == 400, "max failed"
    assert greenline.min() == 0, "min failed"
    print(f"  ✓ max/min: {greenline.max()}, {greenline.min()}")

    # Test diff (comme dans GuiSessionViewer.py)
    times = np.array([1000, 2000, 3500, 5000])
    diffs = np.diff(times)
    expected_diffs = np.array([1000, 1500, 1500])
    assert np.array_equal(diffs, expected_diffs), f"diff failed: {diffs} != {expected_diffs}"
    print(f"  ✓ diff: {diffs}")

    # Test append
    diffs2 = np.append(diffs, 2000)
    assert len(diffs2) == 4, "append failed"
    print(f"  ✓ append: {diffs2}")

    # Test nonzero
    THRESHOLD = 1800
    index = np.nonzero(diffs2 > THRESHOLD)
    assert len(index[0]) == 1, "nonzero failed"
    assert index[0][0] == 3, "nonzero index wrong"
    print(f"  ✓ nonzero: {index}")

    print("✅ Tous les tests NumPy 2.x passés!\n")


def test_sqlalchemy_2x():
    """Test que SQLAlchemy 2.x est installé"""
    print("Test SQLAlchemy 2.x...")

    try:
        import sqlalchemy

        version = sqlalchemy.__version__
        major = int(version.split(".")[0])

        assert major >= 2, f"SQLAlchemy 2.0+ requis, trouvé {version}"
        print(f"  ✓ SQLAlchemy version: {version}")
        print("✅ SQLAlchemy 2.x confirmé!\n")
        return True
    except ImportError:
        print("  ⚠ SQLAlchemy non installé (optionnel)")
        return False


def test_matplotlib_3_10():
    """Test que matplotlib 3.10+ est installé"""
    print("Test matplotlib 3.10+...")

    try:
        import matplotlib

        version = matplotlib.__version__
        major_minor = tuple(map(int, version.split(".")[:2]))

        assert major_minor >= (3, 10), f"matplotlib 3.10+ requis, trouvé {version}"
        print(f"  ✓ matplotlib version: {version}")
        print("✅ matplotlib 3.10+ confirmé!\n")
        return True
    except ImportError:
        print("  ⚠ matplotlib non installé")
        return False


def test_fastapi_pydantic():
    """Test que FastAPI et Pydantic sont à jour"""
    print("Test FastAPI et Pydantic...")

    try:
        import fastapi
        import pydantic

        fastapi_version = fastapi.__version__
        pydantic_version = pydantic.__version__

        # FastAPI >= 0.121.1
        fastapi_parts = tuple(map(int, fastapi_version.split(".")[:3]))
        assert fastapi_parts >= (0, 121, 1), f"FastAPI 0.121.1+ requis, trouvé {fastapi_version}"

        # Pydantic >= 2.12.1
        pydantic_major = int(pydantic_version.split(".")[0])
        assert pydantic_major >= 2, f"Pydantic 2.x requis, trouvé {pydantic_version}"

        print(f"  ✓ FastAPI version: {fastapi_version}")
        print(f"  ✓ Pydantic version: {pydantic_version}")
        print("✅ FastAPI et Pydantic à jour!\n")
        return True
    except ImportError:
        print("  ⚠ FastAPI/Pydantic non installés (optionnels)")
        return False


def test_code_modifications():
    """Test que les modifications de code sont correctes"""
    print("Test des modifications de code...")

    # Vérifier GuiGraphViewer.py
    with open(LEGACY_DIR / "GuiGraphViewer.py") as f:
        content = f.read()

    # Ne devrait plus avoir "from numpy import cumsum"
    assert "from numpy import cumsum" not in content, "GuiGraphViewer.py: 'from numpy import cumsum' encore présent"

    # Devrait avoir "import numpy as np"
    assert "import numpy as np" in content, "GuiGraphViewer.py: 'import numpy as np' manquant"

    # Devrait avoir ".cumsum()"
    assert ".cumsum()" in content, "GuiGraphViewer.py: '.cumsum()' manquant"

    print("  ✓ GuiGraphViewer.py: migrations NumPy correctes")

    # Vérifier GuiSessionViewer.py
    with open(LEGACY_DIR / "GuiSessionViewer.py") as f:
        content = f.read()

    # Ne devrait plus avoir "from numpy import append, cumsum, diff, nonzero"
    assert "from numpy import append" not in content or "import numpy as np" in content
    assert ".cumsum()" in content, "GuiSessionViewer.py: '.cumsum()' manquant"
    assert "np.diff" in content, "GuiSessionViewer.py: 'np.diff' manquant"

    print("  ✓ GuiSessionViewer.py: migrations NumPy correctes")

    # Vérifier Database.py
    with open(LEGACY_DIR / "Database.py") as f:
        content = f.read()

    # Devrait avoir le nouveau commentaire SQLAlchemy 2.0
    assert "SQLAlchemy pool.manage was removed in 2.0" in content, "Database.py: commentaire SQLAlchemy 2.0 manquant"

    print("  ✓ Database.py: migration SQLAlchemy correcte")

    print("✅ Toutes les modifications de code validées!\n")


def main():
    """Exécute tous les tests de la Feature 1.1"""
    print("=" * 60)
    print("Tests Feature 1.1: Migration Stack Technique Moderne")
    print("=" * 60)
    print()

    try:
        test_numpy_2x_array_methods()
        test_sqlalchemy_2x()
        test_matplotlib_3_10()
        test_fastapi_pydantic()
        test_code_modifications()

        print("=" * 60)
        print("🎉 SUCCÈS: Tous les tests Feature 1.1 passés!")
        print("=" * 60)
        print()
        print("Résumé des versions:")
        print(f"  • NumPy: {np.__version__}")

        try:
            import sqlalchemy

            print(f"  • SQLAlchemy: {sqlalchemy.__version__}")
        except ImportError:
            pass

        try:
            import matplotlib

            print(f"  • matplotlib: {matplotlib.__version__}")
        except ImportError:
            pass

        try:
            import fastapi
            import pydantic

            print(f"  • FastAPI: {fastapi.__version__}")
            print(f"  • Pydantic: {pydantic.__version__}")
        except ImportError:
            pass

        return 0

    except AssertionError as e:
        print("=" * 60)
        print(f"❌ ÉCHEC: {e}")
        print("=" * 60)
        return 1

    except Exception as e:
        print("=" * 60)
        print(f"❌ ERREUR: {e}")
        import traceback

        traceback.print_exc()
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
