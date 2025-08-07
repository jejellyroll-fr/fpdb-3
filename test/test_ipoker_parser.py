#!/usr/bin/env python3
"""Test script pour le parser iPoker."""

import logging

from PokerTrackerToFpdb import PokerTracker

# Configuration du logging
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)


def test_ipoker_file(file_path) -> bool | None:
    """Test d'un fichier iPoker."""
    try:
        # Lire le fichier
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, encoding="cp1252") as f:
                content = f.read()


        # Créer le parser
        from Configuration import Config

        config = Config()
        parser = PokerTracker(config, autostart=False)
        parser.readFile(file_path)

        # Tester la détection du site
        site_match = parser.re_Site.search(content)
        if site_match:
            pass
        else:
            return False

        # Tester la détection du game type
        try:
            parser.determineGameType(content)
        except Exception:
            return False

        # Tester la division en mains
        hands = parser.allHandsAsList()

        if len(hands) > 0:
            pass

        return True

    except Exception:
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Test avec un fichier iPoker
    test_file = "/Users/jdenis/fpdb-3/regression-test-files/PokerTracker-Archives/Mixed-Sources/cash/NLHE/NLHE-EUR-0.05-0.10-201901.iPoker.new.version.txt"
    test_ipoker_file(test_file)
