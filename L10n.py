"""L10n module for FPDB localization and internationalization.

Copyright 2010-2011 Steffen Schaumburg
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
In the "official" distribution you can find the license in agpl-3.0.txt.
"""

# You may find http://boodebr.org/main/python/all-about-python-and-unicode helpful
import gettext
import locale
import platform
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QTranslator

from Configuration import CONFIG_PATH, GRAPHICS_PATH
from loggingFpdb import get_logger

log = get_logger("translation")


def get_system_language() -> str | None:
    """Get the system default language."""
    system = platform.system()
    if system == "Windows":
        return locale.getdefaultlocale()[0]
    if system == "Linux":
        locale_cmd = shutil.which("locale")
        if locale_cmd:
            process = subprocess.Popen(  # noqa: S603
                [locale_cmd, "-b"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            return None
        output, _ = process.communicate()
        return output.decode().strip()
    if system == "Darwin":
        defaults_cmd = shutil.which("defaults")
        if defaults_cmd:
            process = subprocess.Popen(  # noqa: S603
                [defaults_cmd, "read", "-g", "AppleLanguages"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            return None
        output, _ = process.communicate()
        return output.decode().strip().replace("\n", "").replace('"', "")
    return None


def pass_through(to_translate: str) -> str:
    """Pass-through function for translation (no-op)."""
    return to_translate


def set_translation(to_lang: str) -> None:
    """Set the translation language."""
    try:
        trans = gettext.translation("fpdb", localedir="locale", languages=[to_lang])
        trans.install()
        translation = QTranslator()
        translation.load(to_lang, "locale")
    except OSError:
        translation = None
    return translation


def get_translation() -> Any:
    """Get the current translation function."""
    try:
        return _
    except NameError:
        return pass_through


def init_translation() -> None:
    """Initialize translation system."""
    import Configuration

    conf = Configuration.Config()

    if conf.general["ui_language"] in ("system", ""):
        try:
            (lang, charset) = locale.getdefaultlocale()
        except (ValueError, TypeError, OSError):
            lang = None
        if lang is None or lang[:2] == "en":
            return pass_through
        return set_translation(lang)
    if conf.general["ui_language"] == "en":
        return pass_through
    return set_translation(conf.general["ui_language"])


def get_installed_translations() -> dict[str, str]:
    """Get installed translations mapping."""
    la_list = []
    la_co_list = []

    for la_co in locale.windows_locale.values():
        if gettext.find("fpdb", localedir="locale", languages=[la_co]):
            if "_" in la_co:
                la, co = la_co.split("_", 1)
                la_list.append(la)
            else:
                la_list.append(la_co)
            la_co_list.append(la_co)

    la_set = set(la_list)
    la_list = list(la_set)

    la_dict = {}
    la_co_dict = {}
    try:
        from icu import Locale

        for code in la_list:
            la_dict[code] = Locale.getDisplayName(Locale(code))
        for code in la_co_list:
            la_co_dict[code] = Locale.getDisplayName(Locale(code))
    except (ImportError, AttributeError):
        la_dict = {code: code for code in la_list}
        la_co_dict = {code: code for code in la_co_list}

    return la_dict, la_co_dict


def set_locale_translation() -> None:
    """Set up locale translation system."""
    path = Path(GRAPHICS_PATH)
    transformed_path = path.parent
    locale_path = Path(transformed_path, "locale")
    path_string = str(locale_path)
    log.info("Locale path: %s", path_string)

    gettext.bindtextdomain("fpdb", path_string)
    gettext.textdomain("fpdb")

    tree = ET.parse(f"{CONFIG_PATH}/HUD_config.xml")  # noqa: S314
    root = tree.getroot()
    general_element = root.find("general")
    ui_language = general_element.attrib.get("ui_language")
    log.info("UI Language: %s", ui_language)

    try:
        fr_translation = gettext.translation(
            "fpdb",
            path_string,
            languages=[ui_language],
        )
        fr_translation.install()
    except FileNotFoundError:
        log.exception(
            "No translation file found for domain 'fpdb' in %s for language %s",
            path_string,
            ui_language,
        )
