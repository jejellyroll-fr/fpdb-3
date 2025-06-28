#!/bin/bash

# Arrêter en cas d'erreur
set -e

# Fonction pour détecter l'OS
detect_os() {
    case "$(uname -s)" in
        Linux*)     echo "Linux" ;;
        *)          echo "unknown" ;;
    esac
}

OS=$(detect_os)
echo "Detected OS: $OS"

if [ "$OS" != "Linux" ]; then
    echo "Ce script est uniquement destiné à Linux."
    exit 1
fi

# Téléchargement de appimagetool
if [ ! -f ./appimagetool-x86_64.AppImage ]; then
    wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
fi

# Définir le chemin de base
BASE_PATH=$(pwd)

echo "Chemin de base : $BASE_PATH"

# Nom du script principal
MAIN_SCRIPT="fpdb.pyw"
SECOND_SCRIPT="HUD_main.pyw"

# Options de pyinstaller
PYINSTALLER_OPTIONS="--noconfirm --onedir --windowed --log-level=DEBUG"

# Liste de tous les fichiers pour fpdb
FILES=(
    "Aux_Base.py"
    "Aux_Classic_Hud.py"
    "Aux_Hud.py"
    "BetfairToFpdb.py"
    "BetOnlineToFpdb.py"
    "BovadaSummary.py"
    "BovadaToFpdb.py"
    "CakeToFpdb.py"
    "Card.py"
    "card_path.py"
    "Configuration.py"
    "Database.py"
    "Deck.py"
    "DerivedStats.py"
    "DetectInstalledSites.py"
    "Exceptions.py"
    "Filters.py"
    "fpdb.pyw"
    "fpdb.toml"
    "GGPokerToFpdb.py"
    "GuiAutoImport.py"
    "GuiBulkImport.py"
    "GuiGraphViewer.py"
    "GuiHandViewer.py"
    "GuiLogView.py"
    "GuiPrefs.py"
    "GuiReplayer.py"
    "GuiRingPlayerStats.py"
    "GuiSessionViewer.py"
    "GuiTourneyGraphViewer.py"
    "GuiTourneyPlayerStats.py"
    "Hand.py"
    "HandHistory.py"
    "HandHistoryConverter.py"
    "Hud.py"
    "HUD_config.test.xml"
    "HUD_config.xml"
    "HUD_config.xml.example"
    "HUD_main.pyw"
    "IdentifySite.py"
    "Importer.py"
    "interlocks.py"
    "iPokerSummary.py"
    "iPokerToFpdb.py"
    "KingsClubToFpdb.py"
    "L10n.py"
    "logging.conf"
    "MergeStructures.py"
    "MergeSummary.py"
    "MergeToFpdb.py"
    "Mucked.py"
    "Options.py"
    "OSXTables.py"
    "PacificPokerSummary.py"
    "PacificPokerToFpdb.py"
    "PartyPokerToFpdb.py"
    "PokerStarsStructures.py"
    "PokerStarsSummary.py"
    "PokerStarsToFpdb.py"
    "PokerTrackerSummary.py"
    "PokerTrackerToFpdb.py"
    "Popup.py"
    "SealsWithClubsToFpdb.py"
    "settings.json"
    "SQL.py"
    "Stats.py"
    "TableWindow.py"
    "TourneySummary.py"
    "UnibetToFpdb.py"
    "WinamaxSummary.py"
    "WinamaxToFpdb.py"
    "WinningSummary.py"
    "WinningToFpdb.py"
    "WinTables.py"
    "XTables.py"
    "loggingFpdb.py"
)

FOLDERS=(
    "gfx"
    "icons"
    "fonts"
    "locale"
    "utils"
)

# Convertir tribal.jpg en fpdb.png si nécessaire
if [ ! -f "$BASE_PATH/gfx/fpdb.png" ]; then
    if [ -f "$BASE_PATH/gfx/tribal.jpg" ]; then
        magick convert "$BASE_PATH/gfx/tribal.jpg" "$BASE_PATH/gfx/fpdb.png"
    else
        echo "Erreur : tribal.jpg non trouvé dans $BASE_PATH/gfx/"
        exit 1
    fi
fi

