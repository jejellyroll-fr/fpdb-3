"""Tests complets pour BovadaToFpdb - Validation exhaustive du parser.

Ce module teste le parser Bovada de manière exhaustive avec tous les formats d'archives,
en vérifiant que toutes les données importantes sont correctement extraites.
"""

import logging
import os
import unittest

try:
    from BovadaToFpdb import Bovada, FpdbHandPartial, FpdbParseError
    from Configuration import Config
    from Hand import DrawHand, Hand, HoldemOmahaHand, StudHand
except ImportError:
    import sys

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from BovadaToFpdb import Bovada, FpdbHandPartial, FpdbParseError
    from Configuration import Config
    from Hand import DrawHand, HoldemOmahaHand, StudHand

# Configuration du logging pour debug
logging.basicConfig(level=logging.WARNING)


class ComprehensiveBovadaTest(unittest.TestCase):
    """Tests exhaustifs du parser Bovada avec tous les fichiers d'archives."""

    @classmethod
    def setUpClass(cls) -> None:
        """Configuration générale des tests."""
        cls.config = Config()
        # Setup site IDs for testing
        cls.config.site_ids = {"Bovada": 1, "PokerStars": 2}  # Mock site IDs
        cls.parser = Bovada(config=cls.config)

        # Chemins vers les fichiers de test
        cls.test_files_dir = os.path.join(os.path.dirname(__file__), "..", "regression-test-files")

        # Collecte tous les fichiers Bovada
        cls.bovada_files = []
        for root, _dirs, files in os.walk(cls.test_files_dir):
            if "Bovada" in root:
                for file in files:
                    if file.endswith(".txt"):
                        cls.bovada_files.append(os.path.join(root, file))


    def setUp(self) -> None:
        """Configuration pour chaque test."""
        self.config.site_ids = {"Bovada": 1, "PokerStars": 2}  # Mock site IDs
        self.parser = Bovada(config=self.config)
        self.validation_errors = []

    def read_hand_file(self, file_path):
        """Lit un fichier de main et retourne le contenu."""
        try:
            with open(file_path, encoding="utf-8-sig") as f:
                return f.read()
        except Exception as e:
            self.fail(f"Impossible de lire le fichier {file_path}: {e}")

    def validate_hand_data(self, hand, file_path):
        """Valide qu'une main contient toutes les données essentielles."""
        filename = os.path.basename(file_path)
        errors = []

        # 1. Données de base obligatoires
        if not hand.handid:
            errors.append("handid manquant")
        if not hand.startTime:
            errors.append("startTime manquant")
        if not hand.gametype:
            errors.append("gametype manquant")

        # 2. Joueurs
        if not hand.players:
            errors.append("Aucun joueur trouvé")
        else:
            for player in hand.players:
                if not all(key in player for key in ["name", "stack", "seat"]):
                    errors.append(f"Données joueur incomplètes: {player}")

        # 3. Données spécifiques au type de jeu
        if hand.gametype and hand.gametype.get("type") == "tour":
            # Tournoi - vérifier buyin, fee
            if hand.buyin is None:
                errors.append("buyin manquant pour tournoi")
            if hand.fee is None:
                errors.append("fee manquant pour tournoi")

        # 4. Actions (si pas un partial hand)
        if not filename.endswith(".partial.txt"):
            total_actions = 0
            for street in hand.actionStreets:
                street_actions = [a for a in hand.actions if a[0] == street]
                total_actions += len(street_actions)

            if total_actions == 0:
                errors.append("Aucune action trouvée")

        # 5. Pot et rake (si disponible)
        if hand.totalpot is not None and hand.totalpot <= 0:
            errors.append(f"totalpot invalide: {hand.totalpot}")

        # 6. Validation spécifique aux streets
        if hand.gametype and hand.gametype.get("base") == "hold":
            # Pour Hold'em, vérifier les community cards si streets présentes
            if any(hand.streets.get(street) for street in ["FLOP", "TURN", "RIVER"]):
                # Au moins une street post-flop existe, on devrait avoir des actions
                post_flop_actions = [a for a in hand.actions if a[0] in ["FLOP", "TURN", "RIVER"]]
                if not post_flop_actions and not filename.endswith(".partial.txt"):
                    errors.append("Streets post-flop présentes mais aucune action post-flop")

        return errors

    def test_parse_all_cash_games(self) -> None:
        """Test tous les fichiers de cash games."""
        cash_files = [f for f in self.bovada_files if "/cash/" in f]
        failed_files = []

        for file_path in cash_files:
            filename = os.path.basename(file_path)
            with self.subTest(file=filename):
                try:
                    content = self.read_hand_file(file_path)
                    self.parser.in_path = file_path

                    # Parse each hand in the file
                    hands = content.split("\n\n\n")
                    for i, hand_text in enumerate(hands):
                        if not hand_text.strip():
                            continue

                        try:
                            # Determine gametype first
                            gametype = self.parser.determineGameType(hand_text.split("\n\n")[0])

                            # Create Hand object
                            if gametype["base"] == "hold":
                                hand = HoldemOmahaHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            elif gametype["base"] == "stud":
                                hand = StudHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            elif gametype["base"] == "draw":
                                hand = DrawHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            else:
                                continue

                            # Parse with Bovada parser
                            self.parser.readHandInfo(hand)
                            self.parser.readPlayerStacks(hand)
                            if hand.gametype["base"] != "stud":
                                self.parser.readBlinds(hand)
                            self.parser.compilePlayerRegexs(hand)
                            self.parser.markStreets(hand)

                            # Read actions for each street
                            for street in hand.actionStreets:
                                if hand.streets.get(street):
                                    self.parser.readAction(hand, street)

                            self.parser.readCollectPot(hand)
                            self.parser.readOther(hand)

                            # Validate the parsed data
                            validation_errors = self.validate_hand_data(hand, file_path)
                            if validation_errors:
                                error_msg = f"{filename} hand {i+1}: {', '.join(validation_errors)}"
                                failed_files.append(error_msg)

                        except (FpdbParseError, FpdbHandPartial):
                            # Ces exceptions sont attendues pour certains fichiers
                            pass
                        except Exception as e:
                            failed_files.append(f"{filename} hand {i+1}: Erreur parsing - {e}")

                except Exception as e:
                    failed_files.append(f"{filename}: Erreur lecture - {e}")

        if failed_files:
            self.fail(f"Échecs de parsing dans {len(failed_files)} cas:\n" + "\n".join(failed_files[:10]))

    def test_parse_all_tournaments(self) -> None:
        """Test tous les fichiers de tournois."""
        tour_files = [f for f in self.bovada_files if "/tour/" in f]
        failed_files = []

        for file_path in tour_files:
            filename = os.path.basename(file_path)
            with self.subTest(file=filename):
                try:
                    content = self.read_hand_file(file_path)
                    self.parser.in_path = file_path

                    hands = content.split("\n\n\n")
                    for i, hand_text in enumerate(hands):
                        if not hand_text.strip():
                            continue

                        try:
                            gametype = self.parser.determineGameType(hand_text.split("\n\n")[0])

                            if gametype["base"] == "hold":
                                hand = HoldemOmahaHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            elif gametype["base"] == "stud":
                                hand = StudHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            elif gametype["base"] == "draw":
                                hand = DrawHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            else:
                                continue

                            self.parser.readHandInfo(hand)
                            self.parser.readPlayerStacks(hand)
                            if hand.gametype["base"] != "stud":
                                self.parser.readBlinds(hand)
                            self.parser.compilePlayerRegexs(hand)
                            self.parser.markStreets(hand)

                            for street in hand.actionStreets:
                                if hand.streets.get(street):
                                    self.parser.readAction(hand, street)

                            self.parser.readCollectPot(hand)
                            self.parser.readOther(hand)

                            # Validation spécifique aux tournois
                            validation_errors = self.validate_hand_data(hand, file_path)
                            if hand.gametype.get("type") == "tour":
                                if not hand.tourNo:
                                    validation_errors.append("tourNo manquant")
                                if not hand.tablename:
                                    validation_errors.append("tablename manquant")

                            if validation_errors:
                                error_msg = f"{filename} hand {i+1}: {', '.join(validation_errors)}"
                                failed_files.append(error_msg)

                        except (FpdbParseError, FpdbHandPartial):
                            pass
                        except Exception as e:
                            failed_files.append(f"{filename} hand {i+1}: Erreur parsing - {e}")

                except Exception as e:
                    failed_files.append(f"{filename}: Erreur lecture - {e}")

        if failed_files:
            self.fail(f"Échecs de parsing dans {len(failed_files)} cas:\n" + "\n".join(failed_files[:10]))

    def test_specific_edge_cases(self) -> None:
        """Test des cas spécifiques problématiques identifiés."""
        edge_case_files = [
            "NLHE-USD-5-10-201511.concatenated.partial.txt",  # Partial hands
            "PLO8-9max-USD-0.02-0.05-201408.corrupted.lines.txt",  # Corrupted
            "NLHE-USD - $0.25-$0.50 - 202103.MVS.version.txt",  # MVS version
            "NLHE-USD - $0.05-$0.10 - 201308.ZonePoker.txt",  # Zone Poker
        ]

        for filename in edge_case_files:
            matching_files = [f for f in self.bovada_files if filename in f]
            if not matching_files:
                self.skipTest(f"Fichier {filename} non trouvé")
                continue

            file_path = matching_files[0]
            with self.subTest(file=filename):
                content = self.read_hand_file(file_path)
                self.parser.in_path = file_path

                # Ces fichiers peuvent lever des exceptions, c'est normal
                try:
                    hands = content.split("\n\n\n")
                    parsed_hands = 0

                    for hand_text in hands:
                        if not hand_text.strip():
                            continue
                        try:
                            gametype = self.parser.determineGameType(hand_text.split("\n\n")[0])

                            if gametype["base"] == "hold":
                                hand = HoldemOmahaHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            elif gametype["base"] == "stud":
                                hand = StudHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            elif gametype["base"] == "draw":
                                hand = DrawHand(self.config, self.parser, "Bovada", gametype, hand_text)
                            else:
                                continue

                            self.parser.readHandInfo(hand)
                            parsed_hands += 1
                        except (FpdbParseError, FpdbHandPartial):
                            # Attendu pour partial/corrupted files
                            pass


                except Exception as e:
                    # Pour les fichiers corrompus, c'est attendu
                    if "corrupted" not in filename and "partial" not in filename:
                        self.fail(f"Erreur inattendue pour {filename}: {e}")

    def test_data_consistency(self) -> None:
        """Test la cohérence des données extraites."""
        test_file = None
        for f in self.bovada_files:
            if "NLHE-6max-USD - $0.25-$0.50 - 201804.bodog.eu.txt" in f:
                test_file = f
                break

        if not test_file:
            self.skipTest("Fichier de test spécifique non trouvé")

        content = self.read_hand_file(test_file)
        self.parser.in_path = test_file

        gametype = self.parser.determineGameType(content.split("\n\n")[0])

        # Créer le bon type de Hand selon le gametype
        if gametype["base"] == "hold":
            hand = HoldemOmahaHand(self.config, self.parser, "Bovada", gametype, content)
        elif gametype["base"] == "stud":
            hand = StudHand(self.config, self.parser, "Bovada", gametype, content)
        elif gametype["base"] == "draw":
            hand = DrawHand(self.config, self.parser, "Bovada", gametype, content)
        else:
            msg = f"Type de jeu non supporté: {gametype['base']}"
            raise ValueError(msg)

        # Parse complètement
        self.parser.readHandInfo(hand)
        self.parser.readPlayerStacks(hand)
        self.parser.readBlinds(hand)
        self.parser.compilePlayerRegexs(hand)
        self.parser.markStreets(hand)

        for street in hand.actionStreets:
            if hand.streets.get(street):
                self.parser.readAction(hand, street)

        self.parser.readCollectPot(hand)
        self.parser.readOther(hand)

        # Vérifications de cohérence
        assert hand.handid == "3598529418"
        assert len(hand.players) == 6
        assert hand.gametype["limitType"] == "nl"
        assert hand.gametype["base"] == "hold"

        # Vérifier les actions
        preflop_actions = [a for a in hand.actions if a[0] == "PREFLOP"]
        assert len(preflop_actions) > 0

        # Vérifier qu'on a la relance attendue
        raise_actions = [a for a in hand.actions if a[2] == "raise"]
        assert len(raise_actions) > 0



if __name__ == "__main__":
    unittest.main(verbosity=2)
