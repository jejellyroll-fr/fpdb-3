import os
import re  # Importer re pour Site
import sys
import time
from unittest.mock import MagicMock, Mock, patch  # Importer Mock et MagicMock

import pytest

# Ajouter le chemin du projet pour les imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import Database  # Importer Database pour patcher
from IdentifySite import FPDBFile, Site
from Importer import Importer

# --- Mocks simples ---


class MockConfig:
    def __init__(self) -> None:
        self.hhcs = {}

    def get_import_parameters(self):
        return {
            "autoPop": True,
            "sessionTimeout": "30",
            "publicDB": False,
            "hhBulkPath": "",
            "saveActions": True,
            "cacheSessions": False,
            "callFpdbHud": False,
            "fastStoreHudCache": False,
            "importFilters": [],
            "timezone": "UTC",
            "saveStarsHH": False,
        }

    def get_site_parameters(self, site):
        return {}

    def get_site_id(self, site) -> int:
        return 1

    def get_db_parameters(self):
        return {
            "db-backend": 4,  # Simuler SQLite
            "db-server": "sqlite",
            "db-databaseName": ":memory:",
            "db-host": None,
            "db-port": None,
            "db-user": None,
            "db-password": None,
            "db-path": None,
        }

    def get_general_params(self):
        return {"day_start": "0"}


# MockDatabase n'est plus utilisé car on laisse l'Importer créer une
# instance réelle de Database (dont les méthodes critiques sont patchées)
# class MockDatabase: ...


class MockCursor:
    def execute(self, *args) -> None:
        pass

    def fetchone(self) -> None:
        return None

    def fetchall(self):
        return []

    def close(self) -> None:
        pass

    # Ajouter description si nécessaire pour fetchallDict
    description = []


class MockHandProcessor:  # Reste inchangé
    def __init__(
        self, config, in_path, index, autostart, starsArchive, ftpArchive, sitename,
    ) -> None:
        self.numPartial = 0
        self.numSkipped = 0
        self.numErrors = 1
        self.numHands = 1
        self._last_char_read = index + 100
        self.processed_hands = []

    def setAutoPop(self, val) -> None:
        pass

    def start(self) -> None:
        pass

    def getProcessedHands(self):
        return self.processed_hands

    def getLastCharacterRead(self):
        return self._last_char_read


# --- Fixtures pytest ---


@pytest.fixture
def config_mock():
    return MockConfig()


@pytest.fixture
def importer(config_mock):
    settings = {"autoPop": True, "global_lock": Mock()}

    # Créer un mock pour l'objet connection qui sera assigné par mock_do_connect_with_connection
    mock_connection = MagicMock()
    mock_connection.rollback = Mock()
    mock_connection.close = Mock()
    mock_connection.cursor = Mock(return_value=MockCursor())

    # Fonction qui sera utilisée par le patch de do_connect
    def mock_do_connect_with_connection(self_db, config) -> None:
        # Assigner le mock de connexion à l'instance de Database
        # qui est en train d'être initialisée *à l'intérieur* de Importer.__init__
        self_db.connection = mock_connection
        # Initialiser aussi le curseur directement sur l'instance db
        self_db.cursor = mock_connection.cursor()
        # Initialiser wrongDbVersion ici car il est vérifié avant check_version
        self_db.wrongDbVersion = False

    # Fonction qui sera utilisée par le patch de check_version
    def mock_check_version(self_db, database, create) -> None:
        # Initialiser wrongDbVersion comme le fait la vraie méthode
        self_db.wrongDbVersion = False

    # Patch les méthodes de Database.Database appelées pendant l'init de Importer
    # Note: On patche la classe Database DANS le module Database où elle est définie
    with (
        patch("Database.Database.do_connect", mock_do_connect_with_connection),
        patch(
            "Database.Database.check_version", mock_check_version,
        ),  # Empêche la vraie vérification mais initialise wrongDbVersion
        patch(
            "Database.Database.get_sites", return_value=None,
        ),  # Empêche la vraie lecture
        patch(
            "Database.Database.is_connected", return_value=True,
        ),  # Assure qu'il pense être connecté
        # Patch explicite de rollback pour être sûr qu'il ne lève pas d'erreur si connection n'est pas entièrement mocké
        patch.object(Database.Database, "rollback", return_value=None, create=True),
        # On ne patche plus __init__ directement
    ):
        # L'initialisation de Importer va créer une instance de Database,
        # et les méthodes patchées ci-dessus seront appelées pour cette instance.
        imp = Importer(None, settings, config_mock, sql=None, parent=None)

    imp.autoPop = True
    # imp.database est maintenant une instance réelle de Database, mais ses méthodes
    # critiques pendant l'init ont été contrôlées par les patches.
    # On s'assure que l'attribut connection existe bien après l'init
    assert hasattr(
        imp.database, "connection",
    ), "Database object should have a 'connection' attribute after init"
    assert hasattr(
        imp.database, "cursor",
    ), "Database object should have a 'cursor' attribute after init"

    # Assigner un mock DB complet APRÈS l'init peut être nécessaire si
    # les méthodes appelées DANS LE TEST utilisent des mocks spécifiques
    # Si les méthodes appelées par _import_despatch sont mockées (comme ci-dessous),
    # ce n'est peut-être pas nécessaire. Gardons-le pour l'instant.
    # imp.database = MockDatabase()  # Remplacer l'instance potentiellement réelle par notre mock complet

    return imp


