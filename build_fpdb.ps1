# Arrête le script si une commande échoue
$ErrorActionPreference = "Stop"

# Fonction pour détecter l'OS
function Detect-OS {
    switch ($PSVersionTable.Platform) {
        "Unix" { "Linux" }
        "MacOSX" { "MacOS" }
        "Win32NT" { "Windows" }
        default { "unknown" }
    }
}

$OS = Detect-OS
Write-Output "Detected OS: $OS"

# Définir le chemin de base
$BASE_PATH = Get-Location

# Chemin de base où se trouvent vos fichiers Python
$BASE_PATH2 = $BASE_PATH

Write-Output "Adjusted BASE_PATH2 for OS: $BASE_PATH2"

# Nom du script principal pour lequel générer l'exécutable
$MAIN_SCRIPT = "fpdb.pyw"
$SECOND_SCRIPT = "HUD_main.pyw"

# Options de base PyInstaller
$PYINSTALLER_OPTIONS = "--noconfirm --onedir --windowed --log-level=DEBUG"

# Liste de tous les fichiers et dossiers à ajouter
$FILES = @(
    "Anonymise.py",
    "api.py",
    "app.py",
    "Archive.py",
    "Aux_Base.py",
    "Aux_Classic_Hud.py",
    "Aux_Hud.py",
    "base_model.py",
    "BetfairToFpdb.py",
    "BetOnlineToFpdb.py",
    "BovadaSummary.py",
    "BovadaToFpdb.py",
    "bug-1823.py",
    "CakeToFpdb.py",
    "Card.py",
    "Cardold.py",
    "card_path.py",
    "Charset.py",
    "Configuration.py",
    "contributors.txt",
    "Database.py",
    "Databaseold.py",
    "db_sqlite3.md",
    "decimal_wrapper.py",
    "Deck.py",
    "dependencies.txt",
    "DerivedStats.py",
    "DerivedStats_old.py",
    "DetectInstalledSites.py",
    "Exceptions.py",
    "files.qrc",
    "files_rc.py",
    "Filters.py",
    "fpdb.pyw",
    "fpdb.toml",
    "fpdb_prerun.py",
    "GGPokerToFpdb.py",
    "GuiAutoImport.py",
    "GuiBulkImport.py",
    "GuiDatabase.py",
    "GuiGraphViewer.py",
    "GuiHandViewer.py",
    "GuiLogView.py",
    "GuiOddsCalc.py",
    "GuiPositionalStats.py",
    "GuiPrefs.py",
    "GuiReplayer.py",
    "GuiRingPlayerStats.py",
    "GuiSessionViewer.py",
    "GuiStove.py",
    "GuiTourneyGraphViewer.py",
    "GuiTourneyImport.py",
    "GuiTourneyPlayerStats.py",
    "GuiTourneyViewer.py",
    "Hand.py",
    "HandHistory.py",
    "HandHistoryConverter.py",
    "Hello.py",
    "Hud.py",
    "HUD_config.test.xml",
    "HUD_config.xml",
    "HUD_config.xml.example",
    "HUD_config.xml.exemple",
    "HUD_main.pyw",
    "HUD_run_me.py",
    "IdentifySite.py",
    "Importer-old.py",
    "Importer.py",
    "ImporterLight.py",
    "interlocks.py",
    "iPokerSummary.py",
    "iPokerToFpdb.py",
    "KingsClubToFpdb.py",
    "L10n.py",
    "LICENSE",
    "linux_table_detect.py",
    "logging.conf",
    "Makefile",
    "MergeStructures.py",
    "MergeSummary.py",
    "MergeToFpdb.py",
    "montecarlo.py",
    "Mucked.py",
    "OddsCalc.py",
    "OddsCalcnew.py",
    "OddsCalcNew2.py",
    "OddsCalcPQL.py",
    "Options.py",
    "OSXTables.py",
    "P5sResultsParser.py",
    "PacificPokerSummary.py",
    "PacificPokerToFpdb.py",
    "PartyPokerToFpdb.py",
    "Pokenum_api_call.py",
    "pokenum_example.py",
    "pokereval.py",
    "PokerStarsStructures.py",
    "PokerStarsSummary.py",
    "PokerStarsToFpdb.py",
    "PokerTrackerSummary.py",
    "PokerTrackerToFpdb.py",
    "Popup.py",
    "ppt.py",
    "ps.ico",
    "RazzStartHandGenerator.py",
    "run_fpdb.py",
    "RushNotesAux.py",
    "RushNotesMerge.py",
    "ScriptAddStatToRegression.py",
    "ScriptFetchMergeResults.py",
    "ScriptFetchWinamaxResults.py",
    "ScriptGenerateWikiPage.py",
    "SealsWithClubsToFpdb.py",
    "settings.json",
    "setup.py",
    "sim.py",
    "sim2.py",
    "simulation.py",
    "SitenameSummary.py",
    "SplitHandHistory.py",
    "SQL.py",
    "sql_request.py",
    "start_fpdb_web.py",
    "Stats.py",
    "Stove.py",
    "Summaries.py",
    "TableWindow.py",
    "TestDetectInstalledSites.py",
    "TestHandsPlayers.py",
    "testodd.py",
    "TournamentTracker.py",
    "TourneySummary.py",
    "TreeViewTooltips.py",
    "UnibetToFpdb.py",
    "UnibetToFpdb_old.py",
    "upd_indexes.sql",
    "wina.ico",
    "WinamaxSummary.py",
    "WinamaxToFpdb.py",
    "windows_make_bats.py",
    "WinningSummary.py",
    "WinningToFpdb.py",
    "WinTables.py",
    "win_table_detect.py",
    "xlib_tester.py",
    "XTables.py",
    "_pokereval_3_11.pyd"
)

