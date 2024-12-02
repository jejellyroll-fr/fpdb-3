# FPDB 3

[![stars](https://custom-icon-badges.demolab.com/github/stars/jejellyroll-fr/fpdb-3?logo=star)](https://github.com/jejellyroll-fr/fpdb-3/stargazers "stars")
[![issues](https://custom-icon-badges.demolab.com/github/issues-raw/jejellyroll-fr/fpdb-3?logo=issue)](https://github.com/jejellyroll-fr/fpdb-3/issues "issues")
[![license](https://custom-icon-badges.demolab.com/github/license/jejellyroll-fr/fpdb-3?logo=law&logoColor=white)](https://github.com/jejellyroll-fr/fpdb-3/blob/main/LICENSE?rgh-link-date=2021-08-09T18%3A10%3A26Z "license MIT")
![example workflow](https://github.com/jejellyroll-fr/fpdb-3/actions/workflows/fpdb-3.yml/badge.svg)

starting new project base on fpdb python3 adaptation of MegaphoneJon and update from ChazDazzle
(tx to all previous contribs)

Feel free to clone it, and to participate to this development.

I'm not an expert python developer, this project, as a poker player, is for me to develop my skills in this language during my free time.

## Updating to python 3.11.9

FPDB is a poker tools - HUD - Replayer
Download your build directly on this repo: <https://github.com/jejellyroll-fr/fpdb-3-builder>

## wiki

- [wiki Homepage](https://github.com/jejellyroll-fr/fpdb-3/wiki)
- [Compatibility only rooms](https://github.com/jejellyroll-fr/fpdb-3/wiki/Compatibility-online-Rooms)
- [FPDB‐3 and Different Linux Distributions](https://github.com/jejellyroll-fr/fpdb-3/wiki/FPDB%E2%80%903-and-Different-Linux-Distributions,-X11-or-Wayland-Support-and-different-desktop-environment-(WIP))
- [How to Set Up and Use the HUD](https://github.com/jejellyroll-fr/fpdb-3/wiki/How-to-Set-Up-and-Use-the-HUD-with-fpdb%E2%80%903-by-editing-HUD_config.xml)
- [How to contribute](https://github.com/jejellyroll-fr/fpdb-3/wiki/How-to-contribute:-a-Gitflow%E2%80%90inspired-struture)

## Board

- To follow my devs: <https://github.com/users/jejellyroll-fr/projects/2>

## Community

- If have questions or want to discuss about the project: <https://github.com/jejellyroll-fr/fpdb-3/discussions>

## Requirement for dev

```sh
mkdir ~/.fpdb
cp HUD_config.xml ~/.fpdb
```

Install the dependencies and devDependencies

### Using anaconda

You can use anaconda with Python 3.11: <https://www.anaconda.com/download>

### Using UV package manager

Install [UV](https://docs.astral.sh/uv)

```sh
uv venv
source .venv/bin/activate
```

Think to install your needed libs ... in my case linux with postgresql:

```sh
uv pip install .[linux][postgresql]
uv run ./fpdb.pyw`
```

This will create a virtual env (in .venv dir), install all dependencies and run the program.

### Using pip

```sh
pip install -r requirements.txt
```

or

```sh
pip install -r requirements_win.txt
```

or

```sh
pip install -r requirements_macos.txt
```

or

```sh
pip install -r requirements_fpdb_web.txt
```

## Dev test

FPDB3

```Python
python fpdb.pyw
```

FPDB3 web

```Python
python start_fpdb_web.py 
```

## Bugs report and new hand support

you can report the bugs in the appropriate section
Specify your Os
you can send your HH in error by email <jejellyroll.fr@gmail.com>

**Free Software, Hell Yeah!**
