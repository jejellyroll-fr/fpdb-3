"""bet365.fr, the French skin of bet365 on the iPoker network (#717).

Its hands must be filed under "Bet365.fr Poker" (site 132), never under the
international "Bet365 Poker" (site 63): every bet365.fr path also contains
"bet365", so the order of the skin registry decides. Its client must be found
on Windows without any hardcoded path (environment folders, name patterns, the
uninstall and App Paths registry entries), and on macOS in a sandbox container
whose exact name is not confirmed yet.
"""

from __future__ import annotations

import os
import xml.dom.minidom
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import fpdb_3_legacy.DetectInstalledSites as detect_module
from fpdb.infrastructure.platform.macos import MacOSTableDetector
from fpdb_3_legacy.DetectInstalledSites import (
    APP_PATHS_KEY,
    IPOKER_CLIENT_NAME_PATTERNS,
    UNINSTALL_KEY,
    UNINSTALL_KEY_WOW64,
    _folder_of_executable,
    iPokerDetector,
    matching_subfolders,
    windows_registry_install_dirs,
)
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.iPoker.dispatcher import (
    DEFAULT_DISPATCHER,
    IPOKER_SKINS,
    detect_skin,
    get_parser_class_for_path,
    resolve_site_id,
)
from fpdb_3_legacy.iPoker.skins import Bet365FrIPoker, Bet365IPoker

SITE = "Bet365.fr Poker"
SITE_ID = 132
NOT_DETECTED = {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}
REPO = Path(__file__).resolve().parents[1]

WINDOWS_FR_PATH = r"C:\Users\al\AppData\Local\bet365 Poker France\data\hero\History\Data\Tables\5869857694.xml"
WINDOWS_GENERIC_PATH = r"C:\Users\al\AppData\Local\bet365 Poker\data\hero\History\Data\Tables\5869857694.xml"


def same_path(left: str, right: Path | str) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(str(right)))


def tree(root: Path, *parts: str) -> Path:
    target = root.joinpath(*parts)
    target.mkdir(parents=True, exist_ok=True)
    return target


def account(data_dir: Path, hero: str = "Hero") -> Path:
    """Lay out an iPoker account the way the client does: <data>/<account>/History/Data/Tables."""
    tree(data_dir, hero, "History", "Data", "Tournaments")
    return tree(data_dir, hero, "History", "Data", "Tables")


def windows_paths(root: Path) -> dict[str, str]:
    return {
        "appdata": str(root / "AppData" / "Roaming"),
        "local_appdata": str(root / "AppData" / "Local"),
        "program_files": str(root / "Program Files"),
        "program_files_x86": str(root / "Program Files (x86)"),
        "userprofile": str(root / "Users" / "Hero"),
    }


def mac_paths(root: Path) -> dict[str, str]:
    return {
        "app_support": str(root / "Library" / "Application Support"),
        "applications": str(root / "Applications"),
        "documents": str(root / "Documents"),
    }


@pytest.fixture
def config() -> Any:
    stub = MagicMock()
    stub.os_family = "Win7"
    return stub


@pytest.fixture(autouse=True)
def no_registry() -> Any:
    """The machine running the tests may have anything installed: its registry is never read."""
    with patch.object(detect_module, "windows_registry_install_dirs", return_value=[]) as fake:
        yield fake


def detect_on_windows(config: Any, root: Path, skin: str = SITE) -> dict[str, Any]:
    detector = iPokerDetector(config)
    detector.platform = "Windows"
    with patch.object(detect_module, "get_windows_paths", return_value=windows_paths(root)):
        return detector._detect_skin(skin)


def detect_on_macos(detector: iPokerDetector, root: Path, skin: str = SITE) -> dict[str, Any]:
    detector.platform = "Darwin"
    with (
        patch.object(detect_module, "get_mac_paths", return_value=mac_paths(root)),
        patch.object(Path, "home", return_value=root),
    ):
        return detector._detect_skin(skin)


