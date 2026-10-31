"""Live capture that reaches into a poker client runs only once its user said yes (#451).

Two capture paths do more than read files a room writes:

- the SwC native capture loads a tap into the SwC client (a DLL injected on
  Windows, ``DYLD_INSERT_LIBRARIES`` / ``LD_PRELOAD`` at launch elsewhere) and
  reads the client's TLS traffic after decryption;
- the CoinPoker capture records the network packets of the CoinPoker client,
  with administrator rights.

Both are off until the user turns them on, after reading what they do. The
answer is kept beside the configuration with the version of the mechanism it
was given for: when a mechanism changes what it does, its version moves and the
question is asked again.

This module is data and checks only. The Qt confirmation lives in
``live_capture_dialog``; a terminal command asks with :func:`confirm_on_terminal`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, TextIO

from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _

#: Where the answers are kept, beside HUD_config.xml.
CONSENT_NAME: Final = "live-capture-consent.json"


@dataclass(frozen=True)
class Mechanism:
    """One capture path, and what turning it on means."""

    key: str
    #: Moves whenever the mechanism changes what it loads or reads.
    version: int
    #: Marked with N_; translate when shown.
    title: str
    what_happens: str


SWC_NATIVE: Final = Mechanism(
    key="swc_native",
    version=1,
    title=N_("SwC client tap (Seals with Clubs)"),
    what_happens=N_(
        "fpdb loads a small library of its own into the SwC Poker client: injected into the running "
        "client on Windows, preloaded when fpdb launches the client on macOS and Linux. Inside the "
        "client, it reads the table traffic after the client has decrypted it, and writes it to a file "
        "fpdb imports. It stays loaded until the client exits."
    ),
)

COINPOKER_PACKETS: Final = Mechanism(
    key="coinpoker_packets",
    version=1,
    title=N_("CoinPoker packet capture"),
    what_happens=N_(
        "fpdb records the network packets exchanged by the CoinPoker client, with administrator "
        "rights (tcpdump, pkexec or a UAC prompt), and rebuilds the hands from them. It reads the "
        "traffic only; it loads nothing into the client."
    ),
)

MECHANISMS: Final = {mechanism.key: mechanism for mechanism in (SWC_NATIVE, COINPOKER_PACKETS)}


class LiveCaptureNotAccepted(RuntimeError):
    """A capture that needs the user's yes was started without it."""

    def __init__(self, mechanism: Mechanism) -> None:
        self.mechanism = mechanism
        super().__init__(
            _("{title} is off. Turn it on in Tools ▸ Live capture… after reading what it does.").format(
                title=_(mechanism.title)
            )
        )


def capture_installed() -> bool:
    """Whether the capture package is in this install: a build may leave it out (#451)."""
    import importlib.util  # noqa: PLC0415 - only asked by the actions that start a capture

    return importlib.util.find_spec("fpdb_3_legacy.capture") is not None


class CaptureNotInstalled(RuntimeError):
    """A capture was started in an install that does not carry the capture package."""

    def __init__(self) -> None:
        super().__init__(
            _("Live capture is not part of this install. From a source install: pip install -e '.[capture]'.")
        )


def consent_path(config_file: str | os.PathLike[str] | None = None) -> Path:
    """The answers file beside ``config_file``, or in fpdb's configuration folder."""
    if config_file:
        return Path(config_file).expanduser().resolve().parent / CONSENT_NAME
    from fpdb_3_legacy.Configuration import CONFIG_PATH  # noqa: PLC0415 - only needed when no file is given

    return Path(CONFIG_PATH) / CONSENT_NAME


def statement(mechanism: Mechanism) -> str:
    """Everything the user reads before saying yes, translated."""
    return "\n\n".join(
        (
            _(mechanism.what_happens),
            _(
                "Anti-cheat systems look for software that loads into a poker client or reads its "
                "traffic. A room may treat it as a breach of its terms and restrict or close the "
                "account, whatever fpdb does with the data."
            ),
            _(
                "Your room's terms prevail. Read them, and turn this on only if they allow it. fpdb "
                "never shows a recommended action and never acts in the client."
            ),
        )
    )


def _read(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    accepted = document.get("accepted") if isinstance(document, dict) else None
    if not isinstance(accepted, dict):
        return {}
    return {key: value for key, value in accepted.items() if isinstance(value, dict)}


def _write(path: Path, accepted: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"accepted": dict(sorted(accepted.items()))}, indent=2, ensure_ascii=False) + "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def is_accepted(mechanism: Mechanism, path: Path | None = None) -> bool:
    """Whether the user said yes to this version of ``mechanism``."""
    answer = _read(path or consent_path()).get(mechanism.key, {})
    return answer.get("version") == mechanism.version


def accept(mechanism: Mechanism, path: Path | None = None) -> None:
    """Record the user's yes to the current version of ``mechanism``."""
    target = path or consent_path()
    accepted = _read(target)
    accepted[mechanism.key] = {
        "version": mechanism.version,
        "accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write(target, accepted)


def withdraw(mechanism: Mechanism, path: Path | None = None) -> None:
    """Turn ``mechanism`` off again."""
    target = path or consent_path()
    accepted = _read(target)
    if accepted.pop(mechanism.key, None) is not None:
        _write(target, accepted)


def require(mechanism: Mechanism, path: Path | None = None) -> None:
    """Raise :class:`LiveCaptureNotAccepted` unless the user said yes to ``mechanism``."""
    if not is_accepted(mechanism, path):
        raise LiveCaptureNotAccepted(mechanism)


def confirm_on_terminal(
    mechanism: Mechanism,
    path: Path | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> bool:
    """Ask on a terminal, the way the dialog does; record and return a yes.

    A command that is not attached to a terminal cannot be asked, so it is
    refused rather than taken as a yes.
    """
    import sys  # noqa: PLC0415 - streams resolved at call time, so tests can swap them

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if is_accepted(mechanism, path):
        return True
    print(f"{_(mechanism.title)}\n\n{statement(mechanism)}\n", file=stdout)
    if not stdin.isatty():
        print(_("Not turned on: run this command from a terminal to answer, or use Tools ▸ Live capture…"), file=stdout)
        return False
    print(_("Type yes to turn it on: "), end="", file=stdout, flush=True)
    if stdin.readline().strip().casefold() not in {"yes", _("yes").casefold()}:
        return False
    accept(mechanism, path)
    return True
