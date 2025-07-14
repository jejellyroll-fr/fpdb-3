# stop on error
$ErrorActionPreference = "Stop"

# Function to detect OS
function Detect-OS {
    if ($IsWindows) {
        return "Windows"
    } elseif ($IsLinux) {
        return "Linux"
    } elseif ($IsMacOS) {
        return "MacOS"
    } else {
        return "unknown"
    }
}

$OS = Detect-OS
Write-Output "Detected OS: $OS"

# define path to base
$BASE_PATH = Get-Location

# path to base 
$BASE_PATH2 = $BASE_PATH

Write-Output "Adjusted BASE_PATH2 for OS: $BASE_PATH2"

# Name of the main script
$MAIN_SCRIPT = "fpdb.pyw"
$SECOND_SCRIPT = "HUD_main.pyw"

# Options of pyinstaller
$PYINSTALLER_OPTIONS = "--noconfirm --onedir --windowed --log-level=DEBUG"

# List of all files
FILES=@(
    "Aux_Base.py",
    "Aux_Classic_Hud.py",
    "Aux_Hud.py",
    "BovadaSummary.py",
    "BovadaToFpdb.py",
    "CakeToFpdb.py",
    "Card.py",
    "card_path.py",
    "Configuration.py",
    "Database.py",
    "Deck.py",
    "DerivedStats.py",
    "DetectInstalledSites.py",
    "Exceptions.py",
    "Filters.py",
    "fpdb.pyw",
    "fpdb.toml",
    "GGPokerToFpdb.py",
    "GuiAutoImport.py",
    "GuiBulkImport.py",
    "GuiGraphViewer.py",
    "GuiHandViewer.py",
    "GuiLogView.py",
    "GuiPrefs.py",
    "GuiReplayer.py",
    "GuiRingPlayerStats.py",
    "GuiSessionViewer.py",
    "GuiTourneyGraphViewer.py",
    "GuiTourneyPlayerStats.py",
    "Hand.py",
    "HandHistory.py",
    "HandHistoryConverter.py",
    "Hud.py",
    "HUD_config.test.xml",
    "HUD_config.xml",
    "HUD_config.xml.example",
    "HUD_main.pyw",
    "IdentifySite.py",
    "Importer.py",
    "interlocks.py",
    "iPokerSummary.py",
    "iPokerToFpdb.py",
    "KingsClubToFpdb.py",
    "L10n.py",
    "logging.conf",
    "Mucked.py",
    "Options.py",
    "OSXTables.py",
    "PacificPokerSummary.py",
    "PacificPokerToFpdb.py",
    "PartyPokerToFpdb.py",
    "PokerStarsStructures.py",
    "PokerStarsSummary.py",
    "PokerStarsToFpdb.py",
    "PokerTrackerSummary.py",
    "PokerTrackerToFpdb.py",
    "Popup.py",
    "SealsWithClubsToFpdb.py",
    "settings.json",
    "SQL.py",
    "Stats.py",
    "TableWindow.py",
    "TourneySummary.py",
    "UnibetToFpdb.py",
    "WinamaxSummary.py",
    "WinamaxToFpdb.py",
    "WinningSummary.py",
    "WinningToFpdb.py",
    "WinTables.py",
    "XTables.py",
    "loggingFpdb.py"
)

$FOLDERS = @(
    "gfx",
    "icons",
    "fonts",
    "locale",
    "utils"
)

