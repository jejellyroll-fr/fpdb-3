"""Finding a poker client's hand histories on disk.

This is what tells a new player "your hands are here" the first time fpdb
opens. Each detector builds the candidate paths of one room for one operating
system, and almost none of it can run on the machine of whoever is testing:
the Windows branches never execute on Linux, and the Linux ones never execute
on macOS.

So the platform is driven rather than observed. Each test sets the detector's
platform, points the path helpers at a directory it built itself, and checks
what comes back -- which exercises all three operating systems from any one of
them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import fpdb_3_legacy.DetectInstalledSites as detect_module
from fpdb_3_legacy.DetectInstalledSites import (
    ACRDetector,
    CPNDetector,
    DetectInstalledSites,
    PartyGamingDetector,
    PokerStarsDetector,
    SealsWithClubsDetector,
    SiteDetector,
    WinamaxDetector,
    iPokerDetector,
)

NOT_DETECTED = {"detected": False, "hhpath": "", "heroname": "", "tspath": ""}


def path_ends_with(path: str, suffix: str) -> bool:
    """Check that *path* ends with *suffix* regardless of path separator.

    On Windows, Path joins produce backslashes while test literals use forward
    slashes.  Normalising both sides makes the comparison portable.
    """
    return os.path.normpath(path).endswith(os.path.normpath(suffix))


@pytest.fixture
def config() -> Any:
    stub = MagicMock()
    stub.os_family = "Mac"
    return stub


def tree(root: Path, *parts: str) -> Path:
    """Create a directory and return it."""
    target = root.joinpath(*parts)
    target.mkdir(parents=True, exist_ok=True)
    return target


# Each helper answers with every key its platform's detectors read, all of them
# under the test's own directory. A partial dict would raise KeyError as soon as
# a detector reached a branch the test did not think about, so they are complete
# and the test only creates the one tree it cares about.


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
        "app_support": str(root / "Application Support"),
        "applications": str(root / "Applications"),
        "documents": str(root / "Documents"),
    }


def linux_paths(root: Path) -> dict[str, str]:
    return {
        "wine_drive_c": str(root / "drive_c"),
        "wine_program_files": str(root / "drive_c" / "Program Files"),
        "wine_program_files_x86": str(root / "drive_c" / "Program Files (x86)"),
        "wine_users": str(root / "drive_c" / "users"),
    }


def on_platform(name: str, root: Path) -> Any:
    """Patch the path helper of one platform to answer from `root`."""
    helper, builder = {
        "Windows": ("get_windows_paths", windows_paths),
        "Darwin": ("get_mac_paths", mac_paths),
        "Linux": ("get_linux_paths", linux_paths),
    }[name]
    return patch.object(detect_module, helper, return_value=builder(root))


# --------------------------------------------------------------------------
# The shared helpers
# --------------------------------------------------------------------------


def test_the_first_path_that_exists_is_the_one_taken(config, tmp_path) -> None:
    second = tree(tmp_path, "second")
    detector = SiteDetector(config)

    assert detector._check_path_exists(str(tmp_path / "first"), str(second)) == str(second)


def test_no_candidate_path_existing_means_nothing_found(config, tmp_path) -> None:
    detector = SiteDetector(config)

    assert detector._check_path_exists(str(tmp_path / "a"), str(tmp_path / "b")) is None


def test_an_empty_candidate_is_skipped(config, tmp_path) -> None:
    # A path helper returns "" for a location that does not apply to the
    # platform, and Path("") is the current directory, which always exists.
    existing = tree(tmp_path, "real")
    detector = SiteDetector(config)

    assert detector._check_path_exists("", str(existing)) == str(existing)


def test_every_account_folder_is_offered_as_a_hero(config, tmp_path) -> None:
    tree(tmp_path, "Alice")
    tree(tmp_path, "Bob")
    detector = SiteDetector(config)

    assert sorted(detector._find_heroes_in_path(str(tmp_path))) == ["Alice", "Bob"]


@pytest.mark.parametrize("folder", ["archive", "Backup", "TournSummary", "Replayer", "Avatars", "Sounds"])
def test_a_folder_that_is_not_an_account_is_not_a_hero(config, tmp_path, folder) -> None:
    # Matching is case-insensitive: the clients do not agree on capitalisation.
    tree(tmp_path, folder)
    tree(tmp_path, "Alice")
    detector = SiteDetector(config)

    assert detector._find_heroes_in_path(str(tmp_path)) == ["Alice"]


def test_a_hidden_folder_is_not_a_hero(config, tmp_path) -> None:
    tree(tmp_path, ".DS_Store_dir")
    tree(tmp_path, "Alice")
    detector = SiteDetector(config)

    assert detector._find_heroes_in_path(str(tmp_path)) == ["Alice"]


def test_a_file_beside_the_accounts_is_not_a_hero(config, tmp_path) -> None:
    (tmp_path / "readme.txt").write_text("not an account", encoding="utf-8")
    tree(tmp_path, "Alice")
    detector = SiteDetector(config)

    assert detector._find_heroes_in_path(str(tmp_path)) == ["Alice"]


def test_a_path_that_is_not_there_yields_no_heroes(config, tmp_path) -> None:
    detector = SiteDetector(config)

    assert detector._find_heroes_in_path(str(tmp_path / "absent")) == []


def test_a_path_that_cannot_be_read_yields_no_heroes(config, tmp_path) -> None:
    # A client directory owned by another user must not abort detection.
    detector = SiteDetector(config)

    with patch("os.listdir", side_effect=PermissionError("denied")):
        assert detector._find_heroes_in_path(str(tmp_path)) == []


def test_the_base_detector_finds_nothing_of_its_own(config) -> None:
    assert SiteDetector(config).detect() == NOT_DETECTED


# --------------------------------------------------------------------------
# Winamax, on each operating system
# --------------------------------------------------------------------------


def test_winamax_is_found_on_macos(config, tmp_path) -> None:
    support = tmp_path / "Application Support"
    tree(support, "Winamax", "documents", "accounts", "Hero", "history")
    detector = WinamaxDetector(config)
    detector.platform = "Darwin"

    with patch.object(detect_module, "get_mac_paths", return_value={"app_support": str(support)}):
        found = detector.detect()

    assert found["detected"]
    assert found["heroname"] == "Hero"
    assert path_ends_with(found["hhpath"], "accounts/Hero/history")


def test_winamax_is_found_on_windows(config, tmp_path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    tree(appdata, "Winamax", "accounts", "Villain", "history")
    detector = WinamaxDetector(config)
    detector.platform = "Windows"

    with patch.object(
        detect_module,
        "get_windows_paths",
        return_value={"appdata": str(appdata), "local_appdata": str(tmp_path / "nowhere")},
    ):
        found = detector.detect()

    assert found["detected"]
    assert found["heroname"] == "Villain"


def test_winamax_is_found_on_linux_next_to_the_native_client(config, tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    tree(home, ".config", "winamax", "documents", "accounts", "Penguin", "history")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    detector = WinamaxDetector(config)
    detector.platform = "Linux"

    found = detector.detect()

    assert found["detected"]
    assert found["heroname"] == "Penguin"


def test_winamax_reports_nothing_when_the_client_is_not_installed(config, tmp_path) -> None:
    detector = WinamaxDetector(config)
    detector.platform = "Darwin"

    with patch.object(detect_module, "get_mac_paths", return_value={"app_support": str(tmp_path)}):
        assert detector.detect() == NOT_DETECTED


def test_an_account_without_a_history_folder_is_not_reported(config, tmp_path) -> None:
    # An account that never played has no history directory, and offering its
    # path would point the importer at nothing.
    support = tmp_path / "Application Support"
    tree(support, "Winamax", "documents", "accounts", "NeverPlayed")
    detector = WinamaxDetector(config)
    detector.platform = "Darwin"

    with patch.object(detect_module, "get_mac_paths", return_value={"app_support": str(support)}):
        assert detector.detect() == NOT_DETECTED


# --------------------------------------------------------------------------
# PokerStars, whose variants live side by side
# --------------------------------------------------------------------------


def test_a_pokerstars_variant_is_found_on_macos(config, tmp_path) -> None:
    support = tmp_path / "Application Support"
    tree(support, "PokerStarsFR", "HandHistory", "Hero")
    tree(support, "PokerStarsFR", "TournSummary", "Hero")
    detector = PokerStarsDetector(config)
    detector.platform = "Darwin"

    with patch.object(
        detect_module,
        "get_mac_paths",
        return_value={"app_support": str(support), "documents": str(tmp_path / "Documents")},
    ):
        found = detector._detect_variant("PokerStarsFR")

    assert found["detected"]
    assert found["heroname"] == "Hero"
    assert path_ends_with(found["hhpath"], "HandHistory/Hero")
    assert path_ends_with(found["tspath"], "TournSummary/Hero")


def test_a_pokerstars_variant_is_found_on_windows(config, tmp_path) -> None:
    local = tmp_path / "AppData" / "Local"
    tree(local, "PokerStars", "HandHistory", "Hero")
    tree(local, "PokerStars", "TournSummary", "Hero")
    detector = PokerStarsDetector(config)
    detector.platform = "Windows"
    elsewhere = str(tmp_path / "nowhere")

    with patch.object(
        detect_module,
        "get_windows_paths",
        return_value={
            "local_appdata": str(local),
            "appdata": elsewhere,
            "program_files": elsewhere,
            "program_files_x86": elsewhere,
        },
    ):
        found = detector._detect_variant("PokerStars")

    assert found["detected"]
    assert found["heroname"] == "Hero"


def test_a_variant_that_is_not_installed_is_reported_as_absent(config, tmp_path) -> None:
    detector = PokerStarsDetector(config)
    detector.platform = "Darwin"

    with patch.object(
        detect_module,
        "get_mac_paths",
        return_value={"app_support": str(tmp_path), "documents": str(tmp_path)},
    ):
        assert detector._detect_variant("PokerStarsIT")["detected"] is False


# --------------------------------------------------------------------------
# iPoker, a network of skins that each ship their own client
# --------------------------------------------------------------------------


def test_an_ipoker_skin_is_found_on_windows(config, tmp_path) -> None:
    paths = windows_paths(tmp_path)
    tree(Path(paths["local_appdata"]), "Betclic Poker", "data", "Hero", "History", "Data", "Tables")
    detector = iPokerDetector(config)
    detector.platform = "Windows"

    with on_platform("Windows", tmp_path):
        found = detector._detect_skin("Betclic Poker")

    assert found["detected"]
    assert found["heroname"] == "Hero"


def test_an_ipoker_skin_is_found_under_wine(config, tmp_path) -> None:
    paths = linux_paths(tmp_path)
    tree(Path(paths["wine_users"]), "hero", "AppData", "Local", "NetBet", "data", "Hero", "History", "Data", "Tables")
    detector = iPokerDetector(config)
    detector.platform = "Linux"

    with on_platform("Linux", tmp_path):
        found = detector._detect_skin("NetBet")

    assert found["detected"]
    assert found["heroname"] == "Hero"


def test_an_ipoker_skin_is_found_in_wine_program_files(config, tmp_path) -> None:
    # No Wine user profile carries the client, so the install directory is the
    # fallback -- the branch a bottle created by hand ends up on.
    paths = linux_paths(tmp_path)
    tree(Path(paths["wine_users"]))
    tree(Path(paths["wine_program_files"]), "NetBet", "data", "Hero", "History", "Data", "Tables")
    detector = iPokerDetector(config)
    detector.platform = "Linux"

    with on_platform("Linux", tmp_path):
        found = detector._detect_skin("NetBet")

    assert found["detected"]


def test_an_ipoker_skin_that_is_not_installed_is_reported_as_absent(config, tmp_path) -> None:
    detector = iPokerDetector(config)
    detector.platform = "Windows"

    with on_platform("Windows", tmp_path):
        assert detector._detect_skin("NetBet")["detected"] is False


# --------------------------------------------------------------------------
# The shared PokerClient folder, where several iPoker skins install together
# --------------------------------------------------------------------------


def pokerclient(root: Path, folder: str, hero: str = "Hero", *, tournaments: bool = True) -> Path:
    """Lay out one skin the way the shared PokerClient installer does."""
    base = root / folder / "data" / hero / "History" / "Data"
    (base / "Tables").mkdir(parents=True)
    if tournaments:
        (base / "Tournaments").mkdir(parents=True)
    return base


def test_a_skin_of_the_shared_folder_is_found_on_windows(config, tmp_path) -> None:
    paths = windows_paths(tmp_path)
    pokerclient(Path(paths["local_appdata"]) / "PokerClient", "betclicpoker")
    detector = iPokerDetector(config)
    detector.platform = "Windows"

    with on_platform("Windows", tmp_path):
        found = detector._detect_pokerclient()

    assert found["detected"]
    assert found["heroname"] == "Hero"
    assert found["skin"] == "Betclic Poker"


def test_the_folder_name_is_translated_to_the_room_it_belongs_to(config, tmp_path) -> None:
    # The installer names directories after the brand's domain, which is not
    # what the rest of fpdb calls the room.
    paths = mac_paths(tmp_path)
    pokerclient(Path(paths["app_support"]) / "PokerClient", "nordicbet.com")
    detector = iPokerDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        found = detector._detect_pokerclient()

    assert found["skin"] == "NordicBet Poker"


def test_a_shared_folder_skin_is_found_under_wine(config, tmp_path) -> None:
    paths = linux_paths(tmp_path)
    pokerclient(Path(paths["wine_users"]) / "hero" / "AppData" / "Local" / "PokerClient", "unibet")
    detector = iPokerDetector(config)
    detector.platform = "Linux"

    with on_platform("Linux", tmp_path):
        found = detector._detect_pokerclient()

    assert found["detected"]
    assert found["skin"] == "Unibet Poker"


@pytest.mark.parametrize("noise", ["cache", "logs", "plugins", "qml", "missions"])
def test_the_clients_own_folders_are_not_taken_for_players(config, tmp_path, noise) -> None:
    # These sit beside the account directories and would otherwise be reported
    # as the hero's name.
    root = Path(mac_paths(tmp_path)["app_support"]) / "PokerClient"
    pokerclient(root, "titan", hero="RealPlayer")
    (root / "titan" / "data" / noise / "History" / "Data" / "Tables").mkdir(parents=True)
    detector = iPokerDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        found = detector._detect_pokerclient()

    assert found["heroname"] == "RealPlayer"


def test_a_player_without_tournaments_still_reports_the_cash_hands(config, tmp_path) -> None:
    root = Path(mac_paths(tmp_path)["app_support"]) / "PokerClient"
    pokerclient(root, "sky", tournaments=False)
    detector = iPokerDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        found = detector._detect_pokerclient()

    assert found["detected"]
    assert found["tspath"] == ""


def test_no_shared_folder_at_all_is_reported_as_absent(config, tmp_path) -> None:
    detector = iPokerDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        assert detector._detect_pokerclient() == NOT_DETECTED


def test_a_shared_folder_holding_no_skin_is_reported_as_absent(config, tmp_path) -> None:
    tree(Path(mac_paths(tmp_path)["app_support"]), "PokerClient")
    detector = iPokerDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        assert detector._detect_pokerclient() == NOT_DETECTED


def test_a_shared_folder_that_cannot_be_read_is_reported_rather_than_raised(config, tmp_path) -> None:
    pokerclient(Path(mac_paths(tmp_path)["app_support"]) / "PokerClient", "coral")
    detector = iPokerDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path), patch("os.listdir", side_effect=PermissionError("denied")):
        assert detector._detect_pokerclient() == NOT_DETECTED


# --------------------------------------------------------------------------
# ACR, whose Windows branch is hard-coded to C:\
# --------------------------------------------------------------------------


def test_acr_is_found_under_wine(config, tmp_path) -> None:
    # The Windows branch names C:\ literally and so cannot be redirected at a
    # directory; Wine is the branch that reads a path helper.
    paths = linux_paths(tmp_path)
    tree(Path(paths["wine_drive_c"]), "ACR Poker", "handHistory", "Hero")
    tree(Path(paths["wine_drive_c"]), "ACR Poker", "TournamentSummary", "Hero")
    detector = ACRDetector(config)
    detector.platform = "Linux"

    with on_platform("Linux", tmp_path):
        found = detector._detect_skin("ACR Poker")

    assert found["detected"]
    assert found["heroname"] == "Hero"
    assert path_ends_with(found["tspath"], "TournamentSummary/Hero")


def test_acr_is_found_on_macos(config, tmp_path) -> None:
    paths = mac_paths(tmp_path)
    tree(Path(paths["app_support"]), "BlackChip Poker", "handHistory", "Hero")
    detector = ACRDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        found = detector._detect_skin("BlackChip Poker")

    assert found["detected"]
    assert found["skin"] == "BlackChip Poker"


def test_acr_without_a_summary_folder_still_reports_the_hands(config, tmp_path) -> None:
    # Summaries are optional: a player who only plays cash has no such folder,
    # and refusing the room over it would lose the hand histories too.
    paths = mac_paths(tmp_path)
    tree(Path(paths["app_support"]), "ACR Poker", "handHistory", "Hero")
    detector = ACRDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        found = detector._detect_skin("ACR Poker")

    assert found["detected"]
    assert found["tspath"] == ""


def test_an_acr_history_folder_without_an_account_is_not_reported(config, tmp_path) -> None:
    paths = mac_paths(tmp_path)
    tree(Path(paths["app_support"]), "ACR Poker", "handHistory")
    detector = ACRDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        assert detector._detect_skin("ACR Poker") == NOT_DETECTED


# --------------------------------------------------------------------------
# PartyGaming and the Cake network, which share a directory layout
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("detector_class", "skin"),
    [(PartyGamingDetector, "PartyPoker"), (CPNDetector, "Cake Poker")],
)
def test_a_skin_is_found_on_windows(config, tmp_path, detector_class, skin) -> None:
    paths = windows_paths(tmp_path)
    tree(Path(paths["local_appdata"]), skin, "HandHistory", "Hero")
    tree(Path(paths["local_appdata"]), skin, "TournSummary", "Hero")
    detector = detector_class(config)
    detector.platform = "Windows"

    with on_platform("Windows", tmp_path):
        found = detector._detect_skin(skin)

    assert found["detected"]
    assert found["heroname"] == "Hero"


@pytest.mark.parametrize(
    ("detector_class", "skin"),
    [(PartyGamingDetector, "PartyPoker"), (CPNDetector, "Cake Poker")],
)
def test_a_skin_is_found_on_macos(config, tmp_path, detector_class, skin) -> None:
    paths = mac_paths(tmp_path)
    tree(Path(paths["app_support"]), skin, "HandHistory", "Hero")
    detector = detector_class(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        found = detector._detect_skin(skin)

    assert found["detected"]
    assert found["heroname"] == "Hero"


@pytest.mark.parametrize(
    ("detector_class", "skin"),
    [(PartyGamingDetector, "PartyPoker"), (CPNDetector, "Cake Poker")],
)
def test_a_skin_is_found_under_wine(config, tmp_path, detector_class, skin) -> None:
    paths = linux_paths(tmp_path)
    tree(Path(paths["wine_program_files"]), skin, "HandHistory", "Hero")
    detector = detector_class(config)
    detector.platform = "Linux"

    with on_platform("Linux", tmp_path):
        found = detector._detect_skin(skin)

    assert found["detected"]


@pytest.mark.parametrize("platform", ["Darwin", "Linux"])
def test_the_windows_only_install_scan_is_skipped_elsewhere(config, platform) -> None:
    # This scan reads C:\Programs literally, so it has nothing to look at on
    # any other system and must not be attempted there.
    detector = PartyGamingDetector(config)
    detector.platform = platform

    assert detector._detect_programs_installations() == []


@pytest.mark.parametrize("detector_class", [PartyGamingDetector, CPNDetector])
def test_a_skin_that_is_not_installed_is_reported_as_absent(config, tmp_path, detector_class) -> None:
    detector = detector_class(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        assert detector._detect_skin("PartyPoker")["detected"] is False


# --------------------------------------------------------------------------
# Seals with Clubs, which has one client rather than a family of skins
# --------------------------------------------------------------------------


def hand_file(folder: Path, name: str = "swc.txt") -> None:
    """Seals is the one detector that wants files, not just a directory."""
    (folder / name).write_text("SwC Poker Hand #1\n", encoding="utf-8")


def test_seals_with_clubs_is_found_on_windows(config, tmp_path) -> None:
    paths = windows_paths(tmp_path)
    hand_file(tree(Path(paths["userprofile"]), "Documents", "SwC Poker", "Hand History", "Hero"))
    detector = SealsWithClubsDetector(config)
    detector.platform = "Windows"

    with on_platform("Windows", tmp_path):
        found = detector.detect()

    assert found["detected"]
    assert found["heroname"] == "Hero"


def test_seals_with_clubs_is_found_in_a_wine_user_profile(config, tmp_path) -> None:
    paths = linux_paths(tmp_path)
    hand_file(tree(Path(paths["wine_users"]), "hero", "Documents", "SwC Poker", "Hand History", "Villain"))
    detector = SealsWithClubsDetector(config)
    detector.platform = "Linux"

    with on_platform("Linux", tmp_path):
        found = detector.detect()

    assert found["detected"]
    assert found["heroname"] == "Villain"


def test_seals_with_clubs_names_the_hero_itself_when_the_hands_are_loose(config, tmp_path) -> None:
    # The client writes straight into Hand History with no account folder, so
    # there is no name to read and the detector supplies a generic one.
    paths = mac_paths(tmp_path)
    hand_file(tree(Path(paths["documents"]), "SwC Poker", "Hand History"))
    detector = SealsWithClubsDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        found = detector.detect()

    assert found["detected"]
    assert found["heroname"] == "Hero"
    assert path_ends_with(found["hhpath"], "Hand History")


def test_a_seals_folder_holding_no_hands_is_not_reported(config, tmp_path) -> None:
    # The directory survives uninstalling the client; pointing the importer at
    # an empty one would report a room the player no longer has.
    paths = mac_paths(tmp_path)
    tree(Path(paths["documents"]), "SwC Poker", "Hand History", "Hero")
    detector = SealsWithClubsDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        assert detector.detect() == NOT_DETECTED


def test_seals_with_clubs_is_not_reported_when_absent(config, tmp_path) -> None:
    detector = SealsWithClubsDetector(config)
    detector.platform = "Darwin"

    with on_platform("Darwin", tmp_path):
        assert detector.detect()["detected"] is False


# --------------------------------------------------------------------------
# What the application asks for
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def detector() -> Any:
    return DetectInstalledSites()


def test_the_rooms_it_can_look_for_are_listed(detector) -> None:
    assert {"PokerStars", "Winamax", "iPoker", "ACR"} <= set(detector.supportedSites)


def test_nothing_is_reported_for_a_room_it_does_not_know(detector) -> None:
    assert detector.get_site_info("A Room That Does Not Exist") is None


def test_what_was_detected_is_a_subset_of_what_was_looked_for(detector) -> None:
    assert set(detector.get_detected_sites()) <= set(detector.supportedSites)


def test_each_detected_room_reports_a_hand_history_path(detector) -> None:
    # Machine-independent on purpose: which rooms are installed differs, but a
    # room reported as detected must say where its hands are.
    for name in detector.get_detected_sites():
        info = detector.get_site_info(name)
        assert info["detected"] is True
        assert info["hhpath"]


def test_the_rooms_it_can_look_for_are_known_without_building_a_detector(detector) -> None:
    # The auto-detect button in Site Preferences only needs this list, and asking
    # a whole DetectInstalledSites for it meant one config parse and one
    # filesystem sweep per site card.
    assert list(detect_module.SUPPORTED_SITES) == detector.supportedSites
    assert detect_module.is_network_detectable("PokerStars")
    assert not detect_module.is_network_detectable("A Room That Does Not Exist")


@pytest.mark.parametrize("network", ["PokerStars", "iPoker", "PartyGaming"])
def test_looking_for_one_room_still_answers_for_that_room(network) -> None:
    # Site Preferences detects the network of the card that was clicked, rather
    # than sweeping all of them, so the scoped construction has to fill in
    # everything the caller reads back.
    scoped = DetectInstalledSites(sitename=network)

    assert network in scoped.sitestatusdict
    assert set(scoped.sitestatusdict[network]) >= {"detected", "hhpath", "heroname", "tspath"}
    for accessor in ("get_all_pokerstars_variants", "get_all_ipoker_skins", "get_all_partypoker_skins"):
        assert isinstance(getattr(scoped, accessor)(), list)


@pytest.mark.parametrize(
    "accessor", ["get_all_pokerstars_variants", "get_all_ipoker_skins", "get_all_partypoker_skins"]
)
def test_every_skin_accessor_answers_with_a_list(detector, accessor) -> None:
    result = getattr(detector, accessor)()

    assert isinstance(result, list)
    assert all(entry["detected"] for entry in result)


# --------------------------------------------------------------------------
# The command line, which is how the module is run on its own
# --------------------------------------------------------------------------
#
# Every test here stands in for the detector: run against the real one, what
# is printed depends on which poker clients the machine happens to have.


@pytest.fixture
def stub_detector() -> Any:
    stub = MagicMock()
    stub.supported_sites = ["PokerStars", "Winamax"]
    stub.get_detected_sites.return_value = ["Winamax"]
    stub.get_site_info.return_value = {"detected": True, "hhpath": "/hands/Winamax", "heroname": "Hero"}
    with patch.object(detect_module, "DetectInstalledSites", return_value=stub):
        yield stub


def test_no_argument_at_all_prints_the_help(capsys) -> None:
    assert detect_module.main([]) == 0

    assert "usage:" in capsys.readouterr().out


def test_the_supported_sites_are_listed(stub_detector, capsys) -> None:
    assert detect_module.main(["--supported-sites"]) == 0

    printed = capsys.readouterr().out
    assert "PokerStars" in printed
    assert "Total: 2 sites supported" in printed


def test_the_detected_sites_are_listed(stub_detector, capsys) -> None:
    assert detect_module.main(["--list-detected"]) == 0

    assert "Winamax" in capsys.readouterr().out


def test_nothing_detected_is_said_plainly(stub_detector, capsys) -> None:
    stub_detector.get_detected_sites.return_value = []

    assert detect_module.main(["--list-detected"]) == 0

    assert "No poker sites detected" in capsys.readouterr().out


def test_the_paths_are_shown_beside_the_sites(stub_detector, capsys) -> None:
    assert detect_module.main(["--show-paths"]) == 0

    assert "/hands/Winamax" in capsys.readouterr().out


def test_a_site_detected_without_a_path_says_so(stub_detector, capsys) -> None:
    stub_detector.get_site_info.return_value = {"detected": True}

    detect_module.main(["--show-paths"])

    assert "Path: Not available" in capsys.readouterr().out


def test_the_details_of_one_site_are_shown(stub_detector, capsys) -> None:
    assert detect_module.main(["--show-info", "Winamax"]) == 0

    assert "Heroname: Hero" in capsys.readouterr().out


def test_asking_about_a_site_that_was_not_detected_is_answered(stub_detector, capsys) -> None:
    assert detect_module.main(["--show-info", "PokerStars"]) == 0

    assert "not detected on this system" in capsys.readouterr().out


def test_a_detection_failure_is_reported_rather_than_raised(capsys) -> None:
    with patch.object(detect_module, "DetectInstalledSites", side_effect=OSError("disk gone")):
        assert detect_module.main(["--list-detected"]) == 1

    assert "Error during site detection" in capsys.readouterr().out


# --------------------------------------------------------------------------
# The interactive menu
# --------------------------------------------------------------------------


def answers(*replies: str) -> Any:
    return patch("builtins.input", side_effect=list(replies))


def test_the_menu_runs_until_it_is_asked_to_stop(stub_detector, capsys) -> None:
    with answers("5"):
        assert detect_module.run_interactive_menu() == 0

    assert "Exiting..." in capsys.readouterr().out


def test_the_menu_detects_on_request(stub_detector, capsys) -> None:
    with answers("1", "5"):
        detect_module.run_interactive_menu()

    assert "Found 1 sites" in capsys.readouterr().out


def test_the_menu_says_when_it_found_nothing(stub_detector, capsys) -> None:
    stub_detector.get_detected_sites.return_value = []

    with answers("1", "5"):
        detect_module.run_interactive_menu()

    assert "No poker sites detected" in capsys.readouterr().out


def test_the_menu_lists_the_supported_sites(stub_detector, capsys) -> None:
    with answers("2", "5"):
        detect_module.run_interactive_menu()

    assert "Supported sites (2)" in capsys.readouterr().out


def test_the_menu_shows_the_details_of_a_site(stub_detector, capsys) -> None:
    with answers("3", "Winamax", "5"):
        detect_module.run_interactive_menu()

    assert "Heroname: Hero" in capsys.readouterr().out


def test_the_menu_rejects_a_site_it_did_not_detect(stub_detector, capsys) -> None:
    with answers("3", "PokerStars", "5"):
        detect_module.run_interactive_menu()

    assert "not in detected sites" in capsys.readouterr().out


def test_the_menu_asks_for_detection_before_details(stub_detector, capsys) -> None:
    stub_detector.get_detected_sites.return_value = []

    with answers("3", "5"):
        detect_module.run_interactive_menu()

    assert "Run detection first" in capsys.readouterr().out


def test_the_menu_shows_the_paths(stub_detector, capsys) -> None:
    with answers("4", "5"):
        detect_module.run_interactive_menu()

    assert "/hands/Winamax" in capsys.readouterr().out


def test_an_unknown_choice_is_refused_without_leaving_the_menu(stub_detector, capsys) -> None:
    with answers("9", "5"):
        detect_module.run_interactive_menu()

    assert "Invalid choice" in capsys.readouterr().out


def test_interrupting_the_menu_leaves_it(stub_detector, capsys) -> None:
    # Ctrl-C at the prompt is how anyone actually leaves this menu.
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        assert detect_module.run_interactive_menu() == 0

    assert "Exiting..." in capsys.readouterr().out


def test_the_menu_reports_a_detector_that_will_not_start(capsys) -> None:
    with patch.object(detect_module, "DetectInstalledSites", side_effect=OSError("disk gone")):
        assert detect_module.run_interactive_menu() == 1

    assert "Error in interactive menu" in capsys.readouterr().out


def test_the_interactive_flag_opens_the_menu(stub_detector) -> None:
    with answers("5"):
        assert detect_module.main(["--interactive"]) == 0
