# fpdb-3 — Plan d'amélioration (branche `bigbang`)

> Établi le 2026-07-12. Vise l'ergonomie (menus, i18n), la fiabilité multi-backend
> (SQLite / PostgreSQL / MySQL-MariaDB), la qualité du code et le domaine poker.
> Statut mis à jour au fil des vagues.

## État des lieux (constats mesurés)

| Signal | Réalité observée |
|---|---|
| **i18n** | `L10n.py` (gettext + QTranslator) et 9+ `.po` existants, mais **0 `.mo` compilé**, layout non standard, chaînes menus non marquées → multilang non fonctionnel *(corrigé en Vague 1)* |
| **Menus** | 9 menus top-level (`fpdb.pyw`), regroupement incohérent (Import vs HUD, Themes en top-level, DB éclatée) *(corrigé en Vague 1)* |
| **God modules** | `SQL.py` ~12k lignes, `Database.py` ~6,6k, `Stats.py` ~5,1k, `Card.py` ~4k, `DerivedStats.py` ~3,9k |
| **Dette lint** | `ruff` : ~2900 erreurs non traitées ; ~78 `TODO/FIXME/HACK` |
| **Typage** | `from __future__ import annotations` dans ~162 fichiers, mais **pas de mypy/pyright** en CI |
| **DB multi-backend** | `SQL.py` code en dur des variantes par backend → fragile (bugs récents `Rank`, boolean, isolation, FK) |
| **Parsers** | 26 convertisseurs `*ToFpdb.py` |
| **Duplication** | dossier `fpdb/` (~10 fichiers) en parallèle de `fpdb_3_legacy/` — à clarifier |

---

## Vague 1 — Menus déclaratifs + fondation i18n — ✅ FAIT (2026-07-12)

**Menus déclaratifs & réorganisés** (`fpdb_3_legacy/menu_layout.py`)
- Barre de menus décrite en **données** (`Menu` / `MenuItem`) au lieu de l'impératif ; construite par `createMenuBar`.
- Regroupement par intention : **File** (Préférences, Databases…, Quitter) · **Import** (bulk + auto/HUD réunis) · **Cash** · **Tournament** · **Database** (ex-Maintenance + panneau multi-backend + migration) · **Tools** · **View** (Themes en sous-menu) · **Help**.
- `refresh_themes_menu` utilise une référence stockée (plus de recherche fragile par texte).
- Libellés marqués `N_()` et rendus via `menu_layout.translate()` (utilise le `_` gettext installé).

**Fondation i18n** (`fpdb_3_legacy/i18n_compile.py`, `L10n.py`, `tools/compile_translations.py`)
- Compilateur `.po → .mo` **sans dépendance** (ni `msgfmt`, ni `babel`) + `ensure_compiled()` (recompile ce qui manque/est périmé).
- Appelé au démarrage par `L10n.set_locale_translation` → les traductions livrées chargent, sans versionner de binaire (`.mo` git-ignorés).
- Résultat : les menus se localisent (ex. `fr_FR` → « Importation en Masse », « Graphiques », « Statistiques »). 14 langues chargent.

Tests ajoutés : `test/test_menu_layout.py`, `test/test_translations.py`.

---

## Vague 2 — Internationalisation en largeur 🌍 — ✅ MARQUAGE TERMINÉ

