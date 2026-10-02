"""Opening a solver review straight in PreflopAdvisor (#413).

How PreflopAdvisor is found (a configured path, the console script on the
PATH, a macOS bundle) and what starting it on a document means: the document
written, then the program started with ``--review`` and that file. Nothing
here starts a real process, and the configuration is a throwaway copy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy.hand_review_payload import (
    PREFLOP_ADVISOR_SCRIPT,
    REVIEW_OPTION,
    PreflopAdvisorTransport,
    preflop_advisor_command,
)

ROOT = Path(__file__).resolve().parents[1]


def nowhere(_name: str) -> None:
    return None


def test_a_configured_program_is_started_as_it_is(tmp_path) -> None:
    program = tmp_path / "PreflopAdvisor.exe"
    program.write_bytes(b"")

    assert preflop_advisor_command(str(program), which=nowhere) == [str(program)]


def test_a_configured_macos_bundle_is_started_through_open(tmp_path) -> None:
    bundle = tmp_path / "PreflopAdvisor.app"
    bundle.mkdir()

    assert preflop_advisor_command(str(bundle), which=nowhere, platform="darwin") == [
        "/usr/bin/open",
        "-n",
        "-a",
        str(bundle),
        "--args",
    ]
    # Elsewhere a folder is no program.
    assert preflop_advisor_command(str(bundle), which=nowhere, platform="linux") is None


def test_without_a_usable_path_the_console_script_on_the_path_is_used(tmp_path) -> None:
    def which(name: str) -> str | None:
        return "/usr/local/bin/preflop_advisor" if name == PREFLOP_ADVISOR_SCRIPT else None

    # Never configured, and configured to a program that has since moved.
    assert preflop_advisor_command(None, which=which) == ["/usr/local/bin/preflop_advisor"]
    assert preflop_advisor_command(str(tmp_path / "gone"), which=which) == ["/usr/local/bin/preflop_advisor"]


def test_nothing_to_start_is_said_rather_than_guessed(tmp_path) -> None:
    assert preflop_advisor_command(None, which=nowhere) is None
    assert preflop_advisor_command(str(tmp_path / "gone"), which=nowhere) is None


def test_the_transport_writes_the_document_then_starts_preflop_advisor_on_it(tmp_path) -> None:
    started: list[tuple[str, list[str]]] = []
    target = tmp_path / "review.json"
    document = {"version": 1, "hands": []}

    transport = PreflopAdvisorTransport(
        ["/usr/bin/open", "-n", "-a", "PreflopAdvisor.app", "--args"],
        target,
        lambda program, arguments: started.append((program, arguments)) or True,
    )

    assert transport.send(document) == str(target)
    assert json.loads(target.read_text(encoding="utf-8")) == document
    assert started == [
        ("/usr/bin/open", ["-n", "-a", "PreflopAdvisor.app", "--args", REVIEW_OPTION, str(target)]),
    ]


def test_a_launch_that_fails_is_an_error(tmp_path) -> None:
    transport = PreflopAdvisorTransport(["preflop_advisor"], tmp_path / "review.json", lambda *_args: False)

    with pytest.raises(OSError, match="preflop_advisor could not be started"):
        transport.send({"version": 1, "hands": []})


def test_the_configuration_remembers_and_forgets_where_preflop_advisor_is(tmp_path, monkeypatch) -> None:
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(configuration, "_find_example_config", lambda _: str(ROOT / "HUD_config.xml.example"))
    path = tmp_path / "HUD_config.xml"
    path.write_text((ROOT / "HUD_config.xml.example").read_text(encoding="utf-8"), encoding="utf-8")

    config = configuration.Config(file=str(path))
    assert "preflop_advisor" not in config.general
    config.set_preflop_advisor_path("/Applications/PreflopAdvisor.app")

    assert config.general["preflop_advisor"] == "/Applications/PreflopAdvisor.app"
    reloaded = configuration.Config(file=str(path))
    assert reloaded.general["preflop_advisor"] == "/Applications/PreflopAdvisor.app"
    assert not reloaded.wrongConfigVersion

    reloaded.set_preflop_advisor_path(None)
    assert "preflop_advisor" not in configuration.Config(file=str(path)).general