# --------------------------------------------------------------------------
# Which room a file is filed under
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        WINDOWS_FR_PATH,
        r"C:\Users\al\AppData\Local\bet365.fr Poker\data\hero\History\Data\Tables\1.xml",
        r"C:\Users\al\AppData\Roaming\bet365fr\data\hero\History\Data\Tables\1.xml",
        r"D:\Jeux\bet365-fr\data\hero\History\Data\Tables\1.xml",
        "/Users/x/Library/Containers/fr.bet365.poker/Data/Library/Application Support/"
        "bet365.fr Online Poker/hero/History/Data/Tables/1.xml",
    ],
)
def test_a_bet365_fr_path_is_filed_under_the_french_room(path: str) -> None:
    assert detect_skin(path) == SITE
    assert get_parser_class_for_path(path) is Bet365FrIPoker


@pytest.mark.parametrize(
    "path",
    [
        WINDOWS_GENERIC_PATH,
        "/Users/x/Library/Application Support/Bet365 Poker/data/hero/History/Data/Tables/1.xml",
    ],
)
def test_an_international_bet365_path_stays_with_bet365_poker(path: str) -> None:
    assert detect_skin(path) == "Bet365 Poker"
    assert get_parser_class_for_path(path) is Bet365IPoker


def test_the_french_skin_is_checked_before_the_generic_bet365_one() -> None:
    # detect() takes the first skin whose indicator is in the path, and every
    # bet365.fr path contains "bet365": moving the entry after it files the
    # French hands under the international room.
    names = [skin.site_name for skin in IPOKER_SKINS]
    assert names.index(SITE) < names.index("Bet365 Poker")


def test_the_french_skin_is_its_own_site() -> None:
    skin = DEFAULT_DISPATCHER.get_by_site_name(SITE)

    assert skin.default_site_id == SITE_ID
    assert Bet365FrIPoker.sitename == SITE
    assert Bet365FrIPoker.site_id == SITE_ID
    assert resolve_site_id(SimpleNamespace(), SITE) == SITE_ID
    # No other skin claims the id.
    assert [s.site_name for s in IPOKER_SKINS if s.default_site_id == SITE_ID] == [SITE]


@pytest.mark.parametrize("parser_class", [iPoker, Bet365FrIPoker])
def test_a_converter_of_a_bet365_fr_file_files_it_under_the_french_room(parser_class: type[iPoker]) -> None:
    hhc = parser_class(
        MagicMock(),
        in_path=WINDOWS_FR_PATH,
        index=0,
        autostart=False,
        starsArchive=False,
        ftpArchive=False,
        sitename="Bet365 Poker",
    )

    assert hhc.sitename == SITE
    assert hhc.site_id == SITE_ID


# --------------------------------------------------------------------------
# The site is known everywhere a site has to be declared
# --------------------------------------------------------------------------


def test_a_new_database_holds_the_site(tmp_path: Path) -> None:
    from fpdb_3_legacy.Database import Database
    from tests.helpers import analytics_golden as golden

    db = Database(golden.build_config(tmp_path))
    try:
        db.recreate_tables()
        cursor = db.get_cursor()
        cursor.execute(f"SELECT name, code FROM Sites WHERE id = {SITE_ID}")  # nosemgrep
        assert cursor.fetchone() == (SITE, "IP")
    finally:
        db.disconnect()


def test_an_existing_database_gains_the_site_on_connect(tmp_path: Path) -> None:
    # A database created before the site existed has no row 132, and a hand
    # filed there would break the Sites foreign key.
    from fpdb_3_legacy.Database import Database
    from tests.helpers import analytics_golden as golden

    db = Database(golden.build_config(tmp_path))
    try:
        db.recreate_tables()
        cursor = db.get_cursor()
        cursor.execute(f"DELETE FROM Sites WHERE id = {SITE_ID}")  # nosemgrep
        db.commit()

        db.ensure_feature_tables()
        db.ensure_feature_tables()  # running it again is a no-op, not a duplicate

        cursor = db.get_cursor()
        cursor.execute(f"SELECT name, code FROM Sites WHERE id = {SITE_ID}")  # nosemgrep
        assert cursor.fetchall() == [(SITE, "IP")]
    finally:
        db.disconnect()