$FOLDERS = @(
    "gfx",
    "icons",
    "fonts",
    "locale",
    "ppt",
    "static",
    "templates",
    "utils"
)

# Fonction pour générer la commande PyInstaller avec --add-data
function Generate-PyInstallerCommand {
    param (
        [string]$scriptPath
    )

    $command = "pyinstaller $PYINSTALLER_OPTIONS"

    # Traite les fichiers
    foreach ($file in $FILES) {
        if ($OS -eq "Windows") {
            $command += " --add-data `"$BASE_PATH2\$file;.`""
        } else {
            $command += " --add-data `"$(Join-Path -Path $BASE_PATH2 -ChildPath $file):.`""
        }
    }

    # Traite les dossiers
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

# Fonction pour déplacer les fichiers
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

# Fonction pour copier et supprimer les dossiers
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

# Fonction pour copier HUD_main.exe et le dossier _internal sans écraser les fichiers existants
function Copy-HUDMain {
    param (
        [string]$sourceDir,
        [string]$targetDir
    )

    $hudMainExe = Join-Path -Path $sourceDir -ChildPath "HUD_main.exe"
    $targetExe = Join-Path -Path $targetDir -ChildPath "HUD_main.exe"

    # Copier HUD_main.exe s'il n'existe pas déjà dans le dossier cible
    if (-not (Test-Path -Path $targetExe)) {
        Write-Output "Copie de HUD_main.exe de $hudMainExe à $targetExe"
        Copy-Item -Path $hudMainExe -Destination $targetExe -Force
    }

    # Copier le dossier _internal sans écraser les fichiers existants
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

# Générer et exécuter la commande pour le script principal
$command = Generate-PyInstallerCommand -scriptPath $MAIN_SCRIPT
Write-Output "Exécution : $command"
Invoke-Expression $command

# Générer et exécuter la commande pour le second script, si nécessaire
$command = Generate-PyInstallerCommand -scriptPath $SECOND_SCRIPT
Write-Output "Exécution : $command"
Invoke-Expression $command

Write-Output "Build terminé avec succès."

# Chemins de sortie pour fpdb et HUD_main
$fpdbOutputDir = Join-Path -Path $BASE_PATH -ChildPath "dist/fpdb"
$hudOutputDir = Join-Path -Path $BASE_PATH -ChildPath "dist/HUD_main"

# Chemins internes pour fpdb et HUD_main
$fpdbInternalDir = Join-Path -Path $fpdbOutputDir -ChildPath "_internal"
$hudInternalDir = Join-Path -Path $hudOutputDir -ChildPath "_internal"

# Déplacer les fichiers nécessaires après le build pour fpdb
Move-Files -sourceDir $fpdbInternalDir -targetDir $fpdbOutputDir

# Copier et supprimer les dossiers nécessaires après le build pour fpdb
Copy-And-Remove-Folders -sourceDir $fpdbInternalDir -targetDir $fpdbOutputDir

# Copier HUD_main.exe et le dossier _internal dans fpdb
Copy-HUDMain -sourceDir $hudOutputDir -targetDir $fpdbOutputDir

Write-Output "Déplacement terminé avec succès."
