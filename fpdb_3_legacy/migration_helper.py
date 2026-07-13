#!/usr/bin/env python3
from __future__ import annotations
"""Helper interactif pour la migration Python 3.13/3.14.

Ce script guide l'utilisateur à travers le processus de migration
avec des menus interactifs et des actions automatiques.
"""

import subprocess
import sys
from pathlib import Path

MIGRATION_HELPER_COMMAND_ERRORS = (OSError,)


class Colors:
    """ANSI color codes."""

    BLUE = "\033[0;34m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"  # No Color
    BOLD = "\033[1m"


def print_header(text: str):
    """Print a header."""
    print(f"\n{Colors.BLUE}{'=' * 70}{Colors.NC}")
    print(f"{Colors.BOLD}{text}{Colors.NC}")
    print(f"{Colors.BLUE}{'=' * 70}{Colors.NC}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.NC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}❌ {text}{Colors.NC}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.NC}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.NC}")


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print_info(f"{description}...")
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode == 0:
            print_success(f"{description} - OK")
            return True
        else:
            print_error(f"{description} - ÉCHEC")
            return False
    except MIGRATION_HELPER_COMMAND_ERRORS as e:
        print_error(f"{description} - ERREUR: {e}")
        return False


def show_main_menu():
    """Display main menu."""
    print_header("Assistant de Migration Python 3.13/3.14 - FPDB-3")

    print(f"{Colors.BOLD}Menu Principal:{Colors.NC}\n")
    print("1. 📋 Afficher le statut de la migration")
    print("2. 🔍 Valider l'installation")
    print("3. 🧪 Exécuter les tests")
    print("4. 📚 Ouvrir la documentation")
    print("5. 🚀 Lancer l'application")
    print("6. 🔧 Outils avancés")
    print("7. ❓ Aide")
    print("0. ❌ Quitter")

    print()
    return input("Votre choix: ").strip()


def show_status():
    """Show migration status."""
    print_header("Statut de la Migration")

    # Check Python version
    import sys

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"Python version: {py_version}")

    if sys.version_info >= (3, 13):
        print_success("Python 3.13+ détecté - Migration supportée")
    else:
        print_warning("Python 3.10-3.12 - Migration ciblée pour 3.13+")

    # Check key libraries
    print("\n" + Colors.BOLD + "Bibliothèques:" + Colors.NC)

    libs_to_check = [
        ("numpy", "2.1.0"),
        ("sqlalchemy", "2.0.0"),
        ("matplotlib", "3.10.7"),
        ("PyQt5", "5.15.0"),
    ]

    for lib_name, min_version in libs_to_check:
        try:
            if lib_name == "PyQt5":
                from PySide6 import __version__ as version

            else:
                lib = __import__(lib_name)
                version = lib.__version__

            print(f"  {lib_name:20s} {version:15s} ", end="")

            # Simple version check
            if version >= min_version:
                print_success("OK")
            else:
                print_warning(f"< {min_version}")

        except ImportError:
            print_error(f"{lib_name:20s} NOT INSTALLED")

    # Check modified files
    print("\n" + Colors.BOLD + "Fichiers Modifiés:" + Colors.NC)

    modified_files = [
        "pyproject.toml",
        "GuiSessionViewer.py",
    ]

    for file in modified_files:
        if Path(file).exists():
            print_success(f"  {file}")
        else:
            print_error(f"  {file} - MANQUANT")

    # Check documentation
    print("\n" + Colors.BOLD + "Documentation:" + Colors.NC)

    doc_files = [
        "MIGRATION_README.md",
        "MIGRATION_CHECKLIST.md",
        "MIGRATION_PYTHON_3.13_3.14.md",
        "validate_migration.py",
        "test_migration.py",
    ]

    for doc in doc_files:
        if Path(doc).exists():
            print_success(f"  {doc}")
        else:
            print_warning(f"  {doc} - MANQUANT")


def run_validation():
    """Run validation script."""
    print_header("Validation de la Migration")

    if not Path("validate_migration.py").exists():
        print_error("validate_migration.py introuvable")
        return

    run_command([sys.executable, "validate_migration.py"], "Validation")


