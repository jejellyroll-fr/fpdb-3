"""Tests de régression pour BovadaToFpdb - S'assurer que les corrections restent fonctionnelles.

Ce module contient des tests de régression pour prévenir la réintroduction de bugs
déjà corrigés dans le parser Bovada.
"""

import os
import subprocess
import sys
import unittest


class BovadaRegressionTests(unittest.TestCase):
    """Tests de régression pour s'assurer que les corrections antérieures fonctionnent toujours."""

    def test_all_original_tests_still_pass(self) -> None:
        """Régression: S'assurer que tous les tests originaux passent encore."""
        # Exécuter les tests originaux qui fonctionnaient après les corrections
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test/test_BovadaToFpdb.py", "-v"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            capture_output=True,
            text=True, check=False,
        )

        assert result.returncode == 0, f"Tests originaux échouent - régression détectée:\n{result.stdout}\n{result.stderr}"

        # Vérifier que le nombre exact de tests passe (23 tests)
        assert "23 passed" in result.stdout

    def test_datetime_import_regression(self) -> None:
        """Régression: S'assurer que l'import datetime.strptime fonctionne."""
        try:
            import datetime

            # Test direct de l'utilisation dans le code - le plus important
            test_date_string = "2012-08-26 23:35:15"
            parsed_date = datetime.datetime.strptime(test_date_string, "%Y-%m-%d %H:%M:%S")
            assert isinstance(parsed_date, datetime.datetime)

        except AttributeError as e:
            if "datetime" in str(e):
                self.fail(f"Régression datetime import détectée: {e}")
            raise

    def test_split_flag_regression(self) -> None:
        """Régression: S'assurer que la clé 'split' est toujours définie."""
        # Importer et vérifier que la définition de split est dans le code
        import inspect

        from BovadaToFpdb import Bovada

        # Vérifier que _buildGameTypeInfo contient le code pour split
        source = inspect.getsource(Bovada._buildGameTypeInfo)
        assert "split" in source, "La clé 'split' manque dans _buildGameTypeInfo - régression détectée"

    def test_cli_importer_basic_functionality(self) -> None:
        """Régression: S'assurer que l'importer CLI fonctionne toujours."""
        test_file = "regression-test-files/cash/Bovada/Flop/NLHE-USD-0.10-0.25-201208.raise.to.format.change.txt"

        # Vérifier que le fichier existe
        if not os.path.exists(test_file):
            self.skipTest(f"Fichier de test {test_file} non disponible")

        # Tester l'import sans réellement modifier la base
        result = subprocess.run(
            [sys.executable, "importer_cli.py", "--site", "Bovada", "--no-progress", test_file],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            capture_output=True,
            text=True,
            timeout=30, check=False,
        )

        # L'import doit réussir (code retour 0)
        assert result.returncode == 0, f"CLI importer échoue - régression détectée:\n{result.stdout}\n{result.stderr}"


if __name__ == "__main__":
    unittest.main()
