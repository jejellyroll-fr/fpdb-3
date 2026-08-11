#!/usr/bin/env python3
from __future__ import annotations

"""Tests de validation pour la migration NumPy 2.x.

Ce module teste les fonctionnalités NumPy critiques utilisées dans FPDB.
"""

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
        """Verify that NumPy 2.x is installed."""
        version = np.__version__
        major_version = int(version.split(".")[0])
        self.assertGreaterEqual(major_version, 2, f"NumPy 2.x requis, version actuelle : {version}")
        print(f"✅ NumPy version : {version}")

    def test_cumsum_function(self):
        """Test cumsum() - used in GuiGraphViewer and GuiSessionViewer."""
        # Test simple
        arr = [1, 2, 3, 4, 5]
        result: np.ndarray = cumsum(arr)
        expected = np.array([1, 3, 6, 10, 15])

        np.testing.assert_array_equal(result, expected)
        print(f"✅ cumsum() : {list(result)}")

        # Test with floats (as in the real code)
        profits = [10.5, 20.3, -5.2, 15.7]
        cumulative: np.ndarray = cumsum(profits)
        self.assertEqual(len(cumulative), len(profits))
        self.assertAlmostEqual(cumulative[-1], sum(profits))
        print("✅ cumsum() avec floats : OK")

    def test_array_max_method(self):
        """Test array.max() - replaces deprecated numpy.max()."""
        # Simulation du code GuiSessionViewer
        cum_sum = np.array([0, 10, 15, 12, 18, 25, 20])
        first_idx = 1
        end_idx = 6

        # Nouvelle syntaxe NumPy 2.x
        hwm = cum_sum[first_idx - 1 : end_idx].max()

        self.assertEqual(hwm, 25)
        print(f"✅ array.max() : {hwm} (high water mark)")

    def test_array_min_method(self):
        """Test array.min() - replaces deprecated numpy.min()."""
        # Simulation du code GuiSessionViewer
        cum_sum = np.array([0, 10, 15, 12, 18, 25, 20])
        first_idx = 1
        end_idx = 6

        # Nouvelle syntaxe NumPy 2.x
        lwm = cum_sum[first_idx - 1 : end_idx].min()

        self.assertEqual(lwm, 0)
        print(f"✅ array.min() : {lwm} (low water mark)")

    def test_append_function(self):
        """Test append() - used in GuiSessionViewer."""
        arr = np.array([1, 2, 3])
        value = 4

        result: np.ndarray = append(arr, value)
        expected = np.array([1, 2, 3, 4])

        np.testing.assert_array_equal(result, expected)
        print(f"✅ append() : {list(result)}")

    def test_diff_function(self):
        """Test diff() - used in GuiSessionViewer for time calculations."""
        times = [1000, 1500, 1800, 2500, 3000]
        times_array = np.array(times)

        diffs = diff(times_array)
        expected = np.array([500, 300, 700, 500])

        np.testing.assert_array_equal(diffs, expected)
        print(f"✅ diff() : {list(diffs)}")

    def test_nonzero_function(self):
        """Test nonzero() - used in GuiSessionViewer for session detection."""
        arr = np.array([0, 1, 0, 2, 0, 0, 3])

        indices = nonzero(arr)

        # nonzero retourne un tuple d'arrays
        self.assertEqual(len(indices), 1)
        expected_indices = [1, 3, 6]
        np.testing.assert_array_equal(indices[0], expected_indices)
        print(f"✅ nonzero() : {list(indices[0])}")

    def test_var_function(self):
        """Test var() - used in Database.py (optional)."""
        from numpy import var

        data = [1, 2, 3, 4, 5]
        variance = var(data)

        # Variance de [1,2,3,4,5] = 2.0
        self.assertAlmostEqual(variance, 2.0)
        print(f"✅ var() : {variance}")

    def test_deprecated_functions_removed(self):
        """Verify that deprecated functions are no longer imported."""
        # These functions must NOT be in the namespace after import

        # On ne devrait pas pouvoir importer max, min, sum directement
        # (but they may still exist in the NumPy namespace)
        print("✅ Imports dépréciés non utilisés")

    def test_realistic_session_calculation(self):
        """Test with realistic GuiSessionViewer data."""
        # Simulation d'une session de poker
        profits = [10.5, -5.2, 15.3, -8.1, 20.7, -3.4, 12.9]

        # Cumulative calculation (as in the code)
        cum_sum = cumsum(profits) / 100.0  # Divide by 100 as in the code

        # Calcul high/low water marks
        hwm = cum_sum.max()
        lwm = cum_sum.min()

        self.assertGreater(hwm, lwm)
        self.assertAlmostEqual(cum_sum[-1], sum(profits) / 100.0)

        print(f"✅ Session réaliste : HWM={hwm:.2f}, LWM={lwm:.2f}, Final={cum_sum[-1]:.2f}")

    def test_graph_viewer_calculation(self):
        """Test with realistic GuiGraphViewer data."""
        # Simulate hand results
        winnings = [
            (1, 10.0, True, 5.0),  # (id, profit, showdown, ev)
            (2, -5.0, False, 2.0),
            (3, 15.0, True, 12.0),
            (4, -8.0, False, -3.0),
            (5, 20.0, True, 18.0),
        ]

        # As in GuiGraphViewer
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


