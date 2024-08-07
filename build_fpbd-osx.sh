#!/bin/bash

# Stop on error
set -e

# Function to detect the OS
detect_os() {
    case "$(uname -s)" in
        Linux*)     echo "Linux" ;;
        Darwin*)    echo "MacOS" ;;
        CYGWIN*|MINGW*|MSYS_NT*) echo "Windows" ;;
        *)          echo "unknown" ;;
    esac
}

OS=$(detect_os)
echo "Detected OS: $OS"

# Define path to base
BASE_PATH=$(pwd)

# Path to base for Windows
if [ "$OS" = "Windows" ]; then
    BASE_PATH2=$(cygpath -w "$BASE_PATH")
else
    BASE_PATH2="$BASE_PATH"
fi

echo "Adjusted BASE_PATH2 for OS: $BASE_PATH2"

# Name of the main script
MAIN_SCRIPT="fpdb.pyw"
SECOND_SCRIPT="HUD_main.pyw"

# Options of pyinstaller
PYINSTALLER_OPTIONS="--noconfirm --onedir --windowed --log-level=DEBUG"

# List of all files for fpdb
FILES=(
    "Anonymise.py"
    "api.py"
    "app.py"
    "Archive.py"
    "Aux_Base.py"
    "Aux_Classic_Hud.py"
    "Aux_Hud.py"
    "base_model.py"
    "BetfairToFpdb.py"
    "BetOnlineToFpdb.py"
    "BovadaSummary.py"
    "BovadaToFpdb.py"
    "bug-1823.py"
    "CakeToFpdb.py"
    "Card.py"
    "Cardold.py"
    "card_path.py"
    "Charset.py"
    "Configuration.py"
    "contributors.txt"
    "Database.py"
    "Databaseold.py"
    "db_sqlite3.md"
    "decimal_wrapper.py"
    "Deck.py"
    "dependencies.txt"
    "DerivedStats.py"
    "DerivedStats_old.py"
    "DetectInstalledSites.py"
    "Exceptions.py"
    "files.qrc"
    "files_rc.py"
    "Filters.py"
    "fpdb.pyw"
    "fpdb.toml"
    "fpdb_prerun.py"
    "GGPokerToFpdb.py"
    "GuiAutoImport.py"
    "GuiBulkImport.py"
    "GuiDatabase.py"
    "GuiGraphViewer.py"
    "GuiHandViewer.py"
    "GuiLogView.py"
    "GuiOddsCalc.py"
    "GuiPositionalStats.py"
    "GuiPrefs.py"
    "GuiReplayer.py"
    "GuiRingPlayerStats.py"
    "GuiSessionViewer.py"
    "GuiStove.py"
    "GuiTourneyGraphViewer.py"
    "GuiTourneyImport.py"
    "GuiTourneyPlayerStats.py"
    "GuiTourneyViewer.py"
    "Hand.py"
    "HandHistory.py"
    "HandHistoryConverter.py"
    "Hello.py"
    "Hud.py"
    "HUD_config.test.xml"
    "HUD_config.xml"
    "HUD_config.xml.example"
    "HUD_config.xml.exemple"
    "HUD_main.pyw"
    "HUD_run_me.py"
    "IdentifySite.py"
    "Importer-old.py"
    "Importer.py"
    "ImporterLight.py"
    "interlocks.py"
    "iPokerSummary.py"
    "iPokerToFpdb.py"
    "KingsClubToFpdb.py"
    "L10n.py"
    "LICENSE"
    "linux_table_detect.py"
    "logging.conf"
    "Makefile"
    "MergeStructures.py"
    "MergeSummary.py"
    "MergeToFpdb.py"
    "montecarlo.py"
    "Mucked.py"
    "OddsCalc.py"
    "OddsCalcnew.py"
    "OddsCalcNew2.py"
    "OddsCalcPQL.py"
    "Options.py"
    "OSXTables.py"
    "P5sResultsParser.py"
    "PacificPokerSummary.py"
    "PacificPokerToFpdb.py"
    "PartyPokerToFpdb.py"
    "Pokenum_api_call.py"
    "pokenum_example.py"
    "PokerStarsStructures.py"
    "PokerStarsSummary.py"
    "PokerStarsToFpdb.py"
    "PokerTrackerSummary.py"
    "PokerTrackerToFpdb.py"
    "Popup.py"
    "ppt.py"
    "ps.ico"
    "RazzStartHandGenerator.py"
    "run_fpdb.py"
    "RushNotesAux.py"
    "RushNotesMerge.py"
    "ScriptAddStatToRegression.py"
    "ScriptFetchMergeResults.py"
    "ScriptFetchWinamaxResults.py"
    "ScriptGenerateWikiPage.py"
    "SealsWithClubsToFpdb.py"
    "settings.json"
    "setup.py"
    "sim.py"
    "sim2.py"
    "simulation.py"
    "SitenameSummary.py"
    "SplitHandHistory.py"
    "SQL.py"
    "sql_request.py"
    "start_fpdb_web.py"
    "Stats.py"
    "Stove.py"
    "Summaries.py"
    "TableWindow.py"
    "TestDetectInstalledSites.py"
    "TestHandsPlayers.py"
    "testodd.py"
    "TournamentTracker.py"
    "TourneySummary.py"
    "TreeViewTooltips.py"
    "UnibetToFpdb.py"
    "UnibetToFpdb_old.py"
    "upd_indexes.sql"
    "wina.ico"
    "WinamaxSummary.py"
    "WinamaxToFpdb.py"
    "windows_make_bats.py"
    "WinningSummary.py"
    "WinningToFpdb.py"
    "WinTables.py"
    "win_table_detect.py"
    "xlib_tester.py"
    "XTables.py"
)

