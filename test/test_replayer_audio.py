from pathlib import Path
from types import SimpleNamespace

from fpdb_3_legacy import replayer_audio


def test_pokerstars_cache_reuses_audio_and_invalidates_changed_source(tmp_path, monkeypatch):
    site_path = tmp_path / "PokerStars"
    audio_dir = site_path / "Gx" / "table-view" / "audio"
    audio_dir.mkdir(parents=True)
    source = audio_dir / "sfx_check.mp3"
    source.write_bytes(b"first source")
    config = SimpleNamespace(supported_sites={"PokerStars": SimpleNamespace(site_path=str(site_path))})
    monkeypatch.setattr(replayer_audio, "SOUNDS", {"check": "sfx_check.mp3"})
    monkeypatch.setattr(replayer_audio.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(replayer_audio.QStandardPaths, "writableLocation", lambda _location: str(tmp_path / "cache"))
    conversions = []

    def convert(command, **kwargs):
        conversions.append(command)
        assert kwargs["check"] and kwargs["timeout"] == 15
        Path(command[-1]).write_bytes(b"decoded PCM")

    monkeypatch.setattr(replayer_audio.subprocess, "run", convert)
    first = replayer_audio.prepare_sounds(config)
    assert first["check"].read_bytes() == b"decoded PCM"
    assert replayer_audio.prepare_sounds(config) == first
    assert len(conversions) == 1
    source.write_bytes(b"updated source with different size")
    second = replayer_audio.prepare_sounds(config)
    assert second["check"] != first["check"]
    assert len(conversions) == 2
    assert "volume=0.7" in conversions[-1]


def test_failed_conversion_does_not_publish_partial_audio(tmp_path, monkeypatch):
    import subprocess

    audio_dir = tmp_path / "Gx" / "table-view" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "sfx_check.mp3").write_bytes(b"source")
    config = SimpleNamespace(supported_sites={"PokerStars": SimpleNamespace(site_path=str(tmp_path))})
    cache = tmp_path / "cache"
    monkeypatch.setattr(replayer_audio, "SOUNDS", {"check": "sfx_check.mp3"})
    monkeypatch.setattr(replayer_audio.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(replayer_audio.QStandardPaths, "writableLocation", lambda _location: str(cache))

    def fail(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(replayer_audio.subprocess, "run", fail)
    audio = replayer_audio.ReplayerAudio(config=config)
    assert not audio.effects
    assert not list(cache.rglob("*.wav"))
