"""Play poker foley from the user's installed PokerStars client."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QStandardPaths, QUrl

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("replayer_audio")
# Read these from the local client; proprietary audio is not bundled in FPDB.
SOUNDS = {
    "check": "sfx_check.mp3",
    "fold": "sfx_fold.mp3",
    "chips": "sfx_bet.mp3",
    "raise": "sfx_raise.mp3",
    "deal": "sfx_card_dealt.mp3",
    "allin": "chip_stack_down.mp3",
    "collect": "sfx_chips_from_pot.mp3",
}
# The client's card and pot samples are much quieter than its chip/check samples.
# Balance them for standalone replay, without changing their timbre or speed.
SOURCE_GAIN = {"check": 0.7, "fold": 4, "chips": 1, "raise": 1, "deal": 1.6, "allin": 1.25, "collect": 4}


def prepare_sounds(config) -> dict[str, Path]:
    """Cache PCM copies for QSoundEffect, preserving the original stereo mix."""
    site = getattr(config, "supported_sites", {}).get("PokerStars")
    site_path = getattr(site, "site_path", "")
    if not site_path:
        log.warning("Set the PokerStars installation path to enable replayer sounds.")
        return {}
    source_dir = Path(site_path) / "Gx" / "table-view" / "audio"
    cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation))
    cache = cache / "fpdb" / "replayer-pokerstars-v2"
    cache.mkdir(parents=True, exist_ok=True)
    decoder = shutil.which("ffmpeg")
    paths = {}
    for name, filename in SOUNDS.items():
        source = source_dir / filename
        if not source.is_file():
            log.warning("PokerStars replayer audio missing: %s", source)
            continue
        stat = source.stat()
        fingerprint = hashlib.sha256(f"{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:16]
        output = cache / f"{name}-{fingerprint}.wav"
        if not output.is_file():
            if not decoder:
                log.warning("ffmpeg is needed to prepare PokerStars replayer sounds.")
                continue
            with tempfile.TemporaryDirectory(dir=cache) as temporary_dir:
                temporary = Path(temporary_dir) / "sound.wav"
                subprocess.run(
                    [
                        decoder,
                        "-nostdin",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(source),
                        "-map_metadata",
                        "-1",
                        "-af",
                        f"volume={SOURCE_GAIN[name]}",
                        "-c:a",
                        "pcm_s16le",
                        str(temporary),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                # Publish only completed conversions, including with two replay windows open.
                temporary.replace(output)
        paths[name] = output
    return paths


def transition_sound(previous, current) -> str | None:
    """Classify only the newly visible event, not stale actions from earlier frames."""
    if getattr(current, "ended", False) and not getattr(previous, "ended", False):
        return "collect"
    if getattr(current, "phase", None):
        return "collect" if current.phase == "result" else "deal"
    if current.street != previous.street:
        return "deal"
    for player in current.players.values():
        if not player.justacted:
            continue
        action = (player.action or "").lower()
        if action == "checks":
            return "check"
        if action == "folds" or action.startswith("discards"):
            return "fold"
        if action in {"bets", "raises", "calls", "big blind", "small blind", "ante", "both", "secondsb", "bringin"}:
            if player.stack <= 0:
                return "allin"
            return "raise" if action == "raises" else "chips"
    return None


class ReplayerAudio(QObject):
    """Own asynchronous effects and persist the player's sound preferences."""

    def __init__(self, parent=None, *, config=None):
        super().__init__(parent)
        self.settings = QSettings("fpdb", "replayer")
        self.enabled = self.settings.value("sound/enabled", True, type=bool)
        self.volume = max(0, min(100, self.settings.value("sound/volume", 35, type=int)))
        self.effects = {}
        try:
            from PySide6.QtMultimedia import QSoundEffect

            for name, path in prepare_sounds(config).items():
                effect = QSoundEffect(self)
                effect.setVolume(self.volume / 100)
                effect.setSource(QUrl.fromLocalFile(str(path)))
                self.effects[name] = effect
        except (ImportError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            log.warning("Replayer sound unavailable: %s", exc)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.settings.setValue("sound/enabled", enabled)
        if not enabled:
            self.stop()

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, volume))
        self.settings.setValue("sound/volume", self.volume)
        for effect in self.effects.values():
            effect.setVolume(self.volume / 100)

    def stop(self) -> None:
        for effect in self.effects.values():
            effect.stop()

    def play(self, name: str | None) -> None:
        effect = self.effects.get(name)
        if self.enabled and self.volume and effect is not None and effect.isLoaded():
            # Let different actions finish their natural tails instead of cutting
            # off the previous sample whenever the next action appears.
            effect.stop()
            effect.play()