FOLDERS=(
    "gfx"
    "icons"
    "fonts"
    "locale"
    "ppt"
    "static"
    "templates"
    "utils"
)

# Function to generate the pyinstaller command
generate_pyinstaller_command() {
    local script_path=$1
    local command="pyinstaller $PYINSTALLER_OPTIONS"

    # Add icon
    command+=" --icon=\"$BASE_PATH2/gfx/tribal.icns\""

    # Process files
    for file in "${FILES[@]}"; do
        command+=" --add-data \"$BASE_PATH2/$file:./\""
    done

    # Process folders
    for folder in "${FOLDERS[@]}"; do
        command+=" --add-data \"$BASE_PATH2/$folder:$folder\""
    done

    command+=" \"$BASE_PATH2/$script_path\""
    echo "$command"
}

# Build HUD_main first
command=$(generate_pyinstaller_command "$SECOND_SCRIPT")
echo "Exécution : $command"
eval "$command"

echo "HUD_main build success."

# Build fpdb
command=$(generate_pyinstaller_command "$MAIN_SCRIPT")
echo "Exécution : $command"
eval "$command"

echo "fpdb build success."

# Copy HUD_main _internal to fpdb
echo "Copying HUD_main _internal to fpdb"
if [ -d "$BASE_PATH/dist/HUD_main/_internal" ]; then
    cp -R "$BASE_PATH/dist/HUD_main/_internal" "$BASE_PATH/dist/fpdb/"
    cp "$BASE_PATH/dist/HUD_main/HUD_main" "$BASE_PATH/dist/fpdb/_internal/"
    echo "HUD_main _internal folder copied successfully."
else
    echo "Error: HUD_main _internal folder not found."
    exit 1
fi

# Create .app bundle for macOS
if [ "$OS" = "MacOS" ]; then
    APP_NAME="fpdb3"
    APP_DIR="$BASE_PATH/dist/$APP_NAME.app/Contents/MacOS"
    RES_DIR="$BASE_PATH/dist/$APP_NAME.app/Contents/Resources"

    # Create AppDir structure
    mkdir -p "$APP_DIR"
    mkdir -p "$RES_DIR"

    # Copy built files to AppDir, including the first _internal
    cp -R "$BASE_PATH/dist/fpdb/"* "$RES_DIR/"

    # Create the nested _internal structure
    mkdir -p "$RES_DIR/_internal/_internal"

    # Copy the content of the original _internal to the nested _internal
    cp -R "$BASE_PATH/dist/fpdb/_internal/"* "$RES_DIR/_internal/_internal/"

    echo "Nested _internal structure created successfully."

    # Create launcher script
    cat <<EOF >"$APP_DIR/$APP_NAME"
#!/bin/bash
# Définir le chemin de base
BASE_DIR="\$(cd "\$(dirname "\$0")/../Resources" && pwd)"
# Définir les variables d'environnement
export DYLD_LIBRARY_PATH="\$BASE_DIR:\$BASE_DIR/_internal:\$DYLD_LIBRARY_PATH"
export PYTHONHOME="\$BASE_DIR/_internal"
export PYTHONPATH="\$BASE_DIR:\$BASE_DIR/_internal:\$PYTHONPATH"
# Lancer l'application principale
"\$BASE_DIR/fpdb"
EOF

    # Make launcher executable
    chmod +x "$APP_DIR/$APP_NAME"

    # Create Info.plist
    cat <<EOF >"$BASE_PATH/dist/$APP_NAME.app/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>
    <string>tribal.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.example.$APP_NAME</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

    # Copy the existing tribal.icns file
    if [ -f "$BASE_PATH2/gfx/tribal.icns" ]; then
        cp "$BASE_PATH2/gfx/tribal.icns" "$RES_DIR/tribal.icns"
    else
        echo "Warning: tribal.icns not found in gfx folder. Icon will be missing."
    fi

    # Ensure all files are executable
    chmod -R 755 "$APP_DIR"
    chmod -R 755 "$RES_DIR"

    # Remove quarantine attribute
    xattr -cr "$BASE_PATH/dist/$APP_NAME.app"

    # Check if HUD_main _internal is in the correct location
    if [ -d "$RES_DIR/_internal/_internal" ] && [ -f "$RES_DIR/_internal/_internal/HUD_main" ]; then
        echo "HUD_main _internal found in the correct nested location."
    else
        echo "Error: HUD_main _internal not found in the nested structure in $RES_DIR"
        exit 1
    fi

    # List contents of _internal folder for verification
    echo "Contents of $RES_DIR/_internal:"
    ls -R "$RES_DIR/_internal"

    echo "App bundle created successfully."
    echo "You can now test the app by running:"
    echo "open \"$BASE_PATH/dist/$APP_NAME.app\""

    # Check dependencies of HUD_main
    echo "Checking dependencies of HUD_main:"
    otool -L "$BASE_PATH/dist/$APP_NAME.app/Contents/Resources/_internal/_internal/HUD_main"

    # Clean up build files
    echo "Cleaning up build files..."
    rm -rf "$BASE_PATH/build"
    rm -rf "$BASE_PATH/dist/fpdb"
    rm -rf "$BASE_PATH/dist/HUD_main"


    echo "Cleanup completed. Only $APP_NAME.app remains in the dist folder."
fi