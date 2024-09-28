import ctypes
import re
import logging
from ctypes import wintypes
from PyQt5.QtGui import QWindow
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
import sys
import time

from TableWindow import Table_Window

app = QApplication(sys.argv)

# logging setup
log = logging.getLogger("hud")

# Definition of Windows API constants
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SM_CXSIZEFRAME = 32
SM_CYCAPTION = 4

# Windows functions via ctypes
EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetParent = ctypes.windll.user32.GetParent
GetWindowRect = ctypes.windll.user32.GetWindowRect
GetWindowLong = ctypes.windll.user32.GetWindowLongW
GetSystemMetrics = ctypes.windll.user32.GetSystemMetrics
IsWindow = ctypes.windll.user32.IsWindow
MoveWindow = ctypes.windll.user32.MoveWindow

# Global variables
b_width = 3
tb_height = 29

# Class for temporarily storing securities
class WindowInfoTemp:
    def __init__(self):
        self.titles = {}
        #print("WindowInfo initialized with an empty dictionary.")

# Function for listing windows and retrieving titles
def win_enum_handler(hwnd, lParam):
    #print(f"Handler called for hwnd: {hwnd}")
    window_info = ctypes.cast(lParam, ctypes.py_object).value
    length = GetWindowTextLength(hwnd)
    #print(f"Window text length: {length}")
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        GetWindowText(hwnd, buff, length + 1)
        #print(f"Text retrieved for hwnd {hwnd}: {buff.value}")
        window_info.titles[hwnd] = buff.value
    return True


class Table(Table_Window):
    # In find_table_parameters of WinTables.py
    def find_table_parameters(self):
        """Trouver une fenêtre de poker client correspondant au nom de table donné."""
        
        # Log du début de la fonction
        start_time = time.time()
        log.debug("Début de find_table_parameters")

        window_info = WindowInfoTemp()
        
        try:
            log.debug("Avant EnumWindows")
            EnumWindows(EnumWindowsProc(win_enum_handler), ctypes.py_object(window_info))
            log.debug(f"Après EnumWindows, {len(window_info.titles)} fenêtres trouvées")
        except Exception as e:
            log.error(f"Erreur pendant EnumWindows : {e}")
        
        # Limite de temps pour la recherche
        time_limit = 10  # secondes
        start_search_time = time.time()

        # Première passe : filtrer avec self.site
        found = False
        for hwnd in window_info.titles:
            if time.time() - start_search_time > time_limit:
                log.error(f"Limite de temps de {time_limit} secondes atteinte. Sortie de la boucle.")
                break
            
            title = window_info.titles[hwnd]
            if not title:
                continue

            if not IsWindowVisible(hwnd):
                continue
            if GetParent(hwnd) != 0:
                continue

            # Appliquer le filtre self.site si défini
            if self.site and self.site.lower() not in title.lower():
                continue

            if re.search(self.search_string, title, re.I):
                if self.check_bad_words(title):
                    continue
                self.number = hwnd
                self.title = title
                found = True
                break
        
        # Si aucune fenêtre trouvée avec le filtre, rechercher dans toutes les fenêtres
        if not found:
            log.debug("Pas de fenêtre trouvée avec le filtre site, recherche dans toutes les fenêtres")
            for hwnd in window_info.titles:
                if time.time() - start_search_time > time_limit:
                    log.error(f"Limite de temps de {time_limit} secondes atteinte. Sortie de la boucle.")
                    break

                title = window_info.titles[hwnd]
                if not title:
                    continue

                if not IsWindowVisible(hwnd):
                    continue
                if GetParent(hwnd) != 0:
                    continue

                if re.search(self.search_string, title, re.I):
                    if self.check_bad_words(title):
                        continue
                    self.number = hwnd
                    self.title = title
                    break
        
        if self.number is None:
            log.error(f"Fenêtre {self.search_string} non trouvée.")
        
        # Log de fin de fonction avec le temps écoulé
        end_time = time.time()
        log.debug(f"Fin de find_table_parameters. Temps écoulé : {end_time - start_time:.2f} secondes.")



    # In get_geometry of WinTables.py
    def get_geometry(self):
        """Get the window geometry."""
        #print(f"Attempting to retrieve geometry for hwnd: {self.number}")
        try:
            rect = wintypes.RECT()
            if IsWindow(self.number):
                result = GetWindowRect(self.number, ctypes.byref(rect))
                if result != 0:
                    x, y = rect.left, rect.top
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top

                    self.b_width = GetSystemMetrics(SM_CXSIZEFRAME)
                    self.tb_height = GetSystemMetrics(SM_CYCAPTION)

                    #print(f"Position: ({x}, {y}), Dimensions: {width}x{height}")
                    #print(f"Border width: {self.b_width}, Title bar height: {self.tb_height}")

                    return {
                        'x': int(x) + self.b_width,
                        'y': int(y) + self.tb_height + self.b_width,
                        'height': int(height) - 2 * self.b_width - self.tb_height,
                        'width': int(width) - 2 * self.b_width
                    }
                else:
                    log.error(f"Failed to retrieve GetWindowRect for hwnd: {self.number}")
                    return None
            else:
                log.error(f"The window {self.number} is not valid.")
                return None
        except Exception as e:
            log.error(f"Error retrieving geometry: {e}")
            return None

    def get_window_title(self):
        log.debug(f"title for {self.number}")
        length = GetWindowTextLength(self.number)
        buff = ctypes.create_unicode_buffer(length + 1)
        GetWindowText(self.number, buff, length + 1)
        log.debug(f"title {buff.value}")
        return buff.value

    def move_and_resize_window(self, x, y, width, height):
        """Move and resize the specified window."""
        if self.number:
            #print(f"Moving and resizing window {self.number}")
            MoveWindow(self.number, x, y, width, height, True)
            #print(f"Window moved to ({x}, {y}) with dimensions {width}x{height}")
        else:
            log.info("No window to move.")

    def topify(self, window):
        """Make the specified Qt window 'always on top' under Windows."""
        if self.gdkhandle is None:
            self.gdkhandle = QWindow.fromWinId(int(self.number))

        qwindow = (window.windowHandle())
        qwindow.setTransientParent(self.gdkhandle)
        qwindow.setFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint)

