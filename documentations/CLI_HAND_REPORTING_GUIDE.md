# Guide d'utilisation CLI - Hand Data Reporting / CLI Usage Guide - Hand Data Reporting

## 🇫🇷 Version Française

### Présentation

Le système de reporting des mains FPDB permet d'analyser la qualité du parsing des historiques de mains et de générer des rapports détaillés. Cette fonctionnalité est intégrée dans l'interface en ligne de commande (CLI) pour une utilisation facile et flexible.

### Installation et Configuration

```bash
# Installer les dépendances avec uv
uv install

# Ou avec pip traditionnel
pip install -r requirements.txt
```

### Syntaxe de Base

```bash
uv run python importer_cli.py [OPTIONS] FICHIER_OU_DOSSIER
```

### Options Principales

#### Activation du Reporting
```bash
--enable-hand-reporting          # Active le système de reporting des mains
```

#### Niveaux de Rapport
```bash
--report-level NIVEAU           # Définit le niveau de détail du rapport
```

**Niveaux disponibles :**
- `hierarchy` : Vue d'ensemble hiérarchique par type de jeu
- `detailed` : Rapport détaillé avec échantillon de mains (2 premières)  
- `full` : Rapport complet avec toutes les mains et informations enrichies

#### Options de Debug
```bash
--debug                         # Active les logs détaillés pour diagnostic
```

#### Identification du Site
```bash
--site SITE_NAME               # Force l'identification du site poker
```

### Exemples d'Utilisation

#### 1. Rapport Rapide (Hiérarchique)
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level hierarchy fichier.txt
```

**Idéal pour :**
- Vue d'ensemble rapide de la répartition des types de jeux
- Vérification de la classification automatique
- Contrôle qualité rapide

#### 2. Analyse Détaillée
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level detailed fichier.txt
```

**Idéal pour :**
- Analyse approfondie d'un échantillon de mains
- Vérification des données extraites
- Diagnostic des problèmes de parsing

#### 3. Analyse Complète
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level full fichier.txt
```

**Idéal pour :**
- Analyse exhaustive de tous les détails
- Rapport de qualité complet
- Debug approfondi des problèmes

#### 4. Debug Mode pour Diagnostic
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level full --debug fichier.txt
```

**Idéal pour :**
- Diagnostic technique des problèmes
- Développement et debugging
- Analyse des structures internes

### Gestion des Fichiers avec Caractères Spéciaux

Pour les fichiers contenant des caractères spéciaux (`$`, `,`, espaces), utilisez des guillemets simples :

```bash
# ✅ Correct
uv run python importer_cli.py --enable-hand-reporting --report-level full '/path/file-$5-$10,$1.25Ante.txt'

# ❌ Incorrect
uv run python importer_cli.py --enable-hand-reporting --report-level full "/path/file-$5-$10,$1.25Ante.txt"
```

### Sites Poker Supportés

```bash
--site Bovada              # Bovada Poker
--site PokerStars          # PokerStars
--site PartyPoker          # PartyPoker
--site GGPoker             # GGPoker
# ... et d'autres sites supportés
```

### Types de Jeux Supportés

Le système classe automatiquement les mains dans une hiérarchie organisée :

#### Cash Games
- **Hold'em** : No Limit, Pot Limit, Fixed Limit
- **Stud** : 7-Card Stud, 5-Card Stud, Hi/Lo Split
- **Draw** : 5-Card Draw, 2-7 Triple Draw, Badugi

#### Tournois/SNGs
- **Hold'em** : No Limit, Pot Limit, Fixed Limit
- **Stud** : 7-Card Stud, 5-Card Stud, Hi/Lo Split
- **Draw** : 5-Card Draw, 2-7 Triple Draw, Badugi

### Informations Affichées

#### Niveau Hierarchy
- Répartition par type de jeu
- Compteurs de mains par variante
- Taux de succès global

#### Niveau Detailed
- Détails de quelques mains représentatives
- Informations des joueurs
- Actions par street
- Cartes visibles

#### Niveau Full
- **Toutes les mains** avec détails complets
- **Informations financières** : Rake, Ante, Blinds, Collections
- **Structure des mises** : Progression détaillée par street
- **Stacks finaux** : Soldes de tous les joueurs
- **Diagnostic intelligent** : Alertes spécifiques au type de jeu
- **Cartes des joueurs** : Hole cards extraites
- **Actions détaillées** : Séquence complète par street

