import Quartz


def get_window_info() -> None:
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


if __name__ == "__main__":
    get_window_info()
