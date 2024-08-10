#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2010-2011 Steffen Schaumburg
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

#You may find http://boodebr.org/main/python/all-about-python-and-unicode helpful
import gettext
import platform
import subprocess
import locale
from pathlib import Path
from Configuration import GRAPHICS_PATH, CONFIG_PATH
import xml.etree.ElementTree as ET
from PyQt5.QtCore import QTranslator

def get_system_language():
    system = platform.system()
    if system == 'Windows':
        return locale.getdefaultlocale()[0]
    elif system == 'Linux':
        process = subprocess.Popen(['locale', '-b'],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        output, _ = process.communicate()
        return output.decode().strip()
    elif system == 'Darwin':
        process = subprocess.Popen(['defaults', 'read', '-g', 'AppleLanguages'],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        output, _ = process.communicate()
        output = output.decode().strip().replace('\n', '').replace('"', '')
        return output
    else:
        return None

def pass_through(to_translate):
    return to_translate

def set_translation(to_lang):
    try:
        trans = gettext.translation("fpdb", localedir="locale", languages=[to_lang])
        trans.install()
        translation = QTranslator()
        translation.load(to_lang, "locale")
    except IOError:
        translation = None
    return translation

def get_translation():
    try:
        return _
    except NameError:
        return pass_through

def init_translation():
    import Configuration
    conf = Configuration.Config()

    if conf.general['ui_language'] in ("system", ""):
        try:
            (lang, charset) = locale.getdefaultlocale()
        except Exception:
            lang = None
        if lang is None or lang[:2] == "en":
            return pass_through
        else:
            return set_translation(lang)
    elif conf.general['ui_language'] == "en":
        return pass_through
    else:
        return set_translation(conf.general['ui_language'])

def get_installed_translations():
    la_list = []
    la_co_list = []

    for (ident, la_co) in locale.windows_locale.items():
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
    except Exception:
        for code in la_list:
            la_dict[code] = code
        for code in la_co_list:
            la_co_dict[code] = code

    return la_dict, la_co_dict

def set_locale_translation():
    path = Path(GRAPHICS_PATH)
    transformed_path = path.parent
    locale_path = Path(transformed_path, "locale")
    path_string = str(locale_path)
    print(f"Locale path: {path_string}")

    gettext.bindtextdomain('fpdb', path_string)
    gettext.textdomain('fpdb')

    tree = ET.parse(f"{CONFIG_PATH}/HUD_config.xml")
    root = tree.getroot()
    general_element = root.find('general')
    ui_language = general_element.attrib.get('ui_language')
    print(f"UI Language: {ui_language}")

    try:
        fr_translation = gettext.translation('fpdb', path_string, languages=[ui_language])
        fr_translation.install()
    except FileNotFoundError:
        print(f"No translation file found for domain: 'fpdb' in {path_string} for language {ui_language}")

