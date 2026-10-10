#!/usr/bin/env python3
"""Install Linux launchers for a source checkout without hard-coded home paths."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import time
from pathlib import Path


def install_file(path: Path, content: str, *, executable: bool = False) -> None:
    """Keep a backup when replacing an existing, different launcher."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != content:
        backup = path.with_name(f"{path.name}.bak.{time.time_ns()}")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")
    path.write_text(content)
    if executable:
        path.chmod(0o755)
    print(f"Installed: {path}")


def desktop_quote(value: Path) -> str:
    escaped = str(value)
    for character in ("\\", '"', "`", "$"):
        escaped = escaped.replace(character, "\\" + character)
    # Desktop Entry string unescaping happens before Exec argument parsing.
    return '"' + escaped.replace("\\", "\\\\") + '"'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".fpdb" / "HUD_config.xml")
    parser.add_argument("--bin-dir", type=Path, default=Path.home() / ".local" / "bin")
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    parser.add_argument("--applications-dir", type=Path, default=data_home / "applications")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    python = root / ".venv" / "bin" / "python"
    launcher = root / ".venv" / "bin" / "fpdb_3_legacy"
    if not python.is_file() or not launcher.is_file():
        parser.error("Install FPDB in this checkout's .venv first; see docs/PERSONAL_SETUP.md")
    config = args.config.expanduser().absolute()
    bin_dir = args.bin_dir.expanduser().absolute()
    applications_dir = args.applications_dir.expanduser().absolute()
    install_file(
        bin_dir / "fpdb",
        "#!/usr/bin/env bash\n"
        "export FPDB_FORCE_X11=1\n"
        "export QT_QPA_PLATFORM=xcb\n"
        f'exec {shlex.quote(str(launcher))} -c {shlex.quote(str(config))} "$@"\n',
        executable=True,
    )
    # Resolve the history folder from the user's configuration at each invocation.
    import_code = (
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        "from fpdb_3_legacy import Configuration\n"
        "from fpdb_3_legacy.GuiBulkImport import main\n"
        f"config_path = {str(config)!r}\n"
        "config = Configuration.Config(file=config_path)\n"
        "site = config.supported_sites.get('PokerStars')\n"
        "history = getattr(site, 'HH_path', '')\n"
        "if not history or not Path(history).is_dir():\n"
        "    sys.exit('Configure an existing PokerStars HH_path in HUD_config.xml first.')\n"
        "sys.exit(main(['-x', '-C', config_path, '-c', 'PokerStars', '-f', history, *sys.argv[1:]]))\n"
    )
    install_file(
        bin_dir / "fpdb-import-pokerstars",
        f'#!/usr/bin/env bash\nexec {shlex.quote(str(python))} -c {shlex.quote(import_code)} "$@"\n',
        executable=True,
    )
    icon = str(root / "gfx" / "fpdb-icon.png").replace("\\", "\\\\")
    install_file(
        applications_dir / "fpdb.desktop",
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=FPDB 3\n"
        "Comment=Poker hand statistics and replay\n"
        f"Exec={desktop_quote(bin_dir / 'fpdb')}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Game;\n"
        "StartupNotify=true\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