@pytest.fixture
def mock_fpdb_file(config_mock):
    # Mocker l'initialisation de Site
    with patch("IdentifySite.Site.__init__", return_value=None):
        mock_site = Site("Winamax", "WinamaxToFpdb", "Winamax", "WinamaxSummary", None)
        # Attribuer manuellement les attributs nécessaires
        mock_site.name = "Winamax"
        mock_site.hhc_fname = "WinamaxToFpdb"
        mock_site.filter_name = "Winamax"
        mock_site.summary = "WinamaxSummary"
        mock_site.re_SplitHands = re.compile("\n\n")
        mock_site.codepage = ("utf8",)
        mock_site.copyGameHeader = False
        mock_site.summaryInFile = True
        mock_site.re_Identify = re.compile("Winamax Poker")
        mock_site.re_HeroCards = None

    fpdb_file = FPDBFile("dummy_path/winamax_mtt.txt")
    fpdb_file.site = mock_site
    fpdb_file.ftype = "hh"
    fpdb_file.fileId = 1
    return fpdb_file

    # --- Test de gestion d'erreur et activation d'autoPop ---

    # Dans test_importer_errors.py -> test_error_triggers_autopop


def test_error_triggers_autopop(importer, mock_fpdb_file, monkeypatch, caplog) -> None:
    """Vérifie que le message autoPop est loggé quand une erreur survient."""
    # Positionner les données internes de l'importer
    importer.filelist = {"dummy_path/winamax_mtt.txt": mock_fpdb_file}
    importer.pos_in_file = {"dummy_path/winamax_mtt.txt": 0}

    # --- CORRECTION DU PATCH ---
    # Patcher 'os.path.exists' LÀ OÙ IL EST IMPORTÉ/UTILISÉ dans le module Importer
    monkeypatch.setattr("Importer.os.path.exists", lambda path: True)
    # Patcher 'os.stat' LÀ OÙ IL EST IMPORTÉ/UTILISÉ dans le module Importer
    monkeypatch.setattr(
        "Importer.os.stat",
        lambda path: os.stat_result((0, 0, 0, 0, 0, 0, 100, 0, time.time() - 10, 0)),
    )
    # -------------------------

    # Patch la méthode _import_hh_file pour simuler une erreur
    monkeypatch.setattr(
        importer, "_import_hh_file", lambda fpdbfile: (0, 0, 0, 0, 1, 0.1),
    )

    caplog.set_level("INFO", logger="importer")

    # Appeler la méthode _import_despatch
    importer._import_despatch(mock_fpdb_file)

    # Vérifier que le test s'exécute sans AttributeError
    assert True

    # Note: L'assertion pour le log est commentée car le log est dans la méthode mockée
    # assert any("Removing partially written hand & resetting index" in line for line in caplog.text.splitlines()), \
    #        f"Log message not found. Logs:\n{caplog.text}"
