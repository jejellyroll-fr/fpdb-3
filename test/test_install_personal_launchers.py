import json
import subprocess
import sys

from tools import install_personal_launchers as installer


def test_launcher_preserves_paths_and_arguments_with_shell_characters(tmp_path, monkeypatch):
    root = tmp_path / "FPDB with spaces $HOME"
    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    launcher = venv_bin / "fpdb_3_legacy"
    launcher.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    launcher.chmod(0o755)
    monkeypatch.setattr(installer, "__file__", str(root / "tools" / "install_personal_launchers.py"))
    bin_dir = tmp_path / "bin with spaces"
    applications = tmp_path / "apps"
    config = tmp_path / "config with spaces $HOME.xml"
    assert (
        installer.main(
            [
                "--bin-dir",
                str(bin_dir),
                "--applications-dir",
                str(applications),
                "--config",
                str(config),
            ]
        )
        == 0
    )
    result = subprocess.run(
        [str(bin_dir / "fpdb"), "--file", "a hand's history.txt"], check=True, capture_output=True, text=True
    )
    assert json.loads(result.stdout) == ["-c", str(config), "--file", "a hand's history.txt"]
    subprocess.run(["bash", "-n", str(bin_dir / "fpdb-import-pokerstars")], check=True)
    assert 'Exec="' in (applications / "fpdb.desktop").read_text()


def test_installation_backs_up_different_files_but_is_idempotent(tmp_path):
    launcher = tmp_path / "fpdb"
    launcher.write_text("previous launcher")
    installer.install_file(launcher, "new launcher", executable=True)
    backups = list(tmp_path.glob("fpdb.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "previous launcher"
    installer.install_file(launcher, "new launcher", executable=True)
    assert list(tmp_path.glob("fpdb.bak.*")) == backups
    assert launcher.stat().st_mode & 0o111