def run_tests():
    """Run test suite."""
    print_header("Tests de Migration")

    print(f"{Colors.BOLD}Choisissez les tests à exécuter:{Colors.NC}\n")
    print("1. Tests de migration (test_migration.py)")
    print("2. Tests unitaires complets (pytest)")
    print("3. Les deux")
    print("0. Retour")

    choice = input("\nVotre choix: ").strip()

    if choice == "1" or choice == "3":
        if Path("test_migration.py").exists():
            run_command([sys.executable, "test_migration.py"], "Tests de migration")
        else:
            print_error("test_migration.py introuvable")

    if choice == "2" or choice == "3":
        run_command([sys.executable, "-m", "pytest", "test/"], "Tests unitaires")


def open_documentation():
    """Open documentation menu."""
    print_header("Documentation")

    docs = [
        ("QUICKSTART.md", "⚡ Démarrage rapide (5 minutes)"),
        ("MIGRATION_README.md", "📖 Guide de migration complet"),
        ("MIGRATION_FAQ.md", "❓ FAQ - 47 questions/réponses"),
        ("MIGRATION_CHECKLIST.md", "✅ Checklist de validation"),
        ("RELEASE_NOTES.md", "📢 Notes de version"),
        ("CHANGELOG.md", "📝 Historique des changements"),
        ("DEPLOYMENT.md", "🚀 Guide de déploiement production"),
        ("MIGRATION_PYTHON_3.13_3.14.md", "🔧 Détails techniques"),
        ("IMPLEMENTATION_SUMMARY.md", "📊 Résumé d'implémentation"),
        ("TECHNICAL_DEBT_ANALYSIS.md", "💡 Analyse stratégique"),
        ("LIBRARY_IMPACT_ANALYSIS.md", "📂 Impact fichier par fichier"),
        ("PYSIDE6_MIGRATION_ANALYSIS.md", "🔄 Migration PySide6 (optionnel)"),
    ]

    print(f"{Colors.BOLD}Documents disponibles:{Colors.NC}\n")
    for i, (filename, description) in enumerate(docs, 1):
        status = "✅" if Path(filename).exists() else "❌"
        print(f"{i}. {status} {description}")
        print(f"   {Colors.CYAN}{filename}{Colors.NC}")

    print("\n0. Retour")

    choice = input("\nNuméro du document à afficher (0 pour retour): ").strip()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(docs):
            filename = docs[idx][0]
            if Path(filename).exists():
                # Try to use less, fall back to cat
                try:
                    subprocess.run(["less", filename])
                except FileNotFoundError:
                    subprocess.run(["cat", filename])
            else:
                print_error(f"{filename} introuvable")
    except (ValueError, IndexError):
        pass


def launch_application():
    """Launch FPDB application."""
    print_header("Lancement de l'Application")

    if not Path("fpdb.pyw").exists():
        print_error("fpdb.pyw introuvable")
        return

    print_info("Lancement de FPDB-3...")
    print_warning("L'application va démarrer dans une nouvelle fenêtre")
    print_info("Testez les fonctionnalités suivantes:")
    print("  - Menu → Graphs → Graph Viewer")
    print("  - Menu → Graphs → Session Viewer")
    print("  - Import de mains")
    print()

    input("Appuyez sur Entrée pour continuer...")

    try:
        subprocess.Popen([sys.executable, "fpdb.pyw"])
        print_success("Application lancée")
    except MIGRATION_HELPER_COMMAND_ERRORS as e:
        print_error(f"Erreur au lancement: {e}")


def advanced_tools():
    """Show advanced tools menu."""
    print_header("Outils Avancés")

    print(f"{Colors.BOLD}Outils disponibles:{Colors.NC}\n")
    print("1. 🔍 Vérifier les versions des bibliothèques")
    print("2. 📦 Réinstaller les dépendances")
    print("3. 🗑️  Nettoyer l'environnement")
    print("4. 📊 Afficher les statistiques de migration")
    print("5. 🔄 Vérifier les mises à jour Git")
    print("0. Retour")

    choice = input("\nVotre choix: ").strip()

    if choice == "1":
        check_library_versions()
    elif choice == "2":
        reinstall_dependencies()
    elif choice == "3":
        clean_environment()
    elif choice == "4":
        show_migration_stats()
    elif choice == "5":
        check_git_status()


def check_library_versions():
    """Check library versions in detail."""
    print_header("Versions des Bibliothèques")

    libs = [
        "numpy",
        "sqlalchemy",
        "matplotlib",
        "mplfinance",
        "fastapi",
        "pydantic",
        "aiohttp",
        "PyQt5",
        "pandas",
        "pytest",
    ]

    for lib in libs:
        cmd = [sys.executable, "-c", f"import {lib}; print('{lib}:', {lib}.__version__)"]
        subprocess.run(cmd, stderr=subprocess.DEVNULL)