def test_an_empty_sites_table_is_left_to_the_default_data() -> None:
    # fillDefaultData inserts every site into the empty table right after it
    # is created: a row added first would make it fail on a duplicate id.
    from fpdb_3_legacy.Database import Database

    class Cursor:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: str, *_params: Any) -> None:
            self.statements.append(statement)

        def fetchall(self) -> list[tuple[int]]:
            return []

    cursor = Cursor()
    db = Database.__new__(Database)
    db.get_cursor = lambda: cursor
    db.commit = MagicMock()
    db.rollback = MagicMock()

    db.ensure_sites_rows()

    assert cursor.statements == ["SELECT id FROM Sites"]
    db.commit.assert_not_called()


def test_the_configuration_knows_the_site_id_without_a_database() -> None:
    from fpdb_3_legacy.config_sites import ConfigSitesMixin

    holder = ConfigSitesMixin.__new__(ConfigSitesMixin)
    holder.site_ids = {}

    assert holder.get_site_id(SITE) == SITE_ID


def test_the_preferences_detect_the_site_with_the_ipoker_network() -> None:
    from fpdb_3_legacy.ModernSitePreferences import ModernSiteCard

    assert ModernSiteCard.get_network_for_skin(None, SITE) == "iPoker"


@pytest.mark.parametrize(
    "example", ["HUD_config.xml", "HUD_config.xml.example", "fpdb_3_legacy/HUD_config.xml.example"]
)
def test_the_example_configuration_declares_the_site(example: str) -> None:
    doc = xml.dom.minidom.parse(str(REPO / example))
    [site] = [node for node in doc.getElementsByTagName("site") if node.getAttribute("site_name") == SITE]
    [hhc] = [node for node in doc.getElementsByTagName("hhc") if node.getAttribute("site") == SITE]

    assert site.getAttribute("network") == "iPoker"
    assert site.getAttribute("enabled") == "False"
    # Nothing hardcoded: detection fills the paths in from the installed client.
    assert site.getAttribute("HH_path") == ""
    assert site.getAttribute("site_path") == ""
    [layout] = site.getElementsByTagName("layout_set")
    assert layout.getAttribute("ls") == "ipoker_default"
    assert hhc.getAttribute("converter") == "iPokerToFpdb"
    assert hhc.getAttribute("summaryImporter") == "iPokerSummary"


def test_the_macos_hud_follows_a_bet365_client_window() -> None:
    detector = object.__new__(MacOSTableDetector)

    assert detector._is_target_process("bet365 Poker")


# --------------------------------------------------------------------------
# Finding the client on Windows, with no hardcoded path
# --------------------------------------------------------------------------


@pytest.mark.parametrize("folder", ["bet365 Poker France", "bet365.fr Poker", "bet365fr"])
def test_the_client_is_found_under_its_local_appdata_folder(config, tmp_path, folder) -> None:
    tables = account(Path(windows_paths(tmp_path)["local_appdata"]) / folder / "data", "alice")

    found = detect_on_windows(config, tmp_path)

    assert found["detected"] is True
    assert found["skin"] == SITE
    assert found["heroname"] == "alice"
    assert same_path(found["hhpath"], tables)
    assert same_path(found["tspath"], tables.parent / "Tournaments")
    # The hands found there are filed under the French room too.
    assert detect_skin(found["hhpath"]) == SITE


