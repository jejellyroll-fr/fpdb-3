import sys

try:
    import Quartz
except ImportError:
    if sys.platform == "darwin":
        raise ImportError("Quartz module required on macOS. Install with: pip install pyobjc-framework-Quartz")
    else:
        # On non-macOS platforms, provide dummy implementation or skip
        Quartz = None


def get_window_info() -> None:
    if Quartz is None:
        print("Quartz not available on this platform")
        return
    # Obtenir toutes les fenêtres sur l'écran
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
    )

    # Parcourir toutes les fenêtres et extraire des informations
    for window in window_list:
        window.get("kCGWindowOwnerName", "Inconnu")
        window.get("kCGWindowName", "Sans titre")
        window_bounds = window.get("kCGWindowBounds", {})

        window_bounds.get("X", 0)
        window_bounds.get("Y", 0)
        window_bounds.get("Width", 0)
        window_bounds.get("Height", 0)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="OSX Window Detection utility")
    parser.add_argument("--list-windows", action="store_true", help="List all windows on screen with details")
    parser.add_argument("--show-poker-windows", action="store_true", help="Show only poker-related windows")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        # Default behavior - simple detection
        get_window_info()
        return 0

    if args.list_windows:
        print("=== All Windows on Screen ===")
        list_windows_detailed()
        return 0

    if args.show_poker_windows:
        print("=== Poker Windows ===")
        show_poker_windows()
        return 0

    return 0


def list_windows_detailed():
    """List all windows with detailed information."""
    try:
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
        )

        print(f"Found {len(window_list)} windows:")

        for i, window in enumerate(window_list, 1):
            owner = window.get("kCGWindowOwnerName", "Unknown")
            name = window.get("kCGWindowName", "Untitled")
            window_bounds = window.get("kCGWindowBounds", {})

            x = window_bounds.get("X", 0)
            y = window_bounds.get("Y", 0)
            width = window_bounds.get("Width", 0)
            height = window_bounds.get("Height", 0)

            print(f"{i:3}. {owner} - {name}")
            print(f"     Position: ({x}, {y}) Size: {width}x{height}")

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
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
        )

        poker_windows = []

        for window in window_list:
            owner = window.get("kCGWindowOwnerName", "").lower()
            name = window.get("kCGWindowName", "").lower()

            if any(room in owner or room in name for room in poker_rooms):
                poker_windows.append(window)

        if poker_windows:
            print(f"Found {len(poker_windows)} poker windows:")
            for i, window in enumerate(poker_windows, 1):
                owner = window.get("kCGWindowOwnerName", "Unknown")
                name = window.get("kCGWindowName", "Untitled")
                print(f"{i}. {owner} - {name}")
        else:
            print("No poker windows detected")

    except Exception as e:
        print(f"Error detecting poker windows: {e}")


if __name__ == "__main__":
    import sys

    sys.exit(main())