**Fait (2026-07-12)**
- ✅ **Sélecteur de langue** : View ▸ Language (native names via `QLocale`), écrit `ui_language` dans `HUD_config.xml` (`set_general` + `save`), appliqué au redémarrage. Logique pure `menu_layout.language_options` (testée).
- ✅ **Helper i18n partagé** (`fpdb_3_legacy/i18n.py`) : `_` / `N_` avec fallback identité (test-safe).
- ✅ **Marquage `_()` de TOUS les modules GUI** : menus + `GuiDatabase`, `GuiBulkImport`, `GuiAutoImport`, `Filters`, `GuiPrefs`, `GuiGraphViewer`, `GuiSessionViewer`, `GuiTourneyPlayerStats`, `GuiOpponentsReport`, `GuiTourneyGraphViewer`, `GuiTourHandViewer`, `GuiHandViewer`, `GuiLogView`, `GuiAutoNoteRules`, `fpdb.pyw`, `GuiReplayer`, `GuiAutoNotesWorkbench`, `Aux_Hud` (popups HUD). Les 3 restants (`GuiRingPlayerStats`, `GuiStatsInfo`, `GuiConfigObserver`) n'ont **aucune chaîne UI en dur**. Patrons : module-level = `N_()` + traduction au point d'usage (`GuiPrefs.rewrite`) ; conflit `_` jetable → alias `_t` (`Aux_Hud`) ou renommage.
- ✅ **Outillage d'extraction** : `tools/update_pot.py` (xgettext, `--keyword=_ --keyword=N_`) → `locale/fpdb.pot` (git-ignoré).
- ✅ **Traductions FR** couvrant toutes les chaînes marquées + re-validations (« Configure » → « Configurer », correction d'entrées vides/espaces). **Découverte clé** : beaucoup de modules avaient des `_()` *retirés* alors que les catalogues 2011 gardaient la traduction — restaurer `_()` a réactivé des dizaines de libellés FR pour peu de nouvelles traductions.

**Reste à faire (hors dev / séparable)**
- Traduire les chaînes dans les 13 autres langues (travail traducteurs ; `.pot` prêt, workflow Weblate/Crowdin).
- Re-valider en masse les `.po` de 2011 (qualité).
- Formats localisés : nombres / devises / dates dans stats et graphes (€/$/BB selon locale — feature distincte).

**Effort restant** ~2-3j · **Impact** élevé.

---

## Vague 3 — Abstraction de dialecte SQL 🏗️ — 🟡 EN COURS

Les bugs multi-backend récents (`Rank` réservé, `boolean` vs `smallint`, `set_isolation_level(0)`, `session_replication_role`) viennent tous de variantes par backend codées en dur et éparpillées.

**Fait (2026-07-12) — étapes 1 à 3**
- ✅ `fpdb_3_legacy/dialects.py` : classe `Dialect` + `SqliteDialect`/`PostgresDialect`/`MySQLDialect` possédant les quirks — placeholder, `quote_identifier` (casse-préservée), `quote_literal`, `set_autocommit`, `list_tables`, `drop_all_tables`, `suspend/restore_foreign_keys` (PG drop+recreate sans superuser), `boolean_columns`/`coerce_row`, `reset_sequences` — + fabriques `dialect_for_backend`/`dialect_for_server`. Tests : `test/test_dialects.py`.
- ✅ `db_migrate.py` : délègue toute décision par-backend au dialecte.
- ✅ `db_backends.create_database` : quoting identifiants/littéraux (rôle/base) via le dialecte.
- ✅ `Database._pg_set_isolation` : délègue à `dialect.set_autocommit` (shim psycopg2/3 centralisé).

→ **Les 3 quirks à l'origine des bugs multi-backend (migration, création de base, isolation) sont désormais dans le dialecte.**

**Reste à faire (gros chantier séparé, optionnel)**
- Faire produire par le dialecte le quoting d'identifiants de `SQL.py` (12k lignes de requêtes par-backend en dur ; le fix `Rank`). Rendements décroissants, risque élevé.

**Impact** élevé (fiabilité du multi-backend) — atteint pour l'essentiel.

---

## Vague 4 — Domaine poker ♠️ — ✅ FAIT (2026-07-13)

**Fait (2026-07-12)**
- ✅ **Suite de tests remise au vert** : 10 échecs pré-existants (depuis l'import initial) corrigés → **3095 passed, 0 failed**. Diagnostics : mocks PokerStars périmés (`readHoleCards`/`readCommunityCards` lisent désormais `holeStreets`/`handText` — board recovery), assertion `markStreets` (`\r\n`→`\n`), garde `hudcache` (comptait `CACHE_KEYS` sans `HUDCACHE_EXTRA_KEYS` → 253 vs 257 corrects), index absolus fragiles (`isCashOut`), seuil arbitraire (200→400), fixture `tourneysummary` avec BOM UTF-16 accidentel.
- ✅ **Régression HUD positionnel corrigée** (2026-07-13) : les profils historiques sans attribut `positional_mode` avaient commencé à afficher simultanément tous les panneaux SB/BB/BU. Le comportement par défaut redevient positionnel (`current`) ; l'affichage empilé reste un choix explicite.

**Reste à faire**
- ✅ **Stats** (`Stats.py`) : alias modernes WWSF/fold-to-cbet par rue, 3bet/4bet/squeeze par position (BB, SB, BTN, CO, MP, EP), et ranges observées exactes (action / mains distribuées), avec tests de valeurs sur mains connues.
- ✅ **Parsers** (26 sites) : harnais golden étendu à 13 convertisseurs (52 fichiers / 395 mains ; identité, gametype, joueurs, board, actions, gains, pot/rake) et matrice actif/legacy documentée. PartyPoker est hermétique ; BetOnline, iPoker et SwC sont couverts depuis leur corpus public. La fixture Unibet Banzai a été restaurée avec son symbole euro réel.
- ✅ **Équité / EV** : `pypoker-eval` compilé et validé sous Python 3.13/macOS ARM, derrière `fpdb_3_legacy/equity.py` (chargement optionnel sûr, validation des cartes, boards incomplets explicitement complétés, équités normalisées `0..1`, compteurs win/tie/loss, exhaustif/Monte-Carlo et part attendue du pot). `DerivedStats` détecte l'action all-in réelle, transmet le board cumulé à cette rue et stocke `allInEV` comme profit attendu en monnaie/chips ×100. Le replayer affiche pot odds, équité et edge lorsque toutes les mains actives sont connues ; `HandDataReporter` expose la valeur brute et lisible par joueur. L'absence du moteur ou de cartes adverses reste non bloquante.

**Effort** ~1-2 sem · **Impact** moyen/élevé.

---

## Vague 5 — Dette technique longue 🧹

- ✅ **Premier ratchet Ruff** (2026-07-13) : suppression globale des 23 `F541` (f-strings sans interpolation) et des 5 `F601` (clés de dictionnaire dupliquées), avec job CI `quality` empêchant leur retour. Une duplication réelle de l'alias HUD `three_b` écrasait silencieusement l'échantillon `4.4` par `9.0`. Les modules modernisés de la Vague 4 sont vérifiés avec l'ensemble des règles Ruff actives. Dette passée de 3334 à 3306 diagnostics ; les règles seront absorbées une par une pour garder des diffs révisables.
- ✅ **Ruff complet** (2026-07-13) : dette active résorbée règle par règle, imports étoile supprimés, tests masqués restaurés et CI passée de cliquets partiels à `ruff check` sur tout le dépôt. Les exceptions historiques (`E402`, `E501` et huit modules de formatage `%` sensible) sont documentées dans `pyproject.toml`.
- ✅ **Suite Qt réactivée** (2026-07-13) : contrat des mocks remis au niveau des API actuelles (HUD multibloc, notes enrichies, changement de stat-set, `QDialog.exec()`), isolation SQLite du test Unibet et options HUD déterministes. Résultat : **343 passed, 0 failed** sur le marqueur `qt`, qui masquait notamment la régression réelle de fin d'import en masse.
- 🟡 **Typage progressif** (2026-07-13) : mypy activé en CI sur `equity.py`, le socle cartes/mains/stats dérivées/deck (`Card.py`, `Hand.py`, `DerivedStats.py`, `Deck.py`), les socles de parsing/import (`HandHistoryConverter.py`, `TourneySummary.py`, `Importer.py`, `GuiBulkImport.py`, `GuiAutoImport.py`), la chaîne principale du HUD (`HUD_main.pyw`, `Hud.py`, `Aux_Base.py`, `Aux_Hud.py`, `Aux_Classic_Hud.py`, `Mucked.py`, `BlockPopup.py`, `Popup.py`, `RangeChartPopup.py`, `Stats.py`, `SmartHudManager.py`, `TableWindow.py`, `OSXTables.py`, `WinTables.py`, `HudStatsPersistence.py`), le catalogue de requêtes `SQL.py` et le socle convertisseur iPoker avec ses 48 skins et ses résultats de tournoi, le registre typé et l'identification des convertisseurs/résumés, ainsi que tous les adaptateurs de résultats (PartyPoker/Pacific/Unibet/Winning/iPoker/PokerTracker/Merge/Winamax/PokerStars/Full Tilt/Bovada), `dialects.py`, `pt4_adapter/`, l'ensemble du domaine HTTP capture/OFC/SwC, la détection des rooms installées, les fondations menus/i18n (dont le contrat historique `L10n`), l'infrastructure DB découplée, les adaptateurs de statistiques/AutoNotes, le domaine complet des thèmes/popups modernes et les utilitaires CLI/régression (cent quarante-et-un modules), avec imports externes ignorés et corps non annotés vérifiés. Le périmètre sera élargi par domaine sans imposer immédiatement le typage aux autres god-modules.
- ✅ **God-module `Hand.py`** (2026-07-13) : état structurel des mains et du pot, reconstruction DB et fabrique explicités ; dette mypy locale ramenée de 141 à zéro sans modifier les algorithmes de calcul. Le module a rejoint le ratchet CI.
- ✅ **God-module `DerivedStats.py`** (2026-07-13) : contrats des initialiseurs, sorties joueur/main/action, positions, stove/équité et ventilation des pots explicités ; dette mypy locale ramenée de 134 à zéro sans modifier les formules statistiques. Le module a rejoint le ratchet CI.
- ✅ **God-module `Database.py`** (2026-07-13) : interfaces multi-backend, caches d'identifiants, buffers d'import et assemblages HUD/cache explicités ; dette mypy locale ramenée de 132 à zéro. L'export CSV PostgreSQL et la fusion des sessions ont également été rendus corrects, et le module rejoint le ratchet CI.
- ✅ **Socle `Configuration.py`** (2026-07-13) : chemins multi-OS, modèle XML et caches de configuration explicités ; dette mypy locale ramenée de 75 à zéro. La lecture de `default.conf` est restaurée et les réglages de compression raw-hands/raw-tourneys sont validés correctement. Le module rejoint le ratchet CI.
- ✅ **Filtres stats/HUD `Filters.py`** (2026-07-13) : contrôles Qt, sélection héros/sites et requêtes de disponibilité explicités ; dette mypy locale ramenée de 74 à zéro. Le curseur de base ne masque plus la méthode Qt homonyme et les identifiants héros acceptent correctement la relation site → alias. Le module rejoint le ratchet CI.
- ✅ **Rapports joueurs cash/tournoi** (2026-07-13) : `GuiRingPlayerStats.py` et `GuiTourneyPlayerStats.py` rejoignent le ratchet ; la vue tournoi garde les valeurs Qt explicites et protège son rafraîchissement avant création du frame.
- ✅ **Vues graphiques/session** (2026-07-13) : `GuiGraphViewer.py` et `GuiSessionViewer.py` rejoignent le ratchet ; leurs dépendances NumPy/Matplotlib optionnelles sont chargées dynamiquement, compatible avec la cible mypy Python 3.11.
- ✅ **Graphe tournoi** (2026-07-13) : `GuiTourneyGraphViewer.py` rejoint le ratchet ; les courbes ChipEV et dépendances graphiques optionnelles sont explicites.
- ✅ **Vues de mains cash/tournoi** (2026-07-13) : `GuiHandViewer.py` et `GuiTourHandViewer.py` rejoignent le ratchet ; callbacks de modèle Qt, pagination et replayer sont explicités.
- ✅ **Informations/configuration GUI** (2026-07-13) : `GuiStatsInfo.py` et `GuiConfigObserver.py` rejoignent le ratchet ; le signal de sélection Qt accepte explicitement l’élément précédent absent.
- ✅ **Journal GUI** (2026-07-13) : `GuiLogView.py` rejoint le ratchet ; modèle, layout et sélection de fichier nullable sont explicités.
- ✅ **Préférences et AutoNotes GUI** (2026-07-13) : `GuiPrefs.py`, `GuiAutoNoteRules.py` et `GuiAutoNotesWorkbench.py`, déjà sans diagnostic, rejoignent le ratchet CI.
- ✅ **Rapport opposants et base GUI** (2026-07-13) : `GuiOpponentsReport.py` et `GuiDatabase.py` rejoignent le ratchet ; le dialogue de progression de migration respecte le contrat Qt avec une action vide explicite.
- ✅ **Replayer** (2026-07-13) : état de table, showdown, boards multi-runs, cache d’équité, side pots et rendu de cartes explicités ; dette mypy locale ramenée de 41 à zéro. `GuiReplayer.py` rejoint le ratchet CI.
- ✅ **Gestionnaire de configuration** (2026-07-13) : `ConfigurationManager.py` rejoint le ratchet ; ses états de configuration absente sont contrôlés avant reload et capture d’état.
- ✅ **Point d’entrée `fpdb.pyw`** (2026-07-13) : état central Qt (configuration, DB, onglets, threads et fermeture) explicité ; API Qt modernisées et dette mypy ramenée de 104 à zéro. Le module rejoint le ratchet CI.
- ✅ **Préférences de siège HUD** (2026-07-13) : collections des sélecteurs, cartes de rooms et valeurs de configuration rendues explicites ; adaptation Qt 6 de la couleur de rendu et dette mypy ramenée de 9 à zéro. Le module rejoint le ratchet CI.
- ✅ **Widget de rechargement de configuration** (2026-07-13) : utilisation explicite de l’énumération Qt 6 pour le pixmap transparent ; le module rejoint le ratchet CI.
- ✅ **Préférences HUD modernes** (2026-07-13) : formats de profils historiques et multi-blocs, widgets de configuration, export/import XML et références de canvas explicités ; dette mypy ramenée de 22 à zéro. Le module rejoint le ratchet CI.
- ✅ **Préférences modernes par room** (2026-07-13) : cartes de room, jeux de visibilité, état des profils héros et liens site/alias explicités ; dette mypy ramenée de 7 à zéro. Le module rejoint le ratchet CI.
- ✅ **Éditeur de thèmes** (2026-07-13) : `ThemeCreatorDialog.py`, déjà sans diagnostic, rejoint le ratchet CI avec ses tests de création et prévisualisation.
- ✅ **Point d’entrée API** (2026-07-13) : `fpdb_api.py`, lanceur Uvicorn avec factory applicative, rejoint le ratchet CI.
- ✅ **Rapporteur de données de mains** (2026-07-13) : schémas de rapports par fichier/session, analyse d’échec et structures de cartes/actions explicités ; dette mypy ramenée de 41 à zéro sans modifier l’extraction. Le module rejoint le ratchet CI.
- ✅ **Détection de fuites** (2026-07-13) : le moteur de métriques, règles et recommandations d’exploitation, déjà conforme, rejoint le ratchet CI.
- ✅ **Gestionnaire d’erreurs d’import** (2026-07-13) : classification temporaire/récupérable/permanente et historique de retry, déjà conformes, rejoignent le ratchet CI.
- ✅ **Structures de tournois PokerStars** (2026-07-13) : les signatures de structure à trois ou quatre paramètres sont explicitement supportées ; dette mypy ramenée de 4 à zéro. Le module rejoint le ratchet CI.
- ✅ **Verrous inter-processus** (2026-07-13) : ressources fichiers/Win32/socket et sélection de backend explicités ; dette mypy ramenée de 17 à zéro sans modifier le contrat polymorphe historique. Le module rejoint le ratchet CI.
- ✅ **Historique XML de mains** (2026-07-13) : le modèle de parsing XML historique `HandHistory.py`, déjà conforme, rejoint le ratchet CI.
- ✅ **Convertisseur PokerStars** (2026-07-13) : contrats de regex, cartes communes, collectes et cash-outs explicités ; les ajustements monétaires restent en `Decimal`. Dette mypy ramenée de 20 à zéro et module ajouté au ratchet CI.
- ✅ **Convertisseur Winamax** (2026-07-13) : caches de joueurs, routage des métadonnées, mains/stacks/cartes et nullabilité regex explicités ; dette mypy ramenée de 8 à zéro. Le module rejoint le ratchet CI.
- ✅ **Détection de room** (2026-07-13) : `detect_site.py`, déjà conforme, rejoint le ratchet CI.
- ✅ **Convertisseur Absolute** (2026-07-13) : cache joueurs, board, bouton et cartes fermées explicités ; dette mypy ramenée de 4 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur Pacific Poker** (2026-07-13) : indicateur fast et board nullable explicités ; dette mypy ramenée de 2 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur Unibet** (2026-07-13) : cache joueurs, drapeaux de jeu, devise tournoi et itérateurs de date explicités ; dette mypy ramenée de 5 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur PKR** (2026-07-13) : cache joueurs et board nullable explicités ; dette mypy ramenée de 3 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur Everest** (2026-07-13) : état des sièges, board et bouton nullables explicités ; dette mypy ramenée de 4 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur PartyPoker** (2026-07-13) : état des mises/joueurs, cache regex, flags et identification site/devise explicités ; dette mypy ramenée de 7 à zéro. Le module rejoint le ratchet CI sans modifier le parsing des résultats de tournoi.
- ✅ **Convertisseur Cake** (2026-07-13) : données de partie/tournoi et board nullable explicités ; dette mypy ramenée de 2 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur Betfair** (2026-07-13) : cache joueurs et regex de board/blind/bouton nullables explicités ; dette mypy ramenée de 4 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur OnGame** (2026-07-13) : jeux mixtes, cache joueurs, drapeaux fast et board nullable explicités ; dette mypy ramenée de 5 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur Enet** (2026-07-14) : l'absence inattendue du board est désormais signalée comme erreur de parsing explicite ; dette mypy ramenée de 1 à zéro. Le module rejoint le ratchet CI. Le test de main PokerStars vide suit également le contrat `FpdbHandPartial` introduit par le précédent palier.
- ✅ **Convertisseur Entraction** (2026-07-14) : un board absent ou mal formé devient une main partielle explicite au lieu d'une erreur d'attribut ; dette mypy ramenée de 1 à zéro. Le module rejoint le ratchet CI.
- ✅ **Convertisseur Boss** (2026-07-14) : listes de cartes du flop et match des dernières rues sont distingués, avec erreur de parsing explicite si la carte manque ; le chemin d'échec du calcul des antes journalise le bon identifiant de main. Dette mypy agrégée ramenée de 3 à zéro. Le module et sa fixture 5 Card Draw rejoignent les ratchets CI et parser.
- ✅ **Convertisseur Everleaf** (2026-07-14) : cache joueurs typé et identifiant de main, board et bouton obligatoires validés explicitement ; dette mypy ramenée de 4 à zéro. Le module et sa fixture 7 Card Stud rejoignent les ratchets CI et parser.
- ✅ **Convertisseur Microgaming** (2026-07-14) : encodages conformes au contrat commun, table de tournoi obligatoire validée et montants de relance/all-in/blind distingués sans mélange `Decimal`/texte ; dette mypy agrégée ramenée de 4 à zéro. Le module et sa fixture PLO rejoignent les ratchets CI et parser.
- ✅ **Convertisseur KingsClub** (2026-07-14) : cache de regex joueurs et métadonnées de partie hétérogènes explicités, notamment le drapeau multi-board ; dette mypy ramenée de 3 à zéro. Le module rejoint le ratchet CI, couvert par les snapshots NLHE et 5-card PLO existants.
- ✅ **Convertisseur SealsWithClubs** (2026-07-14) : cache joueurs et registres de stacks des formats historique et moderne explicités ; un lookup de devise inexistant et immédiatement écrasé est supprimé au profit de la règle native mBTC. Dette mypy agrégée ramenée de 4 à zéro. Le module rejoint le ratchet CI, couvert par sept snapshots LHE/NLHE/PLO.
- ✅ **Convertisseur GGPoker** (2026-07-14) : contrat polymorphe Hold/Stud/Draw, cache joueurs, limite absente, métadonnées booléennes et collecte du pot explicités ; dette mypy agrégée ramenée de 17 à zéro. Le module rejoint le ratchet CI, couvert par le snapshot PLO de treize mains.
- ✅ **Convertisseur Winning** (2026-07-14) : métadonnées fast, match de table, cartes par joueur et ajustement monétaire explicités ; dette mypy ramenée de 7 à zéro. Le module rejoint le ratchet CI, couvert par son snapshot cash moderne.
- ✅ **Point d'entrée historique iPoker** (2026-07-14) : le shim `iPokerToFpdb.py` qui préserve les imports et configurations antérieurs au découpage en package rejoint explicitement le ratchet CI ; son export reste identique au convertisseur moderne déjà typé. Le registre documente aussi que ses mixins satisfont à l'exécution le contrat abstrait du convertisseur.
- ✅ **Convertisseur PokerTracker** (2026-07-14) : buffers de fichier, métadonnées multi-room, catalogue mixed games, table de tournoi et boards explicités ; un calcul monétaire mort du chemin all-in blind est supprimé. Dette mypy agrégée ramenée de 12 à zéro. Le module et une fixture Microgaming exportée rejoignent les ratchets CI et parser.
- ✅ **Convertisseur BetOnline** (2026-07-14) : validation de l'en-tête, devise nullable, variantes de rues/boards, correction des blinds et titre de table explicités ; dette mypy ramenée de 14 à zéro. Le module rejoint le ratchet CI, couvert par douze snapshots cash multi-formats.
- ✅ **Convertisseur Full Tilt** (2026-07-14) : encodages conformes au contrat commun, cache joueurs, détails de tournoi, entrée, stacks, boards et bouton explicités ; dette mypy agrégée ramenée de 34 à zéro. Le module et sa fixture Triple Draw historique rejoignent les ratchets CI et parser.
- ✅ **Convertisseur Bovada** (2026-07-14) : le doublon de traitement des boards est séparé en restauration des rues manquantes puis nettoyage du texte d'actions, avec tests dédiés Zone et standard ; contrat polymorphe Hold/Stud, partie, devise, blinds, cartes et pots explicités. Dette mypy agrégée ramenée de 44 à zéro. Le dernier convertisseur rejoint le ratchet CI.
- ✅ **Outillage CLI/maintenance** (2026-07-14) : backfills boards/showdown, résolution des chemins de cartes, CLI principale, lanceur legacy, aide de migration et synchronisation de bases, déjà conformes isolément, rejoignent ensemble le ratchet mypy CI.
- ✅ **Résumé HTML Everleaf historique** (2026-07-14) : buffer de classement texte/position explicité et parsing local des métadonnées, horaires et gains couvert sans réseau ; dette mypy ramenée de 1 à zéro. Le module rejoint le ratchet CI.
- ✅ **Notes PLO et structures Merge** (2026-07-14) : `AutoNotePlo.py` et `MergeStructures.py`, déjà conformes et couverts par les tests de notes Hwang ainsi que les chemins convertisseur/résumé Merge, rejoignent le ratchet mypy CI. La frontière du convertisseur transmet désormais explicitement un nom de tournoi texte au catalogue de structures.
- ✅ **Registre déclaratif de statistiques** (2026-07-14) : validations `name`/`inputs`/`value`/`scope`/`context` rendues visibles au type checker ; les collections non itérables lèvent désormais `StatDescriptorError` plutôt qu'un `TypeError` prématuré. Dette mypy ramenée de 4 à zéro et module ajouté au ratchet CI.
- ✅ **Importeur de statistiques PT4** (2026-07-14) : présence du descripteur traduit contrôlée directement avant fusion et rapport, alignant le type checker avec le contrat `supported` ; dette mypy ramenée de 3 à zéro. Le module rejoint le ratchet CI.
- **Découper les god-modules** : `SQL.py` (requêtes par domaine / fichiers `.sql`), `Database.py` (connexion / DDL / cache HUD / requêtes), `Stats.py` (par famille). Incrémental, avec tests de non-régression.
- **Qualité outillée** : résorber la dette `ruff` (~2900) par paliers (règle par règle, `--fix`, baseline) ; introduire **mypy/pyright** en mode progressif ; convertir les 78 `TODO/FIXME` en tâches traçables ; clarifier/supprimer le dossier `fpdb/`.

**Effort** continu · **Impact** moyen.

---

## CI / packaging (transversal)

- **CI** : matrice OS + lint + mypy + tests non-Qt sur Linux/macOS/Windows ; suite Qt complète exécutée hors-écran sous Linux ; **compilation `.mo`** dans le build (Briefcase), et embarquer `locale/**/*.mo` dans les bundles.
- **Migration DB** : tests d'intégration réels PostgreSQL/MySQL en CI (services conteneurisés) — la couverture multi-backend actuelle est mockée.

---

## Roadmap (synthèse)

| Vague | Contenu | Effort | Valeur | Statut |
|---|---|---|---|---|
| **1** | Menus déclaratifs + réorg ; fondation i18n | ~3j | Élevée | ✅ Fait |
| **2** | i18n en largeur (sélecteur, marquage, formats) | ~5j | Élevée | ✅ Marquage fini |
| **3** | Abstraction de dialecte SQL | ~4-6j | Élevée | ✅ Quirks consolidés |
| **4** | Domaine poker (stats, parsers, equity) | ~1-2 sem | Moyen/élevé | ✅ Fait |
| **5** | Dette longue (god-modules, mypy, ruff) | continu | Moyen | À faire |