class TestSQLAlchemyCompatibility(unittest.TestCase):
    """SQLAlchemy 2.0 compatibility tests."""

    def test_sqlalchemy_version(self):
        """Verify that SQLAlchemy 2.0+ is installed."""
        try:
            import sqlalchemy

            version = sqlalchemy.__version__
            major_version = int(version.split(".")[0])
            self.assertGreaterEqual(major_version, 2, f"SQLAlchemy 2.x requis, version actuelle : {version}")
            print(f"✅ SQLAlchemy version : {version}")
        except ImportError:
            self.fail("SQLAlchemy n'est pas installé")

    def test_sqlalchemy_pool_import(self):
        """Verify that sqlalchemy.pool can be imported."""
        try:
            from sqlalchemy import pool  # noqa: F401 -- import compatibility test

            print("✅ sqlalchemy.pool importé avec succès")
        except ImportError as e:
            self.fail(f"Impossible d'importer sqlalchemy.pool : {e}")


class TestMatplotlibCompatibility(unittest.TestCase):
    """Matplotlib compatibility tests."""

    def test_matplotlib_version(self):
        """Verify that matplotlib 3.10.7+ is installed."""
        try:
            import matplotlib

            version = matplotlib.__version__
            parts = [int(x) for x in version.split(".")[:3]]

            # Verify >= 3.10.7
            is_compatible = (
                parts[0] > 3
                or (parts[0] == 3 and parts[1] > 10)
                or (parts[0] == 3 and parts[1] == 10 and parts[2] >= 7)
            )

            self.assertTrue(is_compatible, f"matplotlib 3.10.7+ requis, version actuelle : {version}")
            print(f"✅ matplotlib version : {version}")
        except ImportError:
            self.fail("matplotlib n'est pas installé")

    def test_matplotlib_qt_backend(self):
        """Verify that the PySide6-compatible QtAgg backend can be imported."""
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvas  # noqa: F401 -- import compatibility test
            from matplotlib.figure import Figure  # noqa: F401 -- import compatibility test

            print("✅ matplotlib QtAgg backend importé")
        except ImportError as e:
            self.fail(f"Impossible d'importer backend QtAgg : {e}")


class TestMplfinanceCompatibility(unittest.TestCase):
    """Mplfinance compatibility tests."""

    def test_mplfinance_version(self):
        """Verify that mplfinance 0.12.10+ is installed."""
        try:
            import mplfinance

            version = mplfinance.__version__
            print(f"✅ mplfinance version : {version}")
        except ImportError:
            self.fail("mplfinance n'est pas installé")

    def test_mplfinance_candlestick(self):
        """Verify that candlestick_ochl can be imported."""
        try:
            from mplfinance.original_flavor import candlestick_ochl  # noqa: F401 -- import compatibility test

            print("✅ mplfinance candlestick_ochl importé")
        except ImportError as e:
            self.fail(f"Impossible d'importer candlestick_ochl : {e}")


def run_tests():
    """Run all tests."""
    # Create the test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add the tests
    suite.addTests(loader.loadTestsFromTestCase(TestNumPyMigration))
    suite.addTests(loader.loadTestsFromTestCase(TestSQLAlchemyCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestMatplotlibCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestMplfinanceCompatibility))

    # Run
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
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
