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
import locale
from PyQt5.QtCore import QTranslator

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
        except:
            lang = None
        if lang == None or lang[:2] == "en":
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
    except:
        for code in la_list:
            la_dict[code] = code
        for code in la_co_list:
            la_co_dict[code] = code

    return la_dict, la_co_dict
