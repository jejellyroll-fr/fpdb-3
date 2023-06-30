#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-

# Created by Mika Bostrom, released into the public domain as far as legally possible.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
import glob
import os
import sys
from setuptools import setup, Command
from pathlib import Path

_pfx = '/usr/local'
for a in sys.argv:
    if a.startswith('--prefix='):
        _pfx = a.split('=')[1]

CONTENT = """# card_path.py
# Autogenerated file for FPDB

def deck_path():
    return '{}'
""".format(_pfx)

with open('pyfpdb/card_path.py', 'w+') as f:
    f.write(CONTENT)


class InstallTranslations(Command):
    description = 'Install translations'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        locales = self.__locales('pyfpdb/locale')
        data_files = []
        for loc_dir in locales:
            lang_dir = os.path.join('share', 'locale', loc_dir)
            loc_files = glob.glob(os.path.join('pyfpdb/locale', loc_dir, '*.mo'))
            data_files.append((lang_dir, loc_files))

        self.distribution.data_files.extend(data_files)

    def __locales(self, rootdir):
        paths = glob.glob(os.path.join(rootdir, '*'))
        return [os.path.basename(p) for p in paths]

commands = {
    'install_data': InstallTranslations
}

setup(
    name='fpdb',
    description='Free Poker Database',
    version='3',
    author='FPDB team',
    author_email='jejellyroll-fr@gmail.com',
    packages=['fpdb'],
    package_dir={'fpdb': 'pyfpdb'},
    data_files=[
        (str(Path('usr', 'share', 'pixmaps')), [
            'gfx/fpdb-icon.png',
            'gfx/fpdb-icon2.png',
            'gfx/fpdb-cards.png'
        ]),
        (str(Path('usr', 'share', 'applications')), ['files/fpdb.desktop']),
        (str(Path('usr', 'share', 'python-fpdb')), [
            'pyfpdb/logging.conf',
            'pyfpdb/HUD_config.xml.example'
        ]),
        (str(Path('usr', 'share', 'python-fpdb', 'cards', 'backs')), glob.glob('gfx/cards/backs/*')),
        (str(Path('usr', 'share', 'python-fpdb', 'cards', 'bordered')), glob.glob('gfx/cards/bordered/*')),
        (str(Path('usr', 'share', 'python-fpdb', 'cards', 'colour')), glob.glob('gfx/cards/colour/*')),
        (str(Path('usr', 'share', 'python-fpdb', 'cards', 'simple')), glob.glob('gfx/cards/simple/*')),
        (str(Path('usr', 'share', 'python-fpdb', 'cards', 'white')), glob.glob('gfx/cards/white/*')),
    ],
    cmdclass={'install_translations': InstallTranslations},
)