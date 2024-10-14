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
    "decimal_wrapper.py"
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
    "GuiPositionalStats.py"
    "GuiPrefs.py"
    "GuiReplayer.py"
    "GuiRingPlayerStats.py"
    "GuiSessionViewer.py"
    "GuiTourneyGraphViewer.py"
    "GuiTourneyPlayerStats.py"
    "GuiTourneyViewer.py"
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
    "SplitHandHistory.py"
    "SQL.py"
    "Stats.py"
    "Summaries.py"
    "TableWindow.py"
    "TourneySummary.py"
    "UnibetToFpdb.py"
    "WinamaxSummary.py"
    "WinamaxToFpdb.py"
    "WinningSummary.py"
    "WinningToFpdb.py"
    "WinTables.py"
    "XTables.py"
)

FOLDERS=(
    "gfx"
    "icons"
    "fonts"
    "locale"
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