### Exemples Pratiques

#### Analyser un fichier Stud
```bash
uv run python importer_cli.py \
  --site Bovada \
  --enable-hand-reporting \
  --report-level full \
  '/home/user/fichiers/7-StudHL-USD-RING-$5-$10,$1.25Ante-201404.txt'
```

#### Traitement par lot
```bash
uv run python importer_cli.py \
  --enable-hand-reporting \
  --report-level hierarchy \
  /dossier/historiques/
```

#### Debug d'un problème spécifique
```bash
uv run python importer_cli.py \
  --site PokerStars \
  --enable-hand-reporting \
  --report-level full \
  --debug \
  fichier_problematique.txt
```

### Conseils d'Utilisation

1. **Commencez par `hierarchy`** pour une vue d'ensemble
2. **Utilisez `detailed`** pour l'analyse quotidienne
3. **Réservez `full`** pour les analyses approfondies
4. **Activez `--debug`** uniquement pour le diagnostic technique
5. **Spécifiez `--site`** si la détection automatique échoue

---

## 🇬🇧 English Version

### Overview

The FPDB Hand Data Reporting system allows analyzing the quality of hand history parsing and generating detailed reports. This functionality is integrated into the command-line interface (CLI) for easy and flexible usage.

### Installation and Setup

```bash
# Install dependencies with uv
uv install

# Or with traditional pip
pip install -r requirements.txt
```

### Basic Syntax

```bash
uv run python importer_cli.py [OPTIONS] FILE_OR_DIRECTORY
```

### Main Options

#### Enable Reporting
```bash
--enable-hand-reporting          # Enables hand data reporting system
```

#### Report Levels
```bash
--report-level LEVEL            # Sets the detail level of the report
```

**Available levels:**
- `hierarchy` : Hierarchical overview by game type
- `detailed` : Detailed report with hand samples (first 2 hands)
- `full` : Complete report with all hands and enriched information

#### Debug Options
```bash
--debug                         # Enables detailed logs for diagnostics
```

#### Site Identification
```bash
--site SITE_NAME               # Forces poker site identification
```

### Usage Examples

#### 1. Quick Report (Hierarchical)
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level hierarchy file.txt
```

**Ideal for:**
- Quick overview of game type distribution
- Verification of automatic classification
- Rapid quality control

#### 2. Detailed Analysis
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level detailed file.txt
```

**Ideal for:**
- In-depth analysis of hand samples
- Verification of extracted data
- Parsing problem diagnosis

#### 3. Complete Analysis
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level full file.txt
```

**Ideal for:**
- Exhaustive analysis of all details
- Complete quality report
- Thorough problem debugging

#### 4. Debug Mode for Diagnostics
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level full --debug file.txt
```

**Ideal for:**
- Technical problem diagnosis
- Development and debugging
- Internal structure analysis

### Handling Files with Special Characters

For files containing special characters (`$`, `,`, spaces), use single quotes:

```bash
# ✅ Correct
uv run python importer_cli.py --enable-hand-reporting --report-level full '/path/file-$5-$10,$1.25Ante.txt'

# ❌ Incorrect
uv run python importer_cli.py --enable-hand-reporting --report-level full "/path/file-$5-$10,$1.25Ante.txt"
```

### Supported Poker Sites

```bash
--site Bovada              # Bovada Poker
--site PokerStars          # PokerStars
--site PartyPoker          # PartyPoker
--site GGPoker             # GGPoker
# ... and other supported sites
```

### Supported Game Types

The system automatically classifies hands into an organized hierarchy:

#### Cash Games
- **Hold'em**: No Limit, Pot Limit, Fixed Limit
- **Stud**: 7-Card Stud, 5-Card Stud, Hi/Lo Split
- **Draw**: 5-Card Draw, 2-7 Triple Draw, Badugi

#### Tournaments/SNGs
- **Hold'em**: No Limit, Pot Limit, Fixed Limit
- **Stud**: 7-Card Stud, 5-Card Stud, Hi/Lo Split
- **Draw**: 5-Card Draw, 2-7 Triple Draw, Badugi

### Displayed Information