# Function to generate the pyinstaller command
function Generate-PyInstallerCommand {
    param (
        [string]$scriptPath
    )

    $command = "pyinstaller $PYINSTALLER_OPTIONS"

    # add icon
    if ($OS -eq "Windows") {
        $command += " --icon=`"$BASE_PATH2\gfx\tribal.jpg`""
    } else {
        $command += " --icon=`"$(Join-Path -Path $BASE_PATH2 -ChildPath gfx\tribal.jpg)`""
    }

    # process files
    foreach ($file in $FILES) {
        if ($OS -eq "Windows") {
            $command += " --add-data `"$BASE_PATH2\$file;.`""
        } else {
            $command += " --add-data `"$(Join-Path -Path $BASE_PATH2 -ChildPath $file):.`""
        }
    }

    # process folders
    foreach ($folder in $FOLDERS) {
        if ($OS -eq "Windows") {
            $command += " --add-data `"$BASE_PATH2\$folder;.\$folder`""
        } else {
            $command += " --add-data `"$(Join-Path -Path $BASE_PATH2 -ChildPath $folder):$folder`""
        }
    }

    $command += " `"$BASE_PATH2\$scriptPath`""

    return $command
}

# Function to move files
function Move-Files {
    param (
        [string]$sourceDir,
        [string]$targetDir
    )

    foreach ($file in $FILES) {
        $sourcePath = Join-Path -Path $sourceDir -ChildPath $file
        $targetPath = Join-Path -Path $targetDir -ChildPath $file

        if (Test-Path -Path $sourcePath) {
            if (-not (Test-Path -Path $targetPath)) {
                Write-Output "Déplacement de $file de $sourcePath à $targetPath"
                Move-Item -Path $sourcePath -Destination $targetPath -Force
            }
        }
    }
}

# Function to copy and remove folders
function Copy-And-Remove-Folders {
    param (
        [string]$sourceDir,
        [string]$targetDir
    )

    foreach ($folder in $FOLDERS) {
        $sourcePath = Join-Path -Path $sourceDir -ChildPath $folder
        $targetPath = Join-Path -Path $targetDir -ChildPath $folder

        if (Test-Path -Path $sourcePath) {
            Write-Output "Déplacement de $folder de $sourcePath à $targetPath"
            Copy-Item -Path $sourcePath -Destination $targetPath -Recurse -Force
            Remove-Item -Path $sourcePath -Recurse -Force
        }
    }
}

# Function to copy HUD_main.exe
function Copy-HUDMain {
    param (
        [string]$sourceDir,
        [string]$targetDir
    )

    $hudMainExe = Join-Path -Path $sourceDir -ChildPath "HUD_main.exe"
    $targetExe = Join-Path -Path $targetDir -ChildPath "HUD_main.exe"


    if (-not (Test-Path -Path $targetExe)) {
        Write-Output "Copie de HUD_main.exe de $hudMainExe à $targetExe"
        Copy-Item -Path $hudMainExe -Destination $targetExe -Force
    }


    $sourceInternal = Join-Path -Path $sourceDir -ChildPath "_internal"
    $targetInternal = Join-Path -Path $targetDir -ChildPath "_internal"

    if (Test-Path -Path $sourceInternal) {
        Get-ChildItem -Path $sourceInternal -Recurse | ForEach-Object {
            $destinationPath = Join-Path -Path $targetInternal -ChildPath ($_.FullName.Substring($sourceInternal.Length + 1))
            if (-not (Test-Path -Path $destinationPath)) {
                Write-Output "Copie de $_.FullName à $destinationPath"
                Copy-Item -Path $_.FullName -Destination $destinationPath -Force
            }
        }
    }
}

# Generate the pyinstaller command for the main script
$command = Generate-PyInstallerCommand -scriptPath $MAIN_SCRIPT
Write-Output "Exécution : $command"
Invoke-Expression $command

# Generate the pyinstaller command for the second script
$command = Generate-PyInstallerCommand -scriptPath $SECOND_SCRIPT
Write-Output "Exécution : $command"
Invoke-Expression $command

Write-Output "Build success"


$fpdbOutputDir = Join-Path -Path $BASE_PATH -ChildPath "dist/fpdb"
$hudOutputDir = Join-Path -Path $BASE_PATH -ChildPath "dist/HUD_main"


$fpdbInternalDir = Join-Path -Path $fpdbOutputDir -ChildPath "_internal"
$hudInternalDir = Join-Path -Path $hudOutputDir -ChildPath "_internal"


Move-Files -sourceDir $fpdbInternalDir -targetDir $fpdbOutputDir


Copy-And-Remove-Folders -sourceDir $fpdbInternalDir -targetDir $fpdbOutputDir


Copy-HUDMain -sourceDir $hudOutputDir -targetDir $fpdbOutputDir

Write-Output "Move success"
