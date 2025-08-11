# FPDB-3 - Free Poker Database

[![stars](https://custom-icon-badges.demolab.com/github/stars/jejellyroll-fr/fpdb-3?logo=star)](https://github.com/jejellyroll-fr/fpdb-3/stargazers "stars")
[![issues](https://custom-icon-badges.demolab.com/github/issues-raw/jejellyroll-fr/fpdb-3?logo=issue)](https://github.com/jejellyroll-fr/fpdb-3/issues "issues")
[![license](https://custom-icon-badges.demolab.com/github/license/jejellyroll-fr/fpdb-3?logo=law&logoColor=white)](https://github.com/jejellyroll-fr/fpdb-3/blob/main/LICENSE?rgh-link-date=2021-08-09T18%3A10%3A26Z "license MIT")
![example workflow](https://github.com/jejellyroll-fr/fpdb-3/actions/workflows/fpdb-3.yml/badge.svg)

FPDB-3 is a comprehensive poker tracking and analysis suite that provides:
- **HUD (Heads-Up Display)** for real-time statistics overlay on poker tables
- **Hand History Import and Analysis** from multiple poker sites
- **Statistics and Reporting** with detailed poker metrics
- **Web Interface** for online access to your poker data
- **Database Management** supporting SQLite, MySQL, and PostgreSQL

Built on Python 3.10+ with modern tooling and actively maintained.

## 🎯 Quick Start

### System Requirements
- Python 3.10 or higher
- Operating System: Linux, Windows, or macOS
- For HUD functionality: X11 (Linux), native window support (Windows/macOS)

### Installation

#### Using UV
```bash
# Install UV package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/jejellyroll-fr/fpdb-3.git
cd fpdb-3
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (choose your platform)
uv pip install .[linux]      # Linux
uv pip install .[windows]    # Windows  
uv pip install .[macos]      # macOS

# Add PostgreSQL support (optional)
uv pip install .[postgresql]
```


### Running FPDB-3

#### Main Application (GUI)
```bash
uv run python fpdb.pyw
```


#### Web Interface
```bash
uv run python web/start_fpdb_web.py
# Access at http://localhost:8000
```

## 🎮 Supported Poker Sites

FPDB-3 supports hand history import from:
- PokerStars
- Winamax
- GGPoker
- Bovada/Ignition
- iPoker Network
- And 8+ additional sites

See our [Compatibility Guide](https://github.com/jejellyroll-fr/fpdb-3/wiki/Compatibility-online-Rooms) for the complete list.

## 🖥️ Platform-Specific Setup

### Linux
- **X11**: Works out of the box
- **Wayland**: Use the included wrapper script:
  ```bash
  ./fpdb-xwayland.sh
  # or set: export FPDB_FORCE_X11=1
  ```

### Windows
- Requires pywin32 (included in installation)
- Run as administrator for full HUD functionality

### macOS
- Requires pyobjc (included in installation)
- May need accessibility permissions for HUD overlay

## 📚 Documentation and Support

- **Wiki**: [Complete user guide](https://github.com/jejellyroll-fr/fpdb-3/wiki)
- **HUD Setup**: [How to configure the HUD](https://github.com/jejellyroll-fr/fpdb-3/wiki/How-to-Set-Up-and-Use-the-HUD-with-fpdb%E2%80%903-by-editing-HUD_config.xml)
- **Linux Guide**: [Distribution-specific setup](https://github.com/jejellyroll-fr/fpdb-3/wiki/FPDB%E2%80%903-and-Different-Linux-Distributions,-X11-or-Wayland-Support-and-different-desktop-environment-(WIP))
- **API Documentation**: [Sphinx docs](https://jejellyroll-fr.github.io/fpdb-3/)

## 🐛 Bug Reports and Support

- **GitHub Issues**: [Report bugs](https://github.com/jejellyroll-fr/fpdb-3/issues)
- **Discussions**: [Community support](https://github.com/jejellyroll-fr/fpdb-3/discussions)
- **Hand History Issues**: Email problematic files to jejellyroll.fr@gmail.com

When reporting bugs, please include:
- Your operating system and version
- Python version
- Steps to reproduce the issue
- Any error messages or logs

## 🤝 Contributing

Want to contribute? Check out our [Contributing Guide](CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing procedures
- Pull request process

## 📈 Development Status

Follow development progress on our [Project Board](https://github.com/users/jejellyroll-fr/projects/2).

## 📄 License

AGPL v3 License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

This project builds upon the work of:
- Original FPDB team
- MegaphoneJon's Python 3 adaptation
- ChazDazzle's updates
- All contributors to the poker tracking community

**Free Software, Hell Yeah!**
