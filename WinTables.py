import ctypes
import re
from loggingFpdb import get_logger
from ctypes import wintypes
from PyQt5.QtGui import QWindow
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
import sys
import time

from TableWindow import Table_Window

app = QApplication(sys.argv)

# logging setup
log = get_logger("hud")

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
        # print("WindowInfo initialized with an empty dictionary.")


# Function for listing windows and retrieving titles
def win_enum_handler(hwnd, lParam):
    # print(f"Handler called for hwnd: {hwnd}")
    window_info = ctypes.cast(lParam, ctypes.py_object).value
    length = GetWindowTextLength(hwnd)
    # print(f"Window text length: {length}")
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        GetWindowText(hwnd, buff, length + 1)
        # print(f"Text retrieved for hwnd {hwnd}: {buff.value}")
        window_info.titles[hwnd] = buff.value
    return True


class Table(Table_Window):
    # In find_table_parameters of WinTables.py

    def find_table_parameters(self):
        """Find a poker client window with the given table name."""
        window_info = WindowInfoTemp()

        try:
            log.debug("before EnumWindows")
            EnumWindows(EnumWindowsProc(win_enum_handler), ctypes.py_object(window_info))
            log.debug(f"after EnumWindows found {len(window_info.titles)} windows")
        except Exception as e:
            log.error(f"Error during EnumWindows: {e}")

        time_limit = 10  # Limite de temps en secondes
        start_time = time.time()  # Enregistre l'heure de début

        for hwnd in window_info.titles:
            try:
                if time.time() - start_time > time_limit:
                    log.error(f"Time limit of {time_limit} seconds reached. Exiting loop.")
                    break

                title = window_info.titles[hwnd]
                if not title:
                    continue

                if not IsWindowVisible(hwnd):
                    continue
                if GetParent(hwnd) != 0:
                    continue

                # HasNoOwner = ctypes.windll.user32.GetWindow(hwnd, GW_OWNER) == 0
                # WindowStyle = GetWindowLong(hwnd, GWL_EXSTYLE)

                if title.split(" ", 1)[0] == "Winamax":
                    self.search_string = self.search_string.split(" ", 3)[0]

                if re.search(self.search_string, title, re.I):
                    if self.check_bad_words(title):
                        continue
                    self.number = hwnd
                    self.title = title
                    log.debug(f"Found table in hwnd {self.number} title {self.title}")
                    break

            except IOError as e:
                if "closed file" in str(e):
                    print(f"Warning: Logging to a closed file for hwnd {hwnd}. Skipping this log entry.")
                else:
                    log.error(f"IOError for hwnd {hwnd}: {e}")
            except Exception as e:
                log.error(f"Unexpected error for hwnd {hwnd}: {e}")

        if self.number is None:
            log.error(f"Window {self.search_string} not found.")

    # In get_geometry of WinTables.py
    def get_geometry(self):
        """Get the window geometry."""
        # print(f"Attempting to retrieve geometry for hwnd: {self.number}")
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

                    # print(f"Position: ({x}, {y}), Dimensions: {width}x{height}")
                    # print(f"Border width: {self.b_width}, Title bar height: {self.tb_height}")

                    return {
                        "x": int(x) + self.b_width,
                        "y": int(y) + self.tb_height + self.b_width,
                        "height": int(height) - 2 * self.b_width - self.tb_height,
                        "width": int(width) - 2 * self.b_width,
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
            # print(f"Moving and resizing window {self.number}")
            MoveWindow(self.number, x, y, width, height, True)
            # print(f"Window moved to ({x}, {y}) with dimensions {width}x{height}")
        else:
            log.info("No window to move.")

    def topify(self, window):
        """Make the specified Qt window 'always on top' under Windows."""
        if self.gdkhandle is None:
            self.gdkhandle = QWindow.fromWinId(int(self.number))

        qwindow = window.windowHandle()
        qwindow.setTransientParent(self.gdkhandle)
        qwindow.setFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint)

    def check_bad_words(self, title):
        """Check if the title contains any bad words."""
        bad_words = ["History for table:", "HUD:", "Chat:", "FPDBHUD", "Lobby"]
        return any(bad_word in title.lower() for bad_word in bad_words)
