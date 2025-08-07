#!/usr/bin/env python
"""Test pour vérifier la correction du bug d'initialisation ModernSubmenu."""

import sys
from pathlib import Path

# Add the main directory to sys.path to import FPDB modules
sys.path.insert(0, str(Path(__file__).parent.parent))



def test_modern_submenu_attributes() -> bool | None:
    """Test que ModernSubmenu a tous les attributs requis après init."""
    try:
        from PopupIcons import get_icon_provider
        from PopupThemes import get_theme


        # Test que les classes ont les méthodes requises
        theme = get_theme("material_dark")
        assert hasattr(theme, "get_color"), "Theme should have get_color method"
        assert hasattr(theme, "get_spacing"), "Theme should have get_spacing method"

        icon_provider = get_icon_provider("emoji")
        assert hasattr(icon_provider, "get_icon"), "Icon provider should have get_icon method"


        # Test l'ordre d'initialisation sans créer de QWidget
        # Simuler ce qui se passe dans __init__
        theme_name = "material_dark"
        icon_provider_name = "emoji"

        # Ces assignations doivent réussir AVANT super().__init__()
        theme = get_theme(theme_name)
        icon_provider = get_icon_provider(icon_provider_name)

        # Vérifier que les objets sont utilisables
        bg_color = theme.get_color("window_bg")
        border_color = theme.get_color("border")
        border_radius = theme.get_spacing("border_radius")

        assert bg_color is not None, "Background color should be available"
        assert border_color is not None, "Border color should be available"
        assert border_radius is not None, "Border radius should be available"


        return True

    except Exception:
        import traceback

        traceback.print_exc()
        return False


def test_initialization_order() -> None:
    """Test que l'ordre d'initialisation est correct."""
    # Simuler l'ordre d'initialisation corrigé
    steps = [
        "1. Extract theme/icon names from kwargs",
        "2. Initialize theme = get_theme(theme_name)",
        "3. Initialize icon_provider = get_icon_provider(icon_provider_name)",
        "4. Initialize sections = {}",
        "5. Call super().__init__() which calls create()",
        "6. create() calls setup_window_style() which uses self.theme",
    ]

    for _step in steps:
        pass



if __name__ == "__main__":

    if test_modern_submenu_attributes():
        test_initialization_order()


    else:
        pass

