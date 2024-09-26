import win32gui

def window_enumeration_handler(hwnd, window_list):
    window_list.append((hwnd, win32gui.GetWindowText(hwnd)))

if __name__ == '__main__':
    window_list = []
    win32gui.EnumWindows(window_enumeration_handler, window_list)
    for window in window_list:
        print(window[1])