import win32gui


def window_enumeration_handler(hwnd, window_list) -> None:
    window_list.append((hwnd, win32gui.GetWindowText(hwnd)))


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="Windows Table Detection utility")
    parser.add_argument("--list-windows", action="store_true", help="List all windows with details")
    parser.add_argument("--show-poker-windows", action="store_true", help="Show only poker-related windows")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        # Default behavior - simple detection
        simple_window_detection()
        return 0

    if args.list_windows:
        print("=== All Windows ===")
        list_windows_detailed()
        return 0

    if args.show_poker_windows:
        print("=== Poker Windows ===")
        show_poker_windows()
        return 0

    return 0


def simple_window_detection():
    """Simple window detection (original behavior)."""
    window_list = []
    win32gui.EnumWindows(window_enumeration_handler, window_list)
    for _window in window_list:
        pass


def list_windows_detailed():
    """List all windows with detailed information."""
    try:
        window_list = []
        win32gui.EnumWindows(window_enumeration_handler, window_list)

        print(f"Found {len(window_list)} windows:")

        for i, (hwnd, window_text) in enumerate(window_list, 1):
            if window_text.strip():  # Only show windows with text
                # Get window position
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    x, y, width, height = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]

                    # Get class name
                    class_name = win32gui.GetClassName(hwnd)

                    print(f"{i:3}. {window_text}")
                    print(f"     Class: {class_name}")
                    print(f"     Position: ({x}, {y}) Size: {width}x{height}")

                except Exception as e:
                    print(f"{i:3}. {window_text} (Error getting details: {e})")

    except Exception as e:
        print(f"Error listing windows: {e}")


def show_poker_windows():
    """Show only poker-related windows using supported room names."""
    # Use actual supported poker room names from FPDB
    poker_rooms = [
        "pokerstars",
        "winamax",
        "ipoker",
        "acr",
        "seals",
        "partypoker",
        "partygaming",
        "merge",
        "fulltilt",
        "pacificpoker",
        "cake",
        "cpn",
        "everygame",
        "bovada",
        "ggpoker",
        "unibet",
        "kingsclub",
        "betonline",
        "americas",
        "ignition",
    ]

    try:
        window_list = []
        win32gui.EnumWindows(window_enumeration_handler, window_list)

        poker_windows = []

        for hwnd, window_text in window_list:
            if window_text.strip():
                window_text_lower = window_text.lower()

                if any(room in window_text_lower for room in poker_rooms):
                    poker_windows.append((hwnd, window_text))

        if poker_windows:
            print(f"Found {len(poker_windows)} poker windows:")
            for i, (hwnd, window_text) in enumerate(poker_windows, 1):
                print(f"{i}. {window_text}")
        else:
            print("No poker windows detected")

    except Exception as e:
        print(f"Error detecting poker windows: {e}")


if __name__ == "__main__":
    import sys

    sys.exit(main())
