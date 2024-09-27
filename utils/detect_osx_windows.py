import Quartz
import AppKit

def get_window_info():
    # Obtenir toutes les fenêtres sur l'écran
    window_list = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)

    # Parcourir toutes les fenêtres et extraire des informations
    for window in window_list:
        window_owner = window.get('kCGWindowOwnerName', 'Inconnu')
        window_name = window.get('kCGWindowName', 'Sans titre')
        window_bounds = window.get('kCGWindowBounds', {})

        x = window_bounds.get('X', 0)
        y = window_bounds.get('Y', 0)
        width = window_bounds.get('Width', 0)
        height = window_bounds.get('Height', 0)

        print(f"Propriétaire de la fenêtre : {window_owner}")
        print(f"Nom de la fenêtre : {window_name}")
        print(f"Coordonnées : ({x}, {y})")
        print(f"Taille : {width}x{height}")
        print("-" * 40)

if __name__ == "__main__":
    get_window_info()