@pytest.mark.parametrize(
    ("root_key", "folder"),
    [("local_appdata", "bet365 Poker FR"), ("appdata", "Bet365 Poker France 2026"), ("local_appdata", "fr.bet365")],
)
def test_a_folder_named_otherwise_is_found_by_its_name_pattern(config, tmp_path, root_key, folder) -> None:
    tables = account(Path(windows_paths(tmp_path)[root_key]) / folder / "data")

    found = detect_on_windows(config, tmp_path)

    assert found["detected"] is True
    assert same_path(found["hhpath"], tables)


@pytest.mark.parametrize("layout", [("data",), (SITE, "data"), ("bet365 Poker France", "data")])
def test_the_client_is_found_where_the_registry_says_it_was_installed(config, tmp_path, no_registry, layout) -> None:
    install = tmp_path / "Games" / "somewhere the user picked"
    tables = account(install.joinpath(*layout))
    no_registry.return_value = [str(install)]

    found = detect_on_windows(config, tmp_path)

    assert found["detected"] is True
    assert same_path(found["hhpath"], tables)
    no_registry.assert_called_once_with(IPOKER_CLIENT_NAME_PATTERNS[SITE])


def test_the_international_client_is_not_taken_for_the_french_one(config, tmp_path) -> None:
    account(Path(windows_paths(tmp_path)["local_appdata"]) / "bet365 Poker" / "data")

    assert detect_on_windows(config, tmp_path) == NOT_DETECTED
    assert detect_on_windows(config, tmp_path, "Bet365 Poker")["detected"] is True


def test_the_french_client_is_not_taken_for_the_international_one(config, tmp_path) -> None:
    account(Path(windows_paths(tmp_path)["local_appdata"]) / "bet365 Poker France" / "data")

    assert detect_on_windows(config, tmp_path, "Bet365 Poker") == NOT_DETECTED


def test_a_client_that_is_not_installed_is_reported_as_absent(config, tmp_path) -> None:
    assert detect_on_windows(config, tmp_path) == NOT_DETECTED


def test_the_registry_is_only_read_for_skins_that_need_it(config, tmp_path, no_registry) -> None:
    detect_on_windows(config, tmp_path, "Betclic Poker")

    no_registry.assert_not_called()


def test_the_network_sweep_reports_the_french_client(config, tmp_path) -> None:
    account(Path(windows_paths(tmp_path)["local_appdata"]) / "bet365 Poker France" / "data", "alice")
    detector = iPokerDetector(config)
    detector.platform = "Windows"

    with patch.object(detect_module, "get_windows_paths", return_value=windows_paths(tmp_path)):
        detector.detect()

    assert [skin["skin"] for skin in detector.get_all_detected_skins()] == [SITE]


@pytest.mark.parametrize("folder", ["bet365.fr", "bet365fr"])
def test_the_shared_pokerclient_folder_maps_to_the_french_room(config, tmp_path, folder) -> None:
    account(Path(windows_paths(tmp_path)["local_appdata"]) / "PokerClient" / folder / "data")
    detector = iPokerDetector(config)
    detector.platform = "Windows"

    with patch.object(detect_module, "get_windows_paths", return_value=windows_paths(tmp_path)):
        found = detector._detect_pokerclient()

    assert found["skin"] == SITE


def test_folder_patterns_ignore_case_and_files(tmp_path) -> None:
    tree(tmp_path, "BET365 POKER FRANCE")
    tree(tmp_path, "bet365 Poker")
    (tmp_path / "bet365fr.log").write_text("")

    found = matching_subfolders(tmp_path, IPOKER_CLIENT_NAME_PATTERNS[SITE])

    assert [path.name for path in found] == ["BET365 POKER FRANCE"]
    assert matching_subfolders(tmp_path / "missing", IPOKER_CLIENT_NAME_PATTERNS[SITE]) == []
    assert matching_subfolders("", IPOKER_CLIENT_NAME_PATTERNS[SITE]) == []


# --------------------------------------------------------------------------
# Reading the Windows registry
# --------------------------------------------------------------------------


