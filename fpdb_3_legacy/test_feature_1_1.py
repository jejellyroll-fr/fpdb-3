#!/usr/bin/env python3
"""Test de la Feature 1.1: Migration Stack Technique Moderne.

Les vérifications renvoyaient ``True``/``False`` et ``main()`` jetait ce
résultat : le script annonçait « SUCCÈS: Tous les tests passés » quel que soit
l'état des dépendances. Un contrôle dont le verdict est ignoré ne contrôle
rien, d'où la séparation explicite ci-dessous entre requis et optionnel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

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
    diffs2: np.ndarray = np.append(diffs, 2000)
    assert len(diffs2) == 4, "append failed"
    print(f"  ✓ append: {diffs2}")

    # Test nonzero
    THRESHOLD = 1800
    index = np.nonzero(diffs2 > THRESHOLD)
    assert len(index[0]) == 1, "nonzero failed"
    assert index[0][0] == 3, "nonzero index wrong"
    print(f"  ✓ nonzero: {index}")

    print("✅ Tous les tests NumPy 2.x passés!\n")


def test_pyqtgraph():
    """Test que PyQtGraph, moteur de rendu des graphiques, est utilisable.

    Ajouté parce qu'il ne l'était pas : c'est la bibliothèque qui dessine tous
    les graphiques depuis #228, et la seule dépendance critique que rien ne
    vérifiait.
    """
    print("Test PyQtGraph...")

    import pyqtgraph as pg

    version = pg.__version__
    major_minor = tuple(map(int, version.split(".")[:2]))

    assert major_minor >= (0, 13), f"pyqtgraph 0.13+ requis, trouvé {version}"
    assert hasattr(pg, "PlotWidget"), "pyqtgraph.PlotWidget introuvable"
    print(f"  ✓ pyqtgraph version: {version}")
    print("✅ PyQtGraph confirmé!\n")


def test_sqlalchemy_2x():
    """Test que SQLAlchemy, s'il est présent, est en 2.x.

    Dépendance optionnelle : ``Database.py`` la sonde derrière un
    ``try``/``except`` et n'est déclarée dans aucune section de
    ``pyproject.toml``. Une absence -- ou une version trop ancienne -- est
    signalée, jamais fatale.

    Returns:
        True si utilisable, False sinon. Le verdict est repris par ``main()``.
    """
    print("Test SQLAlchemy 2.x (optionnel)...")

    try:
        import sqlalchemy
    except ImportError:
        print("  ⚠ SQLAlchemy non installé (optionnel)\n")
        return False

    version = sqlalchemy.__version__
    major = int(version.split(".")[0])
    if major < 2:
        print(f"  ⚠ SQLAlchemy 2.0+ attendu, trouvé {version} (optionnel)\n")
        return False

    print(f"  ✓ SQLAlchemy version: {version}")
    print("✅ SQLAlchemy 2.x confirmé!\n")
    return True


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

    # Ne devrait plus avoir "from numpy import append, cumsum, diff, nonzero".
    # L'ancienne forme "A not in content or B in content" était satisfaite dès
    # que le module importait numpy, donc n'interdisait rien.
    assert "from numpy import append" not in content, "GuiSessionViewer.py: 'from numpy import append' encore présent"
    assert "import numpy as np" in content, "GuiSessionViewer.py: 'import numpy as np' manquant"
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
        # Requis : une défaillance lève une AssertionError, reprise plus bas.
        test_numpy_2x_array_methods()
        test_pyqtgraph()
        test_code_modifications()

        # Optionnel : le verdict est rapporté, pas jeté.
        sqlalchemy_ok = test_sqlalchemy_2x()

        print("=" * 60)
        print("🎉 SUCCÈS: Tous les tests Feature 1.1 passés!")
        print("=" * 60)
        print()
        print("Résumé des versions:")
        print(f"  • NumPy: {np.__version__}")

        import pyqtgraph as pg

        print(f"  • pyqtgraph: {pg.__version__}")

        if sqlalchemy_ok:
            import sqlalchemy

            print(f"  • SQLAlchemy: {sqlalchemy.__version__}")
        else:
            print("  • SQLAlchemy: absent ou < 2.x (optionnel, non bloquant)")

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
