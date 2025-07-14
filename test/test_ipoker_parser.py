#!/usr/bin/env python3
"""Test script pour le parser iPoker"""

import os
import sys
import logging
from PokerTrackerToFpdb import PokerTracker

# Configuration du logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def test_ipoker_file(file_path):
    """Test d'un fichier iPoker"""
    print(f"Testing file: {file_path}")
    
    try:
        # Lire le fichier
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            print("UTF-8 failed, trying cp1252...")
            with open(file_path, 'r', encoding='cp1252') as f:
                content = f.read()
        
        print(f"File content (first 500 chars):")
        print(content[:500])
        print("---")
        
        # Créer le parser
        from Configuration import Config
        config = Config()
        parser = PokerTracker(config, autostart=False)
        parser.readFile(file_path)
        
        # Tester la détection du site
        print("Testing site detection...")
        site_match = parser.re_Site.search(content)
        if site_match:
            print(f"Site detected: {site_match.group('SITE')}")
        else:
            print("No site detected!")
            return False
        
        # Tester la détection du game type
        print("Testing game type detection...")
        try:
            gametype = parser.determineGameType(content)
            print(f"Game type: {gametype}")
        except Exception as e:
            print(f"Error in determineGameType: {e}")
            return False
            
        # Tester la division en mains
        print("Testing hand splitting...")
        hands = parser.allHandsAsList()
        print(f"Number of hands found: {len(hands)}")
        
        if len(hands) > 0:
            print(f"First hand (first 200 chars): {hands[0][:200]}")
            
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Test avec un fichier iPoker
    test_file = "/Users/jdenis/fpdb-3/regression-test-files/PokerTracker-Archives/Mixed-Sources/cash/NLHE/NLHE-EUR-0.05-0.10-201901.iPoker.new.version.txt"
    test_ipoker_file(test_file)