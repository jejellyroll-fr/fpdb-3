#!/usr/bin/env python3
"""Tests de validation pour la migration NumPy 2.x.

Ce module teste les fonctionnalités NumPy critiques utilisées dans FPDB.

Une dépendance optionnelle absente doit provoquer un *skip*, jamais un échec :
appeler ``self.fail()`` faisait échouer ce script sur une installation
parfaitement conforme, SQLAlchemy n'étant requis nulle part.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from numpy import append, cumsum, diff, nonzero


class TestNumPyMigration(unittest.TestCase):
    """Tests de validation de la migration NumPy 2.x."""

    def test_numpy_version(self):
        """Vérifie que NumPy 2.x est installé."""
        version = np.__version__
        major_version = int(version.split(".")[0])
        self.assertGreaterEqual(major_version, 2, f"NumPy 2.x requis, version actuelle : {version}")
        print(f"✅ NumPy version : {version}")

    def test_cumsum_function(self):
        """Test cumsum() - utilisé dans GuiGraphViewer et GuiSessionViewer."""
        # Test simple
        arr = [1, 2, 3, 4, 5]
        result: np.ndarray = cumsum(arr)
        expected = np.array([1, 3, 6, 10, 15])

        np.testing.assert_array_equal(result, expected)
        print(f"✅ cumsum() : {list(result)}")

        # Test avec floats (comme dans le code réel)
        profits = [10.5, 20.3, -5.2, 15.7]
        cumulative: np.ndarray = cumsum(profits)
        self.assertEqual(len(cumulative), len(profits))
        self.assertAlmostEqual(cumulative[-1], sum(profits))
        print("✅ cumsum() avec floats : OK")

    def test_array_max_method(self):
        """Test array.max() - remplace numpy.max() déprécié."""
        # Simulation du code GuiSessionViewer
        cum_sum = np.array([0, 10, 15, 12, 18, 25, 20])
        first_idx = 1
        end_idx = 6

        # Nouvelle syntaxe NumPy 2.x
        hwm = cum_sum[first_idx - 1 : end_idx].max()

        self.assertEqual(hwm, 25)
        print(f"✅ array.max() : {hwm} (high water mark)")

    def test_array_min_method(self):
        """Test array.min() - remplace numpy.min() déprécié."""
        # Simulation du code GuiSessionViewer
        cum_sum = np.array([0, 10, 15, 12, 18, 25, 20])
        first_idx = 1
        end_idx = 6

        # Nouvelle syntaxe NumPy 2.x
        lwm = cum_sum[first_idx - 1 : end_idx].min()

        self.assertEqual(lwm, 0)
        print(f"✅ array.min() : {lwm} (low water mark)")

    def test_append_function(self):
        """Test append() - utilisé dans GuiSessionViewer."""
        arr = np.array([1, 2, 3])
        value = 4

        result: np.ndarray = append(arr, value)
        expected = np.array([1, 2, 3, 4])

        np.testing.assert_array_equal(result, expected)
        print(f"✅ append() : {list(result)}")

    def test_diff_function(self):
        """Test diff() - utilisé dans GuiSessionViewer pour calculs de temps."""
        times = [1000, 1500, 1800, 2500, 3000]
        times_array = np.array(times)

        diffs = diff(times_array)
        expected = np.array([500, 300, 700, 500])

        np.testing.assert_array_equal(diffs, expected)
        print(f"✅ diff() : {list(diffs)}")

    def test_nonzero_function(self):
        """Test nonzero() - utilisé dans GuiSessionViewer pour détection sessions."""
        arr = np.array([0, 1, 0, 2, 0, 0, 3])

        indices = nonzero(arr)

        # nonzero retourne un tuple d'arrays
        self.assertEqual(len(indices), 1)
        expected_indices = [1, 3, 6]
        np.testing.assert_array_equal(indices[0], expected_indices)
        print(f"✅ nonzero() : {list(indices[0])}")

    def test_var_function(self):
        """Test var() - utilisé dans Database.py (optionnel)."""
        from numpy import var

        data = [1, 2, 3, 4, 5]
        variance = var(data)

        # Variance de [1,2,3,4,5] = 2.0
        self.assertAlmostEqual(variance, 2.0)
        print(f"✅ var() : {variance}")

    def test_deprecated_functions_removed(self):
        """Vérifie que les modules migrés n'importent plus max/min/sum de NumPy.

        La version précédente de ce test n'affirmait rien : elle affichait un
        ``✅`` sans rien vérifier. Sa prémisse était de surcroît fausse -- NumPy
        2.x exporte toujours ``max``/``min``/``sum``. L'invariant réel de la
        migration porte sur le code de FPDB, qui doit utiliser les méthodes de
        tableau, et c'est lui qui est vérifié ici.
        """
        legacy_dir = Path(__file__).resolve().parent
        for module in ("GuiGraphViewer.py", "GuiSessionViewer.py"):
            content = (legacy_dir / module).read_text(encoding="utf-8")
            for name in ("max", "min", "sum"):
                self.assertNotIn(
                    f"from numpy import {name}",
                    content,
                    f"{module} importe encore numpy.{name} au lieu de la méthode de tableau",
                )
        print("✅ Imports dépréciés non utilisés")

    def test_realistic_session_calculation(self):
        """Test avec données réalistes de GuiSessionViewer."""
        # Simulation d'une session de poker
        profits = [10.5, -5.2, 15.3, -8.1, 20.7, -3.4, 12.9]

        # Calcul cumulatif (comme dans le code)
        cum_sum = cumsum(profits) / 100.0  # Division par 100 comme dans le code

        # Calcul high/low water marks
        hwm = cum_sum.max()
        lwm = cum_sum.min()

        self.assertGreater(hwm, lwm)
        self.assertAlmostEqual(cum_sum[-1], sum(profits) / 100.0)

        print(f"✅ Session réaliste : HWM={hwm:.2f}, LWM={lwm:.2f}, Final={cum_sum[-1]:.2f}")

    def test_graph_viewer_calculation(self):
        """Test avec données réalistes de GuiGraphViewer."""
        # Simulation de résultats de mains
        winnings = [
            (1, 10.0, True, 5.0),  # (id, profit, showdown, ev)
            (2, -5.0, False, 2.0),
            (3, 15.0, True, 12.0),
            (4, -8.0, False, -3.0),
            (5, 20.0, True, 18.0),
        ]

        # Comme dans GuiGraphViewer
        green = [0] + [float(x[1]) for x in winnings]
        blue = [0] + [float(x[1]) if x[2] is True else 0.0 for x in winnings]
        red = [0] + [float(x[1]) if x[2] is False else 0.0 for x in winnings]
        orange = [0] + [float(x[3]) for x in winnings]

        # Calculs cumulatifs
        greenline: np.ndarray = cumsum(green)
        blueline: np.ndarray = cumsum(blue)
        redline: np.ndarray = cumsum(red)
        cumsum(orange)

        self.assertEqual(len(greenline), len(winnings) + 1)
        self.assertAlmostEqual(greenline[-1], sum([x[1] for x in winnings]))

        print(f"✅ GraphViewer : Green={greenline[-1]:.2f}, Blue={blueline[-1]:.2f}, Red={redline[-1]:.2f}")


HAS_SQLALCHEMY = importlib.util.find_spec("sqlalchemy") is not None


@unittest.skipUnless(HAS_SQLALCHEMY, "SQLAlchemy est une dépendance optionnelle (cf. Database.py)")
class TestSQLAlchemyCompatibility(unittest.TestCase):
    """Tests de compatibilité SQLAlchemy 2.0.

    ``Database.py`` sonde SQLAlchemy derrière un ``try``/``except`` et bascule
    sur ``use_sqlalchemy = False`` s'il manque ; il n'est déclaré dans aucune
    section de ``pyproject.toml``. Son absence est donc normale et se traduit
    par un skip, là où la version précédente appelait ``self.fail()`` et
    faisait échouer le script sur une installation saine.
    """

    def test_sqlalchemy_version(self):
        """Vérifie que SQLAlchemy, s'il est présent, est en 2.x."""
        import sqlalchemy

        version = sqlalchemy.__version__
        major_version = int(version.split(".")[0])
        self.assertGreaterEqual(major_version, 2, f"SQLAlchemy 2.x requis, version actuelle : {version}")
        print(f"✅ SQLAlchemy version : {version}")

    def test_sqlalchemy_pool_import(self):
        """Vérifie que sqlalchemy.pool peut être importé."""
        from sqlalchemy import pool  # noqa: F401 -- import compatibility test

        print("✅ sqlalchemy.pool importé avec succès")


def run_tests():
    """Exécute tous les tests."""
    # Créer la suite de tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Ajouter les tests. matplotlib et mplfinance ne figurent plus ici : aucun
    # code applicatif ne les importe depuis le passage à PyQtGraph (#228).
    suite.addTests(loader.loadTestsFromTestCase(TestNumPyMigration))
    suite.addTests(loader.loadTestsFromTestCase(TestSQLAlchemyCompatibility))

    # Exécuter
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Résumé
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ TOUS LES TESTS RÉUSSIS")
        print(f"   {result.testsRun} tests exécutés")
        print("=" * 70)
        return 0
    else:
        print("❌ CERTAINS TESTS ONT ÉCHOUÉ")
        print(f"   Tests exécutés : {result.testsRun}")
        print(f"   Échecs : {len(result.failures)}")
        print(f"   Erreurs : {len(result.errors)}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