#### Hierarchy Level
- Distribution by game type
- Hand counters by variant
- Overall success rate

#### Detailed Level
- Details of representative hands
- Player information
- Actions by street
- Visible cards

#### Full Level
- **All hands** with complete details
- **Financial information**: Rake, Ante, Blinds, Collections
- **Betting structure**: Detailed progression by street
- **Final stacks**: All players' balances
- **Intelligent diagnostics**: Game-specific alerts
- **Player cards**: Extracted hole cards
- **Detailed actions**: Complete sequence by street

### Practical Examples

#### Analyze a Stud file
```bash
uv run python importer_cli.py \
  --site Bovada \
  --enable-hand-reporting \
  --report-level full \
  '/home/user/files/7-StudHL-USD-RING-$5-$10,$1.25Ante-201404.txt'
```

#### Batch processing
```bash
uv run python importer_cli.py \
  --enable-hand-reporting \
  --report-level hierarchy \
  /directory/histories/
```

#### Debug a specific problem
```bash
uv run python importer_cli.py \
  --site PokerStars \
  --enable-hand-reporting \
  --report-level full \
  --debug \
  problematic_file.txt
```

### Usage Tips

1. **Start with `hierarchy`** for an overview
2. **Use `detailed`** for daily analysis
3. **Reserve `full`** for thorough investigations
4. **Enable `--debug`** only for technical diagnosis
5. **Specify `--site`** if automatic detection fails

---

## 🔧 Technical Notes

### Performance Considerations
- `hierarchy` level: Fastest, minimal memory usage
- `detailed` level: Moderate resource usage, good balance
- `full` level: Most resource-intensive, complete information

### Output Formats
- Console output: Formatted text with emojis and colors
- JSON export: Available via `export_json()` method for programmatic processing

### Troubleshooting

#### No valid files found
- Check file path and permissions
- Verify file extension is recognized
- Use single quotes for special characters in filenames (e.g., `'file-$5-$10.txt'`)

#### Classification errors
- Enable `--debug` to see classification logic
- Specify `--site` if auto-detection fails
- Check if game type is supported

#### Missing information in reports
- Verify original hand history file quality
- Check if parser supports all features of the site
- Use `--debug` to see what data is available

#### Debugging Failed Imports

When encountering parsing issues, follow this systematic debugging approach:

**1. Check Import Summary**
Look for these indicators in the summary:
- `⚠️ Duplicates: X` - Hands already in database
- `↪️ Partial (skipped): X` - Incomplete hand histories
- `❌ Errors: X` - True parsing failures

**2. Enable Debug Mode**
```bash
uv run python importer_cli.py --enable-hand-reporting --report-level full --debug problem_file.txt
```

**3. Understanding Error Categories**
The improved reporting categorizes issues by severity:
- `ℹ️ MAINS PARTIELLES` - Incomplete hands (usually normal)
- `⚠️ Warning` - Minor issues (blinds problems, etc.)
- `❌ Error` - Parsing failures (KeyError, AttributeError)
- `🔥 Critical` - Malformed file format

**4. Partial Hands vs Real Errors**
- **Partial hands**: Normal for `.partial.txt` files or interrupted games
- **Real errors**: Indicate parser bugs or unsupported formats

**Example Debug Session:**
```bash
# Step 1: Quick overview
uv run python importer_cli.py --enable-hand-reporting --report-level hierarchy file.txt

# Step 2: If errors found, get details
uv run python importer_cli.py --enable-hand-reporting --report-level full file.txt

# Step 3: If still unclear, enable debug
uv run python importer_cli.py --enable-hand-reporting --report-level full --debug file.txt
```

---

## 📊 Report Samples

### Hierarchy Report Sample
```
🎮 RÉPARTITION PAR TYPE DE JEU:

💰 CASH GAMES (4 mains):
   🎯 Stud (4 mains):
      • 7-Card Stud: 4 mains
```

### Full Report Sample
```
Main #1:
   ID: 2604291510
   Table: 1178621
   Type: studhi fl
   💰 Détails financiers:
      - Rake: $0
      - Ante: $0.01
   📊 Stacks finaux:
      - Hero: $0.37
   💸 Structure des mises par street:
      SEVENTH:
         Hero: $0.10
```

---

*Documentation générée automatiquement - Generated automatically*
*Version: 2025-08-02*