# Fonction pour générer la commande pyinstaller
generate_pyinstaller_command() {
    local script_path=$1
    local command="pyinstaller $PYINSTALLER_OPTIONS"

    command+=" --icon=\"$BASE_PATH/gfx/fpdb.png\""
    command+=" --additional-hooks-dir=hooks"

    local hidden_imports=(
        "PyQt5" "qtpy" "qt_material" "qt_material.resources" "xcffib" "xcffib.xproto"
        "gevent" "gevent-websocket" "uvicorn" "requests" "numpy" "pandas" "sqlalchemy"
        "jinja2" "werkzeug" "flask" "fastapi" "orjson" "beautifulsoup4" "matplotlib"
        "six" "pycparser"
    )
    for import in "${hidden_imports[@]}"; do
        command+=" --hidden-import=$import"
    done

    command+=" --add-data=\"$(python -c 'import qt_material; print(qt_material.__path__[0])'):qt_material\""
    command+=" --add-data=\"$(python -c 'import xcffib; print(xcffib.__path__[0])'):xcffib\""
    
    command+=" --collect-submodules=xcffib"
    command+=" --collect-all xcffib"

    for file in "${FILES[@]}"; do
        command+=" --add-data \"$BASE_PATH/$file:./\""
    done

    for folder in "${FOLDERS[@]}"; do
        command+=" --add-data \"$BASE_PATH/$folder:$folder\""
    done

    command+=" \"$BASE_PATH/$script_path\""

    # Écrire la commande dans un fichier temporaire
    echo "#!/bin/bash" > temp_pyinstaller_command.sh
    echo "$command" >> temp_pyinstaller_command.sh
    chmod +x temp_pyinstaller_command.sh
}

# Construire HUD_main d'abord
generate_pyinstaller_command "$SECOND_SCRIPT"
echo "Exécution de la commande pour HUD_main :"
cat temp_pyinstaller_command.sh
./temp_pyinstaller_command.sh

echo "HUD_main build success."

# Construire fpdb
generate_pyinstaller_command "$MAIN_SCRIPT"
echo "Exécution de la commande pour fpdb :"
cat temp_pyinstaller_command.sh
./temp_pyinstaller_command.sh

echo "fpdb build success."

# Nettoyage du fichier temporaire
rm temp_pyinstaller_command.sh

# Copier HUD_main _internal dans fpdb
echo "Copie de HUD_main _internal dans fpdb"
if [ -d "$BASE_PATH/dist/HUD_main/_internal" ]; then
    cp -R "$BASE_PATH/dist/HUD_main/_internal" "$BASE_PATH/dist/fpdb/"
    cp "$BASE_PATH/dist/HUD_main/HUD_main" "$BASE_PATH/dist/fpdb/_internal/"
    echo "Dossier HUD_main _internal copié avec succès."
else
    echo "Erreur : dossier HUD_main _internal non trouvé."
    exit 1
fi

# Création de l'AppImage
APP_DIR="$BASE_PATH/AppDir"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/256x256/apps"

cp -r "$BASE_PATH/dist/fpdb/"* "$APP_DIR/usr/bin/"

# Copier l'icône en fpdb.png
cp "$BASE_PATH/gfx/fpdb.png" "$APP_DIR/usr/share/icons/hicolor/256x256/apps/fpdb.png"
cp "$BASE_PATH/gfx/fpdb.png" "$APP_DIR/fpdb.png"

# Créer un fichier desktop
cat <<EOF > "$APP_DIR/fpdb.desktop"
[Desktop Entry]
Name=fpdb
Exec=fpdb
Icon=fpdb
Type=Application
Categories=Utility;
EOF

# Création du fichier AppRun
cat <<'EOF' > "$APP_DIR/AppRun"
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PYTHONPATH="$HERE/usr/bin"
exec "$HERE/usr/bin/fpdb"
EOF

chmod +x "$APP_DIR/AppRun"

# Créer l'AppImage avec un nom personnalisé en spécifiant l'architecture
ARCH=x86_64 ./appimagetool-x86_64.AppImage "$APP_DIR" fpdb-x86_64.AppImage

# Nettoyer les fichiers de build
echo "Nettoyage des fichiers de build..."
rm -rf "$BASE_PATH/build"
rm -rf "$BASE_PATH/dist/HUD_main"
rm -rf "$APP_DIR"
rm -rf "$BASE_PATH/dist/fpdb"

echo "Nettoyage terminé. L'AppImage a été créée avec succès."