def reinstall_dependencies():
    """Reinstall dependencies."""
    print_header("Réinstallation des Dépendances")

    print_warning("Ceci va réinstaller toutes les dépendances")
    confirm = input("Continuer? (y/n): ").strip().lower()

    if confirm == "y":
        # Try uv first, fall back to pip
        try:
            subprocess.run(["uv", "pip", "install", "-e", "."])
        except FileNotFoundError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."])


def clean_environment():
    """Clean build artifacts."""
    print_header("Nettoyage de l'Environnement")

    dirs_to_clean = [
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        "*.egg-info",
        "build",
        "dist",
    ]

    print("Répertoires/fichiers à nettoyer:")
    for pattern in dirs_to_clean:
        print(f"  - {pattern}")

    confirm = input("\nContinuer? (y/n): ").strip().lower()

    if confirm == "y":
        subprocess.run(["find", ".", "-type", "d", "-name", "__pycache__", "-exec", "rm", "-rf", "{}", "+"])
        subprocess.run(["find", ".", "-type", "f", "-name", "*.pyc", "-delete"])
        print_success("Nettoyage terminé")


def show_migration_stats():
    """Show migration statistics."""
    print_header("Statistiques de Migration")

    try:
        # Count lines in modified files
        result = subprocess.run(["git", "diff", "--stat", "9bb286b", "HEAD"], capture_output=True, text=True)
        print(result.stdout)
    except MIGRATION_HELPER_COMMAND_ERRORS as e:
        print_error(f"Erreur: {e}")


def check_git_status():
    """Check git status."""
    print_header("Statut Git")

    subprocess.run(["git", "status"])
    print()
    subprocess.run(["git", "log", "--oneline", "-5"])


def show_help():
    """Show help."""
    print_header("Aide")

    print(f"{Colors.BOLD}Guide de Démarrage Rapide:{Colors.NC}\n")

    print("1. Valider l'installation:")
    print(f"   {Colors.CYAN}python validate_migration.py{Colors.NC}")

    print("\n2. Exécuter les tests:")
    print(f"   {Colors.CYAN}python test_migration.py{Colors.NC}")

    print("\n3. Lire la documentation:")
    print(f"   {Colors.CYAN}cat MIGRATION_README.md{Colors.NC}")

    print("\n4. Suivre la checklist:")
    print(f"   {Colors.CYAN}cat MIGRATION_CHECKLIST.md{Colors.NC}")

    print(f"\n{Colors.BOLD}En cas de problème:{Colors.NC}\n")

    print("• Vérifier les logs:")
    print(f"  {Colors.CYAN}cat fpdb-log.txt{Colors.NC}")

    print("\n• Réexécuter la validation:")
    print(f"  {Colors.CYAN}python validate_migration.py{Colors.NC}")

    print("\n• Vérifier les versions:")
    print(f'  {Colors.CYAN}python -c "import numpy; print(numpy.__version__)"{Colors.NC}')

    print(f"\n{Colors.BOLD}Ressources:{Colors.NC}\n")
    print("• Guide utilisateur: MIGRATION_README.md")
    print("• Checklist: MIGRATION_CHECKLIST.md")
    print("• Détails techniques: MIGRATION_PYTHON_3.13_3.14.md")


def main():
    """Main function."""
    while True:
        try:
            choice = show_main_menu()

            if choice == "0":
                print("\n" + Colors.GREEN + "Au revoir!" + Colors.NC)
                break
            elif choice == "1":
                show_status()
            elif choice == "2":
                run_validation()
            elif choice == "3":
                run_tests()
            elif choice == "4":
                open_documentation()
            elif choice == "5":
                launch_application()
            elif choice == "6":
                advanced_tools()
            elif choice == "7":
                show_help()
            else:
                print_warning("Choix invalide")

            input("\nAppuyez sur Entrée pour continuer...")

        except KeyboardInterrupt:
            print("\n\n" + Colors.YELLOW + "Interruption détectée" + Colors.NC)
            break
        except Exception as e:  # intentional broad catch: interactive helper loop should keep running after action failures.
            print_error(f"Erreur: {e}")
            input("\nAppuyez sur Entrée pour continuer...")


if __name__ == "__main__":
    main()
