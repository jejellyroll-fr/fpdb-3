"""L10n module for FPDB localization and internationalization.
from __future__ import annotations
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
import builtins
import gettext
import locale
import platform
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException
from PySide6.QtCore import QTranslator

from fpdb_3_legacy.Configuration import GRAPHICS_PATH, get_config
from fpdb_3_legacy.loggingFpdb import get_logger

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


def set_translation(to_lang: str) -> QTranslator | None:
    """Set the translation language."""
    try:
        trans = gettext.translation("fpdb", localedir="locale", languages=[to_lang])
        trans.install()
        translation = QTranslator()
        translation.load(to_lang, "locale")
    except OSError:
        translation = None
    return translation


def get_translation() -> Callable[[str], str]:
    """Get the current translation function."""
    translation = getattr(builtins, "_", None)
    return translation if callable(translation) else pass_through


def init_translation() -> QTranslator | Callable[[str], str] | None:
    """Initialize translation system."""
    import fpdb_3_legacy.Configuration as Configuration

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


def get_installed_translations() -> tuple[dict[str, str], dict[str, str]]:
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


def set_locale_translation(config_path: str | None = None) -> None:
    """Set up locale translation system.

    Args:
        config_path: Optional path to the HUD config file. When omitted, or when
            the given path does not exist, the file is resolved via
            ``Configuration.get_config()``, which also bootstraps it from the
            bundled ``.example`` on first run. A missing or unreadable config is
            logged and translation setup is skipped, instead of crashing
            startup (see GitHub issue #139).
    """
    path = Path(GRAPHICS_PATH)
    transformed_path = path.parent
    locale_path = Path(transformed_path, "locale")
    path_string = str(locale_path)
    log.info("Locale path: %s", path_string)

    # The .mo catalogs are build artifacts (git-ignored); compile any that are
    # missing or stale from the shipped .po files so translations load at runtime.
    try:
        from fpdb_3_legacy.i18n_compile import ensure_compiled

        recompiled = ensure_compiled(locale_path)
        if recompiled:
            log.info("Compiled translation catalogs: %s", ", ".join(recompiled))
    except Exception as exc:  # noqa: BLE001 - never let i18n setup block startup
        log.warning("Could not compile translation catalogs: %s", exc)

    gettext.bindtextdomain("fpdb", path_string)
    gettext.textdomain("fpdb")

    # Resolve the config path: prefer the caller-supplied one, otherwise let
    # get_config() locate it (and copy the .example into place on first run).
    if not config_path or not Path(config_path).exists():
        try:
            config_path, _, _ = get_config("HUD_config.xml")
        except SystemExit:
            log.warning("Could not resolve HUD_config.xml; skipping translation setup.")
            return

    try:
        tree = ET.parse(config_path)
    except (FileNotFoundError, ET.ParseError, DefusedXmlException):
        log.warning(
            "HUD config not found or invalid at %s; skipping translation setup.",
            config_path,
        )
        return

    root = tree.getroot()
    general_element = root.find("general")
    ui_language = general_element.attrib.get("ui_language") if general_element is not None else None
    log.info("UI Language: %s", ui_language)

    from fpdb_3_legacy.localized_formats import set_format_locale

    resolved_locale = set_format_locale(ui_language)
    log.info("Display format locale: %s", resolved_locale)

    if not ui_language or ui_language == "en" or ui_language.startswith("en_"):
        gettext.NullTranslations().install()
        log.info("Using source strings for language: %s", ui_language or "en")
    else:
        try:
            fr_translation = gettext.translation(
                "fpdb",
                path_string,
                languages=[ui_language] if ui_language != "system" else None,
            )
            fr_translation.install()
        except (FileNotFoundError, OSError):
            gettext.NullTranslations().install()
            log.warning(
                "No translation file found for domain 'fpdb' in %s for language %s; using source strings.",
                path_string,
                ui_language,
            )