class FakeKey:
    def __init__(self, values: dict[str, str] | None = None, children: dict[str, Any] | None = None) -> None:
        self.values = values or {}
        self.children = children or {}

    def __enter__(self) -> FakeKey:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class FakeWinreg:
    """The part of ``winreg`` the detector uses, answering from a dict."""

    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"

    def __init__(self, roots: dict[tuple[str, str], dict[str, dict[str, str]]]) -> None:
        self.roots = roots

    def OpenKey(self, parent: Any, name: str) -> FakeKey:  # noqa: N802 - winreg's name
        if isinstance(parent, FakeKey):
            if name not in parent.children:
                raise FileNotFoundError(name)
            return FakeKey(values=parent.children[name])
        if (parent, name) not in self.roots:
            raise FileNotFoundError(name)
        return FakeKey(children=self.roots[(parent, name)])

    def EnumKey(self, key: FakeKey, index: int) -> str:  # noqa: N802 - winreg's name
        names = list(key.children)
        if index >= len(names):
            raise OSError("no more data")
        return names[index]

    def QueryValueEx(self, key: FakeKey, name: str) -> tuple[str, int]:  # noqa: N802 - winreg's name
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], 1


PATTERNS = IPOKER_CLIENT_NAME_PATTERNS[SITE]


def test_the_install_location_of_a_matching_uninstall_entry_is_returned() -> None:
    winreg = FakeWinreg(
        {
            ("HKCU", UNINSTALL_KEY): {
                "{1}": {"DisplayName": "bet365 Poker France", "InstallLocation": r"E:\Poker\bet365 France"},
                "{2}": {"DisplayName": "bet365 Poker", "InstallLocation": r"E:\Poker\bet365"},
                "{3}": {"DisplayName": "Some Other Program", "InstallLocation": r"E:\Other"},
            },
        },
    )

    assert windows_registry_install_dirs(PATTERNS, winreg) == [r"E:\Poker\bet365 France"]


def test_the_icon_folder_stands_in_for_a_missing_install_location() -> None:
    winreg = FakeWinreg(
        {
            ("HKLM", UNINSTALL_KEY_WOW64): {
                "bet365.fr": {"DisplayName": "bet365.fr Poker", "DisplayIcon": '"E:\\Poker\\b365fr\\client.exe",0'},
            },
        },
    )

    [location] = windows_registry_install_dirs(PATTERNS, winreg)

    assert same_path(location, Path("E:\\Poker\\b365fr"))


def test_an_app_paths_executable_gives_its_folder() -> None:
    winreg = FakeWinreg(
        {
            ("HKCU", APP_PATHS_KEY): {
                "bet365fr.exe": {"": r"E:\Poker\b365\bet365fr.exe"},
                "bet365.exe": {"": r"E:\Poker\intl\bet365.exe"},
            },
            ("HKLM", APP_PATHS_KEY): {
                "bet365frpoker.exe": {"Path": r"E:\Poker\b365 path", "": r"E:\elsewhere\x.exe"},
            },
        },
    )

    found = windows_registry_install_dirs(PATTERNS, winreg)

    assert len(found) == 2
    assert same_path(found[0], Path("E:\\Poker\\b365"))
    assert found[1] == r"E:\Poker\b365 path"


def test_the_same_location_is_returned_once() -> None:
    entry = {"DisplayName": "bet365 Poker France", "InstallLocation": r"E:\Poker\bet365 France"}
    winreg = FakeWinreg({("HKCU", UNINSTALL_KEY): {"a": entry}, ("HKLM", UNINSTALL_KEY): {"b": entry}})

    assert windows_registry_install_dirs(PATTERNS, winreg) == [r"E:\Poker\bet365 France"]


def test_an_empty_registry_yields_nothing() -> None:
    assert windows_registry_install_dirs(PATTERNS, FakeWinreg({})) == []


