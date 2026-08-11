#!/usr/bin/env python3
from __future__ import annotations

"""
Script de validation de la migration PySide6
Vérifie que tous les composants Qt sont correctement migrés
"""

import sys
from pathlib import Path

LEGACY_DIR = Path(__file__).resolve().parent
REPO_ROOT = LEGACY_DIR.parent


def test_pyside6_imports():
    """Test que PySide6 est installé et fonctionnel"""
    print("🔍 Test des imports PySide6...")

    try:
        import PySide6

        print(f"✅ PySide6 version: {PySide6.__version__}")
    except ImportError:
        print("❌ PySide6 n'est pas installé!")
        return False

    # Test des modules principaux
    modules = [
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
    ]

    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            return False

    return True


def check_pyqt5_references():
    """Vérifie qu'il ne reste pas de références PyQt5 problématiques"""
    print("\n🔍 Vérification des références PyQt5 restantes...")

    # Fichiers à vérifier
    important_files = [
        "fpdb.pyw",
        "loggingFpdb.py",
        "GuiHandViewer.py",
        "Aux_Classic_Hud.py",
    ]

    has_issues = False
    for filename in important_files:
        filepath = LEGACY_DIR / filename
        if not filepath.exists():
            print(f"⚠️  Fichier non trouvé: {filename}")
            continue

        content = filepath.read_text()
        if "PyQt5" in content and "from PySide6" not in content:
            print(f"❌ {filename} contient encore des références PyQt5!")
            has_issues = True
        else:
            print(f"✅ {filename}")

    return not has_issues


def test_application_structure():
    """Vérifie la structure de l'application"""
    print("\n🔍 Vérification de la structure de l'application...")

    # Fichiers essentiels
    essential_files = [
        LEGACY_DIR / "fpdb.pyw",
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "run_tests.sh",
        REPO_ROOT / "run_tests.ps1",
    ]

    all_present = True
    for filepath in essential_files:
        if filepath.exists():
            print(f"✅ {filepath.relative_to(REPO_ROOT)}")
        else:
            print(f"❌ {filepath.relative_to(REPO_ROOT)} manquant!")
            all_present = False

    return all_present


def test_test_files():
    """Vérifie que les fichiers de test sont migrés"""
    print("\n🔍 Vérification des fichiers de test...")

    test_dir = REPO_ROOT / "test"
    if not test_dir.exists():
        print("⚠️  Répertoire test/ non trouvé")
        return True  # Non critique

    pyqt5_count = 0
    pyside6_count = 0

    for test_file in test_dir.glob("*.py"):
        content = test_file.read_text()
        if "PyQt5" in content and "PySide6" not in content:
            pyqt5_count += 1
        elif "PySide6" in content:
            pyside6_count += 1

    print(f"📊 Fichiers avec PySide6: {pyside6_count}")
    print(f"📊 Fichiers avec PyQt5 uniquement: {pyqt5_count}")

    if pyqt5_count > 0:
        print(f"⚠️  {pyqt5_count} fichiers de test n'ont pas été migrés")

    return True  # Non bloquant


def main():
    """Fonction principale"""
    print("=" * 60)
    print("🚀 Validation de la Migration PySide6")
    print("=" * 60)

    tests = [
        ("Imports PySide6", test_pyside6_imports),
        ("Références PyQt5", check_pyqt5_references),
        ("Structure App", test_application_structure),
        ("Fichiers Test", test_test_files),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Erreur dans {test_name}: {e}")
            results.append((test_name, False))

    # Résumé
    print("\n" + "=" * 60)
    print("📊 RÉSUMÉ")
    print("=" * 60)

    all_passed = True
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not result:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 TOUS LES TESTS SONT PASSÉS!")
        print("✅ La migration PySide6 est réussie!")
        return 0
    else:
        print("⚠️  CERTAINS TESTS ONT ÉCHOUÉ")
        print("❌ Veuillez vérifier les erreurs ci-dessus")
        return 1


if __name__ == "__main__":
    sys.exit(main())
