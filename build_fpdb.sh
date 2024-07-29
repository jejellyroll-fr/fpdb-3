#!/bin/bash

# stop on error
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

# path to base for Windows
if [ "$OS" = "Windows" ]; then
    BASE_PATH2=$(cygpath -w "$BASE_PATH")
else
    BASE_PATH2="$BASE_PATH"
fi

echo "Adjusted BASE_PATH2 for OS: $BASE_PATH2"

# name of the main script
MAIN_SCRIPT="fpdb.pyw"
SECOND_SCRIPT="HUD_main.pyw"

# Options of pyinstaller
PYINSTALLER_OPTIONS="--noconfirm --onedir --windowed --log-level=DEBUG"

# List of all files
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
    #"pokereval.py"
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
    #"_pokereval_3_11.pyd"
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

    # add icon
    command+=" --icon=\"$BASE_PATH2/gfx/tribal.jpg\""

    # process files
    for file in "${FILES[@]}"; do
        if [ "$OS" = "Windows" ]; then
            command+=" --add-data \"$BASE_PATH2/$file;.\""
        else
            command+=" --add-data \"$BASE_PATH2/$file:.\""
        fi
    done

    # process folders
    for folder in "${FOLDERS[@]}"; do
        if [ "$OS" = "Windows" ]; then
            command+=" --add-data \"$BASE_PATH2/$folder;$folder\""
        else
            command+=" --add-data \"$BASE_PATH2/$folder:$folder\""
        fi
    done

    command+=" \"$BASE_PATH2/$script_path\""
    echo "$command"
}

# Function to move files
move_files() {
    local source_dir=$1
    local target_dir=$2

    for file in "${FILES[@]}"; do
        local source_path="$source_dir/$file"
        local target_path="$target_dir/$file"

        if [ -e "$source_path" ]; then
            if [ ! -e "$target_path" ]; then
                echo "Déplacement de $file de $source_path à $target_path"
                mv "$source_path" "$target_path"
            fi
        fi
    done
}

# Function to copy folders
copy_and_remove_folders() {
    local source_dir=$1
    local target_dir=$2

    for folder in "${FOLDERS[@]}"; do
        local source_path="$source_dir/$folder"
        local target_path="$target_dir/$folder"

        if [ -e "$source_path" ]; then
            echo "Déplacement de $folder de $source_path à $target_path"
            cp -r "$source_path" "$target_path"
            rm -r "$source_path"
        fi
    done
}

# Function to copy the HUD_main.exe
copy_hudmain() {
    local source_dir=$1
    local target_dir=$2

    local hud_main_exe="$source_dir/HUD_main.exe"
    local target_exe="$target_dir/HUD_main.exe"

   
    if [ ! -e "$target_exe" ]; then
        echo "Copie de HUD_main.exe de $hud_main_exe à $target_exe"
        cp "$hud_main_exe" "$target_exe"
    fi

   
    local source_internal="$source_dir/_internal"
    local target_internal="$target_dir/_internal"

    if [ -e "$source_internal" ]; then
        find "$source_internal" -type f | while read -r file; do
            local destination_path="$target_internal/${file#$source_internal/}"
            if [ ! -e "$destination_path" ]; then
                echo "Copie de $file à $destination_path"
                mkdir -p "$(dirname "$destination_path")"
                cp "$file" "$destination_path"
            fi
        done
    fi
}

# Generate the pyinstaller command
command=$(generate_pyinstaller_command "$MAIN_SCRIPT")
echo "Exécution : $command"
eval "$command"


command=$(generate_pyinstaller_command "$SECOND_SCRIPT")
echo "Exécution : $command"
eval "$command"

echo "Build success."


fpdb_output_dir="$BASE_PATH/dist/fpdb"
hud_output_dir="$BASE_PATH/dist/HUD_main"


fpdb_internal_dir="$fpdb_output_dir/_internal"
hud_internal_dir="$hud_output_dir/_internal"


move_files "$fpdb_internal_dir" "$fpdb_output_dir"


copy_and_remove_folders "$fpdb_internal_dir" "$fpdb_output_dir"


copy_hudmain "$hud_output_dir" "$fpdb_output_dir"

echo "move success."