def test_an_unreadable_entry_is_skipped() -> None:
    class Flaky(FakeWinreg):
        def OpenKey(self, parent: Any, name: str) -> FakeKey:  # noqa: N802
            if name == "{broken}":
                raise PermissionError(name)
            return super().OpenKey(parent, name)

    winreg = Flaky(
        {
            ("HKCU", UNINSTALL_KEY): {
                "{broken}": {},
                "{ok}": {"DisplayName": "bet365.fr", "InstallLocation": r"E:\b365fr"},
            },
        },
    )

    assert windows_registry_install_dirs(PATTERNS, winreg) == [r"E:\b365fr"]


def test_without_winreg_nothing_is_read(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "winreg", None)

    assert windows_registry_install_dirs(PATTERNS) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('"E:\\Poker\\b365\\client.exe",0', "E:\\Poker\\b365"),
        ("E:\\Poker\\b365\\client.exe,0", "E:\\Poker\\b365"),
        ("E:\\Poker\\b365\\client.exe", "E:\\Poker\\b365"),
    ],
)
def test_the_folder_of_an_executable_value(value: str, expected: str) -> None:
    assert same_path(_folder_of_executable(value), Path(expected))


def test_an_empty_executable_value_has_no_folder() -> None:
    assert _folder_of_executable("") == ""


# --------------------------------------------------------------------------
# Finding the client on macOS (bundle id still to be confirmed)
# --------------------------------------------------------------------------


def container_support(root: Path, bundle: str) -> Path:
    return tree(root, "Library", "Containers", bundle, "Data", "Library", "Application Support")


@pytest.mark.parametrize("bundle", ["com.bet365.poker", "fr.bet365.poker.macos", "com.bet365.pokerfr.app"])
def test_a_known_folder_name_is_found_in_a_bet365_container(config, tmp_path, bundle) -> None:
    tables = account(container_support(tmp_path, bundle) / "bet365.fr Online Poker", "alice")

    found = detect_on_macos(iPokerDetector(config), tmp_path)

    assert found["detected"] is True
    assert found["heroname"] == "alice"
    assert same_path(found["hhpath"], tables)


def test_an_unknown_french_folder_is_found_when_the_container_can_be_listed(config, tmp_path) -> None:
    tables = account(container_support(tmp_path, "com.bet365.poker") / "bet365 Poker FR 2")

    found = detect_on_macos(iPokerDetector(config), tmp_path)

    assert same_path(found["hhpath"], tables)


def test_the_international_container_folder_is_not_taken_for_the_french_one(config, tmp_path) -> None:
    account(container_support(tmp_path, "com.bet365.poker") / "bet365 Poker")

    assert detect_on_macos(iPokerDetector(config), tmp_path) == NOT_DETECTED


def test_the_plain_application_support_folder_is_the_fallback(config, tmp_path) -> None:
    tables = account(Path(mac_paths(tmp_path)["app_support"]) / SITE / "data")

    found = detect_on_macos(iPokerDetector(config), tmp_path)

    assert same_path(found["hhpath"], tables)


def test_a_protected_container_is_found_by_the_configured_screen_name(config, tmp_path) -> None:
    # macOS 14+ lets fpdb stat inside another app's container but not list it.
    base = container_support(tmp_path, "com.bet365.poker") / "bet365.fr Online Poker"
    account(base, "alice")
    config.supported_sites = {SITE: SimpleNamespace(hero_aliases=["alice"])}
    detector = iPokerDetector(config)
    real_listdir = os.listdir

    def deny_container(path: Any) -> list[str]:
        if Path(path) == base:
            raise PermissionError(1, "Operation not permitted", str(path))
        return real_listdir(path)

    with patch("os.listdir", side_effect=deny_container):
        found = detect_on_macos(detector, tmp_path)

    assert found["detected"] is True
    assert found["heroname"] == "alice"
    assert detector.protected_skins == {SITE: str(base)}
