#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Carl Gherardi
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

import os
import sys


# Modify sys.path[0] to include the 'pyfpdb' directory
sys.path[0] = sys.path[0] + os.sep + "pyfpdb"
print (sys.path[0])
# Change the current working directory to the 'pyfpdb' subdir
os.chdir(sys.path[0])
    
if os.name == 'nt':
    # For Windows systems
    print(os.name)
    print(sys.argv[1:])
    # Construct the command to execute
    command = ['pythonw.exe', 'fpdb_prerun.py'] + sys.argv[1:]
    # Execute the command using os.system
    print(command)
    os.system(' '.join(command))
else:
    # For non-Windows systems
    os.execvpe('python', ['python', 'fpdb_prerun.py'] + sys.argv[1:], os.environ)