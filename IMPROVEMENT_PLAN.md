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
- 🟡 **Formats localisés** (2026-07-16) : socle central nombres/devises/dates piloté par `ui_language`, branché sur les overrides HUD, le profit total, les graphes cash/tournoi/session, les vues ring (KPI, positions, mains de départ), les historiques cash/tournoi/journaux et le rapport joueurs tournoi ; étendre progressivement aux rapports legacy restants.

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
- ✅ **Typage legacy complet** (2026-07-14) : les 244 modules `.py` de `fpdb_3_legacy` sont couverts par mypy entre le ratchet principal et le contrôle dédié aux consommateurs NumPy ; les points d'entrée `.pyw` sont vérifiés séparément. Les imports externes restent ignorés et les corps non annotés sont contrôlés, conformément au palier progressif choisi.
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
- ✅ **Importeur de HUD PT4** (2026-07-14) : valeurs du flux binaire contrôlées selon leur balise avant extraction des entiers, couleurs et mains, et nom de statistique XML rendu explicitement obligatoire ; dette mypy ramenée de 6 à zéro. Le module rejoint le ratchet CI, couvert par les tests du parseur et des grilles de ranges.
- ✅ **Scripts de diagnostic et maintenance** (2026-07-14) : diagnostics d'import et PartyPoker, lecture des retours GitHub et réparation des mains draw historiques, déjà conformes isolément, rejoignent ensemble le ratchet mypy CI sans changement de comportement.
- ✅ **Infrastructure de journalisation** (2026-07-14) : configuration persistée, éléments Qt optionnels, handlers console et flux de rotation différée explicités ; la rotation par taille ouvre désormais correctement un fichier configuré avec `delay=True`. Dette mypy ramenée de 13 à zéro, avec tests de non-régression, puis module ajouté au ratchet CI.
- ✅ **Frontière XML iPoker** (2026-07-14) : contrat du mixin explicité pour le fichier complet, les métadonnées de partie/tournoi et la source de repli du nom de fichier ; les dictionnaires XML hétérogènes conservent leurs types réels. Dette mypy ramenée de 11 à zéro et module ajouté au ratchet CI.
- ✅ **Rues et actions iPoker** (2026-07-14) : expressions régulières, constantes Stud et services hérités déclarés dans le contrat du mixin ; cartes de board et index d'actions possèdent désormais des collections typées sans réutilisation ambiguë de variable. Dette mypy ramenée de 17 à zéro et module ajouté au ratchet CI.
- ✅ **Métadonnées et joueurs iPoker** (2026-07-14) : contrat du mixin explicité pour les regex de main/date/joueur, métadonnées de partie et tournoi, sièges et services hérités ; gains, listes de joueurs et correspondances de sièges possèdent désormais des types précis. Dette mypy ramenée de 28 à zéro et module ajouté au ratchet CI.
- ✅ **Backfill des notes automatiques** (2026-07-14) : actions reconstruites depuis la base, filtres d'identifiants et compteurs extensibles de prévisualisation explicités ; les trois modes fichier brut, correspondance importée et base directe conservent leur schéma dynamique. Dette mypy ramenée de 30 à zéro et outil ajouté au ratchet CI.
- ✅ **Outillage de migration PySide6** (2026-07-14) : migrateur principal, conversion des tests et validation post-migration compilent et passent mypy ensemble ; les trois scripts rejoignent le ratchet CI sans exécuter leurs réécritures sur le dépôt.
- ✅ **Contrôleur des statistiques ring** (2026-07-14) : états dashboard/profit et lignes Qt explicités ; les diagnostics de rafraîchissement positionnel n'écrivent plus dans un chemin absolu de développement et utilisent le logger configuré. Dette mypy propre au contrôleur ramenée à zéro, avec test dédié et contrôle CI isolé des stubs NumPy externes.
- ✅ **Vue des mains de départ ring** (2026-07-14) : mode Hold'em/Omaha, statistiques de cellules et comptage des hauteurs Omaha explicités ; la grille 13×13 et sa mise à jour sur une main connue disposent désormais d'un test Qt dédié. Dette mypy ramenée de 3 à zéro et vue ajoutée au contrôle CI ring.
- ✅ **Package des statistiques ring** (2026-07-14) : filtres détaillés et filtres de cartes explicités malgré leur enrichissement dynamique par des widgets Qt ; les neuf modules du package passent désormais mypy ensemble et remplacent le contrôle CI limité aux deux premiers paliers.
- ✅ **Console de capture SWC** (2026-07-14) : orientations, alignements, rôles de données et graisses de police migrés vers les enums PySide6 ; sortie de processus optionnelle, lecture JSON et états successifs du replayer explicités. Dette mypy ramenée de 35 à zéro, avec tests du catalogue de jeux, puis module ajouté au ratchet CI.
- ✅ **Diagnostics legacy exécutables** (2026-07-14) : client de test API corrigé pour son jeton optionnel et ses en-têtes HTTP typés, accompagné des diagnostics draw, Full Tilt, fuites, rapports adversaires, PartyPoker, profils et run-it-twice. Le contrôle agrégé explicite aussi la classe de main polymorphe PartyPoker et accepte toute séquence numérique pour les percentiles adversaires. Les huit scripts compilent et rejoignent le ratchet CI ; dette API ramenée de 4 à zéro sans appel réseau.
- ✅ **Régressions GUI sans données** (2026-07-14) : la fixture d'export HUD vérifie explicitement la présence de la racine XML avant d'inspecter stat-set, popups et layout-set ; dette mypy ramenée de 4 à zéro et diagnostic Qt ajouté au ratchet CI.
- ✅ **Validateurs de migration avec NumPy** (2026-07-14) : validation fonctionnelle 1.1, tests de migration et audit post-migration compilent et passent mypy avec le package `ring_stats` dans un contrôle CI dédié aux consommateurs NumPy ; les trois scripts rejoignent le ratchet sans être bloqués localement par les stubs NumPy récents incompatibles avec la cible mypy Python 3.11.
- ✅ **Ratchet mypy legacy complet** (2026-07-14) : le dernier fichier restant, `fpdb_3_legacy/__init__.py`, rejoint la CI. Les 244 modules `.py` du package legacy sont désormais couverts entre le contrôle principal et le contrôle dédié aux consommateurs NumPy ; les points d'entrée `.pyw` restent vérifiés séparément.
- ✅ **Premier découpage de `Stats.py`** (2026-07-14) : formatage des décimales, sentinelle « sans données » et pose des tooltips extraits dans `stats_formatting.py` avec contrat minimal de widget. `Stats.py` réexporte les trois symboles historiques, préservant HUD, plugins et patches existants ; 548 tests ciblés passent.
- ✅ **Contexte de main de `Stats.py`** (2026-07-14) : stockage thread-local extrait dans `stats_context.py` avec accesseurs typés ; les alias privés historiques restent disponibles dans `Stats.py`, y compris pour les patches de tests. Les stats de stack, tournoi et blocs dépendantes de la main courante restent couvertes par 514 tests ciblés.
- ✅ **Statistiques de table de `Stats.py`** (2026-07-14) : `live_min_stack_bb`, son dispatcher et son registre extraits dans `stats_table.py`. Fonctions publiques et registre privé historique restent réexportés depuis `Stats.py`, notamment pour la validation PT4 ; 506 tests ciblés passent.
- ✅ **3-bets postflop de `Stats.py`** (2026-07-14) : calcul done/opportunity et six statistiques 3-bet/fold-to-3-bet par rue extraits dans `stats_postflop.py`. Les fonctions restent présentes dans l'espace global de `Stats.py` pour le dispatcher `STATLIST`, tandis que les autres fréquences par rue réutilisent le helper extrait ; 494 tests ciblés passent.
- ✅ **Fréquences postflop de `Stats.py`** (2026-07-14) : 4-bet flop/turn/river, ouverture des trois rues et floats turn/river déplacés dans `stats_postflop.py`, en conservant leurs noms globaux historiques dans `Stats.py`. Les calculs partagent désormais le ratio typé extrait ; 508 tests ciblés passent.
- ✅ **Réponses aux relances postflop de `Stats.py`** (2026-07-14) : face-raise par rue, première relance flop/turn/river, folds par rue et fold-to-squeeze déplacés dans `stats_postflop.py`. Les 11 fonctions restent réexportées sous leurs noms historiques pour le HUD et le dispatcher dynamique.
- ✅ **Fréquences préflop modernes de `Stats.py`** (2026-07-14) : moyenne de limpers rencontrés, straddle, segmentation GP open normal/shove/limp et fold face à all-in extraits dans `stats_preflop.py`, typés et ajoutés au ratchet mypy de la CI.
- ✅ **Montants et SPR de `Stats.py`** (2026-07-14) : six montants moyens investis et les SPR flop/turn/river extraits dans `stats_sizing.py`, avec leurs deux helpers typés et leurs exports historiques préservés.
- ✅ **Tailles de mises de `Stats.py`** (2026-07-14) : tailles moyennes des mises affrontées flop/turn/river, des 2/3/4-bets affrontés préflop et des mises produites postflop déplacées dans `stats_sizing.py`. Le helper en points de base est typé et réexporté pour les familles restantes.
- ✅ **Tailles de relances génériques de `Stats.py`** (2026-07-14) : relances produites et relances affrontées préflop/flop/turn/river déplacées dans `stats_sizing.py`, avec conservation des huit entrées publiques du catalogue HUD.
- ✅ **Matrice des relances affrontées de `Stats.py`** (2026-07-14) : tailles des 2/3/4-bets affrontés au flop, turn et river extraites dans `stats_sizing.py`, en conservant les neuf noms et formats historiques.
- ✅ **Complément sizing de `Stats.py`** (2026-07-14) : secondes relances produites sur les quatre rues et 5-bet préflop affronté déplacés dans `stats_sizing.py`. Le bloc moderne de tailles de mises est désormais entièrement séparé du catalogue monolithique.
- ✅ **HUD préflop positionnel de `Stats.py`** (2026-07-14) : 3-bet, 4-bet et squeeze dans les six buckets BB/SB/BTN/CO/MP/EP déplacés dans `stats_preflop.py`, avec helper typé et 18 exports historiques conservés.
- ✅ **Ranges préflop observées de `Stats.py`** (2026-07-14) : ranges de 3-bet, 4-bet et squeeze déplacées dans `stats_preflop.py`, avec le helper de fréquence sur toutes les mains distribué typé et réexporté.
- ✅ **Fréquences postflop agrégées de `Stats.py`** (2026-07-14) : fréquence de check-raise toutes rues et efficacité des calls river déplacées dans `stats_postflop.py`, avec formats historiques et cas sans opportunité conservés.
- ✅ **RFI total et positionnel de `Stats.py`** (2026-07-14) : estimation RFI totale et agrégats early/middle/late déplacés dans `stats_preflop.py`, avec helper positionnel typé et contrats popup/HUD préservés.
- ✅ **Sizing agrégé de fin de catalogue** (2026-07-14) : trois marqueurs de taille moyenne dépréciés et l'estimation historique d'overbet déplacés dans `stats_sizing.py`. La nature estimée/non disponible de ces valeurs reste explicitement documentée.
- ✅ **Marqueurs préflop dépréciés de `Stats.py`** (2026-07-14) : isolation raise, 3-bet vs steal et call vs steal déplacés dans `stats_preflop.py`. Ils restent compatibles avec les anciennes configurations sans inventer de données absentes du HudCache.
- ✅ **Entrées passives préflop de `Stats.py`** (2026-07-14) : cold call, limp estimé et open limp déplacés dans `stats_preflop.py`, avec dénominateurs, sentinelles sans opportunité et libellés historiques conservés.
- ✅ **Indicateurs préflop dérivés de `Stats.py`** (2026-07-14) : ratio VPIP/PFR et fold face à 4-bet déplacés dans `stats_preflop.py`, y compris ratio infini à PFR nul et sentinelles historiques.
- ✅ **Fréquences de mise directes de `Stats.py`** (2026-07-14) : fréquences de bet flop et turn déplacées dans `stats_postflop.py`, avec un helper typé qui distingue libellé court HUD et libellé long popup.
- ✅ **Fréquences de relance directes de `Stats.py`** (2026-07-14) : fréquences de raise flop et turn déplacées dans `stats_postflop.py`, en réutilisant le helper typé des actions directes par rue.
- ✅ **Winrates showdown de `Stats.py`** (2026-07-14) : winrate au showdown et dérivation historique hors showdown déplacés dans `stats_postflop.py`, avec formule et formats HUD historiques conservés.
- ✅ **Estimations float/probe de `Stats.py`** (2026-07-14) : `float_bet` turn et `probe_bet` flop déplacés dans `stats_postflop.py`. Leur reconstruction historique depuis des compteurs agrégés est désormais explicitement isolée et documentée.
- ✅ **Cellules de présentation de `Stats.py`** (2026-07-14) : cellule vide et icône de note joueur déplacées dans `stats_display.py`, séparant les entrées HUD non numériques des calculs poker et les ajoutant au ratchet mypy.
- ✅ **Abréviation de variante de `Stats.py`** (2026-07-14) : table des variantes/limites et rendu `game_abbr` déplacés dans `stats_display.py`, avec lecture explicite du contexte de main et fallback historique `Unknown`.
- ✅ **Triple barrel de `Stats.py`** (2026-07-14) : estimation par produit des taux de c-bet flop/turn/river déplacée dans `stats_postflop.py`, avec nature dérivée et format historique conservés.
- ✅ **Resteal estimé de `Stats.py`** (2026-07-14) : estimation historique issue des compteurs de 3-bet déplacée dans `stats_preflop.py`, avec coefficients 60 %/70 % explicitement confinés au module préflop.
- ✅ **Probe turn/river de `Stats.py`** (2026-07-14) : estimations probe turn et river déplacées dans `stats_postflop.py` derrière un helper typé par rue, avec sentinelles et libellés historiques conservés.
- ✅ **C-bet IP/OOP de `Stats.py`** (2026-07-14) : estimations flop en position et hors position déplacées dans `stats_postflop.py` derrière un helper typé, avec pondération historique par mains en position conservée.
- ✅ **Fold-to-cbet de `Stats.py`** (2026-07-14) : `f_cb1…4` et alias modernes flop/turn/river déplacés dans `stats_postflop.py`, remplaçant quatre implémentations répétées par un helper typé par rue.
- ✅ **Check-raise par rue de `Stats.py`** (2026-07-14) : `cr1…4` déplacés dans `stats_postflop.py`, remplaçant quatre implémentations répétées par un helper typé et conservant les contrats flop/turn/river/7th street.
- ✅ **Fréquences de fold par rue de `Stats.py`** (2026-07-14) : `ffreq1…4` déplacés dans `stats_postflop.py`, avec helper typé commun et distinction historique entre aucune opportunité et données invalides.
- ✅ **Continuation bets par rue de `Stats.py`** (2026-07-15) : `cb1…4` déplacés dans `stats_postflop.py` et raccordés au helper typé d'action directe, avec libellés Hold'em/Stud historiques conservés.
- ✅ **Continuation bet agrégé de `Stats.py`** (2026-07-15) : `cbet` toutes rues déplacé dans `stats_postflop.py`, avec somme typée des compteurs 1 à 4 et contrat d'erreur historique conservé.
- ✅ **Fréquences d'agression par rue de `Stats.py`** (2026-07-15) : `a_freq1…4` déplacés dans `stats_postflop.py`, avec helper typé commun et particularité historique `saw_f` au flop conservée.
- ✅ **Agression postflop agrégée de `Stats.py`** (2026-07-15) : `a_freq_123`, `agg_fact` et `agg_fact_pct` déplacés dans `stats_postflop.py`, avec agrégation typée commune des actions et conventions numériques historiques conservées.
- ✅ **Won when saw flop de `Stats.py`** (2026-07-15) : `WMsF` et son alias moderne `wwsf` déplacés dans `stats_postflop.py`, avec sentinelle sans flop et dénominateurs historiques conservés.
- ✅ **Réponses préflop de `Stats.py`** (2026-07-15) : `car0`, `f_3bet` et `f_4bet` déplacés dans `stats_preflop.py` derrière un helper typé commun, avec distinction historique entre zéro opportunité et compteur absent conservée.
- ✅ **Squeeze et raise-to-steal de `Stats.py`** (2026-07-15) : `squeeze` et `raiseToSteal` déplacés dans `stats_preflop.py` derrière un helper typé commun, avec leurs sentinelles historiques sans opportunité conservées.
- ✅ **Donk-bet-and-raise par rue de `Stats.py`** (2026-07-15) : `dbr1…3` et `f_dbr1…3` déplacés dans `stats_postflop.py` derrière un helper de compteurs ajustés, avec les contrats historiques distincts de zéro et d'erreur conservés.
- ✅ **3-bet et 4-bet préflop de `Stats.py`** (2026-07-15) : `three_B`, `four_B` et `cfour_B` déplacés dans `stats_preflop.py` en réutilisant le helper typé action/opportunité et leurs libellés HUD historiques.
- ✅ **Dérivées 4-bet-range/call-3-bet de `Stats.py`** (2026-07-15) : `fbr` et `ctb` déplacés dans `stats_preflop.py`, avec leurs formules composées et compteurs d'affichage historiques conservés.
- ✅ **Fold-to-steal des blindes de `Stats.py`** (2026-07-15) : `f_SB_steal`, `f_BB_steal` et `f_steal` déplacés dans `stats_preflop.py`, avec calculs individuels et agrégés ainsi que sentinelles historiques conservés.
- ✅ **Tentative et réussite de steal de `Stats.py`** (2026-07-15) : `steal` et `s_steal` déplacés dans `stats_preflop.py` derrière un helper typé qui préserve leurs libellés distincts de valeur et d'absence de données.
- ✅ **VPIP et PFR de `Stats.py`** (2026-07-15) : les deux fréquences préflop fondamentales déplacées dans `stats_preflop.py`, en généralisant le helper typé à libellés HUD et sans-données distincts.
- ✅ **Showdown et saw-flop fondamentaux de `Stats.py`** (2026-07-15) : `wtsd`, `wmsd` et `saw_f` déplacés dans `stats_postflop.py`, avec formats, sentinelles et comportement historique sur division par zéro conservés.
- ✅ **Rendements financiers de `Stats.py`** (2026-07-15) : `profit100`, `bbper100` et `BBper100` déplacés dans le nouveau module typé `stats_financial.py`, ajouté au ratchet CI avec unités et diagnostics historiques conservés.
- ✅ **Nombre de mains de `Stats.py`** (2026-07-15) : `n` déplacé dans `stats_display.py`, avec notation compacte historique `X.Yk`, arrondi de retenue et repli à zéro conservés.
- ✅ **Identité joueur de `Stats.py`** (2026-07-15) : `playername`, `playershort` et `playerprofile` déplacés dans `stats_display.py`, avec troncature historique, repli optionnel et chargement différé du profileur conservés.
- ✅ **Profit total de `Stats.py`** (2026-07-15) : `totalprofit` rejoint `stats_financial.py`, avec conversion historique depuis les centimes, valeur interne et tuple de repli conservés.
- ✅ **Piles tournoi de `Stats.py`** (2026-07-15) : reconstruction de pile finale, `m_ratio` et `bbstack` déplacés dans le nouveau module typé `stats_tournament.py`, ajouté au ratchet CI avec retours historiques conservés.
- ✅ **Popup des mains de départ de `Stats.py`** (2026-07-15) : `starthands`, sa requête limitée au fichier courant et son formatage positionnel déplacés dans `stats_display.py`, clôturant l'extraction des fonctions statistiques métier du catalogue central.
- **Découper les god-modules** : ✅ `Stats.py` est désormais une façade de compatibilité dont les fonctions métier sont réparties par famille et l'architecture protégée par un test ; restent `SQL.py` (requêtes par domaine / fichiers `.sql`) et `Database.py` (connexion / DDL / cache HUD / requêtes). Incrémental, avec tests de non-régression.
- ✅ **Métadonnées de `SQL.py`** (2026-07-15) : introspection tables/index, transaction et sélections de référence extraites dans `sql_metadata.py`, avec catalogue multi-backend typé et tests d'installation exacte dans `Sql.query`.
- ✅ **Schéma cœur de `SQL.py`** (2026-07-15) : DDL `Settings` et verrou `InsertLock` extraits dans `sql_schema_core.py`, avec variantes exactes par backend et verrou MySQL-only explicitement testé.
- ✅ **Archives brutes de `SQL.py`** (2026-07-15) : DDL jumeaux `RawHands`/`RawTourneys` extraits dans `sql_schema_raw.py`, générés par un helper backend commun et protégés par des tests d'équivalence structurelle.
- ✅ **Lookups Actions/Rank de `SQL.py`** (2026-07-15) : DDL des tables de référence extraits dans `sql_schema_lookup.py`, avec identités backend spécifiques et cas PostgreSQL du nom `Rank` protégés par régression exacte.
- ✅ **Lookups StartCards/Sites de `SQL.py`** (2026-07-15) : DDL des cartes de départ et rooms regroupés dans `sql_schema_lookup.py`, avec chaînes historiques et identités propres aux trois backends conservées.
- ✅ **Backings de `SQL.py`** (2026-07-15) : démarrage du domaine tournoi dans `sql_schema_tournament.py`, avec clés étrangères, types numériques et différences SQLite protégés par des tests multi-backend.
- ✅ **Gametypes de `SQL.py`** (2026-07-15) : DDL des définitions de jeu extrait dans `sql_schema_game.py`, avec types de sièges, booléens et cascade SQLite protégés par régression multi-backend.
- ✅ **Players de `SQL.py`** (2026-07-15) : DDL des identités joueur extrait dans `sql_schema_player.py`, avec séquences PostgreSQL, références Sites et cascade SQLite explicitement protégées.
- ✅ **Autorates de `SQL.py`** (2026-07-15) : DDL des évaluations automatiques regroupé avec le domaine joueur, avec relations Players/Gametypes et absence historique de contraintes SQLite testées.
- ✅ **Boards de `SQL.py`** (2026-07-15) : démarrage du domaine main dans `sql_schema_hand.py`, avec encodage des cartes, identités 64 bits et relation Hands protégés sur chaque backend.
- ✅ **Tourneys de `SQL.py`** (2026-07-15) : DDL des tournois regroupé dans `sql_schema_tournament.py`, avec références TourneyTypes/Sessions et représentations temporelles multi-backend conservées.
- ✅ **TourneyTypes de `SQL.py`** (2026-07-15) : catalogue complet des formats tournoi déplacé dans `sql_schema_tournament.py`, avec montants 64 bits, options modernes et relation Sites préservés.
- ✅ **HandsCashout de `SQL.py`** (2026-07-15) : DDL des cashouts EV déplacé dans `sql_schema_hand.py`, avec montants décimaux et relations Hands/Players conservés sur les backends concernés.
- ✅ **HandsShowdown de `SQL.py`** (2026-07-15) : DDL des combinaisons d'abattage déplacé dans `sql_schema_hand.py`, avec tailles des textes et relations Hands/Players protégées par backend.
- ✅ **HandsStove de `SQL.py`** (2026-07-15) : DDL des résultats d'équité déplacé dans `sql_schema_hand.py`, avec valeurs décimales et références Rank spécifiques à MySQL/PostgreSQL conservées.
- ✅ **HandsActions de `SQL.py`** (2026-07-15) : DDL des actions de main déplacé dans `sql_schema_hand.py`, avec montants 64 bits, cartes défaussées et références Actions préservés.
- ✅ **PlayerAutoNotes de `SQL.py`** (2026-07-15) : DDL des notes générées regroupé dans `sql_schema_player.py`, avec unicité règle/main/joueur et horodatages multi-backend conservés.
- ✅ **HandsPots de `SQL.py`** (2026-07-15) : DDL des pots distribués déplacé dans `sql_schema_hand.py`, avec montants, boards hi/lo et relations Hands/Players conservés.
- ✅ **Files de `SQL.py`** (2026-07-15) : démarrage du domaine import dans `sql_schema_import.py`, avec suivi des compteurs, horodatages et états de fichier protégé sur les trois backends.
- ✅ **Weeks/Months de `SQL.py`** (2026-07-15) : DDL des périodes calendaires extrait dans `sql_schema_time.py` et généré par un helper commun conservant identités et timestamps multi-backend.
- ✅ **Sessions de `SQL.py`** (2026-07-15) : DDL des sessions déplacé dans `sql_schema_time.py`, avec bornes temporelles et relations Weeks/Months conservées sur les backends concernés.
- ✅ **TourneysPlayers de `SQL.py`** (2026-07-15) : DDL des résultats joueur/tournoi déplacé dans `sql_schema_tournament.py`, avec gains, KO, rebuys/add-ons et relations conservés.
- ✅ **Hands de `SQL.py`** (2026-07-15) : table racine des mains extraite mécaniquement dans `sql_schema_hand_root.py`, avec boards, pots, compteurs de rues et références multi-backend conservés à l'identique.
- ✅ **HandsPlayers de `SQL.py`** (2026-07-15) : plus grand DDL métier extrait mécaniquement dans `sql_schema_hand_player.py`, avec colonnes HUD/positionnelles, cartes, équité et relations tournoi conservées à l'identique.
- ✅ **PositionsCache de `SQL.py`** (2026-07-15) : cache HUD positionnel extrait mécaniquement dans `sql_schema_position_cache.py`, avec clés de contexte et compteurs statistiques conservés à l'identique.
- ✅ **SessionsCache de `SQL.py`** (2026-07-15) : agrégats statistiques par session extraits mécaniquement dans `sql_schema_session_cache.py`, avec contexte, résultats financiers et compteurs conservés à l'identique.
- ✅ **TourneysCache de `SQL.py`** (2026-07-15) : agrégats statistiques par tournoi extraits mécaniquement dans `sql_schema_tournament_cache.py`, avec contexte session/tournoi et résultats financiers conservés à l'identique.
- ✅ **HudCache/CardsCache de `SQL.py`** (2026-07-15) : caches HUD principal et par cartes de départ extraits mécaniquement, avec clés positionnelles, périodes et colonnes delayed-cbet/probe turn protégées explicitement.
- ✅ **DDL de `SQL.py` entièrement extrait** (2026-07-15) : plus aucun `CREATE TABLE` ne demeure dans la façade ; une garde architecturale impose désormais l'installation exclusive des catalogues de schéma dédiés.
- ✅ **Index structurels de `SQL.py`** (2026-07-15) : les 30 index et migrations de colonnes indexées sont regroupés dans `sql_indexes.py`, avec syntaxes MySQL/PostgreSQL/SQLite testées exactement.
- ✅ **Lookups cœur de `SQL.py`** (2026-07-15) : bornes temporelles, résolution joueur et informations de partie déplacées dans `sql_queries_core.py`, avec paramètres et jointures protégés.
- ✅ **Détail d'une main de `SQL.py`** (2026-07-15) : joueurs, gagnants, table, sièges et cartes déplacés dans `sql_queries_hand_detail.py`, avec reconstruction draw et placeholders SQLite protégés.
- ✅ **Fenêtres d'historique de `SQL.py`** (2026-07-15) : bornes une journée/N mains déplacées dans `sql_queries_history.py`, avec fonctions de dates et placeholders propres aux trois backends conservés.
- ✅ **Filtres de rapports de `SQL.py`** (2026-07-15) : catégories, positions, devises et limites déplacées dans `sql_queries_filters.py`, avec contraintes room/joueur et placeholders multi-backend protégés.
- ✅ **Rapport adversaires de `SQL.py`** (2026-07-15) : agrégation head-to-head déplacée dans `sql_queries_opponents.py`, avec indicateurs HUD, filtres dynamiques et fonctions temporelles multi-backend conservés.
- ✅ **Rapport cash détaillé de `SQL.py`** (2026-07-15) : `playerDetailedStats` extrait mécaniquement dans `sql_queries_player_detailed.py`, avec positions, agrégats et filtres dynamiques multi-backend conservés.
- ✅ **Rapport tournoi détaillé de `SQL.py`** (2026-07-15) : `tourneyPlayerDetailedStats` extrait dans `sql_queries_tournament_player.py`, avec buy-ins, gains, KO, classements et filtres conservés.
- ✅ **Statistiques joueur agrégées de `SQL.py`** (2026-07-15) : `playerStats` extrait dans `sql_queries_player_stats.py`, avec fréquences, profits, filtres dynamiques et formats numériques multi-backend conservés.
- ✅ **Statistiques joueur par position de `SQL.py`** (2026-07-15) : `playerStatsByPosition` extrait dans `sql_queries_player_position.py`, avec regroupements HUD positionnels, profits et filtres conservés.
- ✅ **Courbes de profit cash de `SQL.py`** (2026-07-15) : requêtes en unités natives, big blinds et dollars déplacées dans `sql_queries_cash_profit.py`, avec all-in EV et filtres temporels conservés.
- ✅ **Graphes tournoi de `SQL.py`** (2026-07-15) : résultats, courbes par type et requêtes ChipEV positionnelles déplacés dans `sql_queries_tournament_graph.py`, avec placeholders de visualisation conservés.
- ✅ **Chronologie des sessions de `SQL.py`** (2026-07-15) : `sessionStats` extrait dans `sql_queries_session_stats.py`, avec conversions epoch/strftime et filtres cash multi-backend conservés.
- ✅ **Navigation/replayer de `SQL.py`** (2026-07-15) : plages de mains, session, boards, joueurs et actions déplacés dans `sql_queries_replayer.py`, avec ordre des actions et placeholders SQLite protégés.
- ✅ **Maintenance des caches HUD de `SQL.py`** (2026-07-15) : vidages, contextes tournoi manquants et périodes week/month déplacés dans `sql_queries_cache_maintenance.py`, avec placeholders SQLite protégés.
- ✅ **Reconstruction des caches HUD de `SQL.py`** (2026-07-15) : `rebuildCache` extrait mécaniquement dans `sql_queries_cache_rebuild.py`, avec agrégats statistiques et placeholders de composition conservés.
- ✅ **Écritures HudCache de `SQL.py`** (2026-07-15) : insert/update, lookups ring/tournoi et borne hero déplacés dans `sql_queries_hud_cache_write.py`, avec position et extensions turn protégées.
- ✅ **Écritures CardsCache de `SQL.py`** (2026-07-15) : insert/update et lookups ring/tournoi déplacés dans `sql_queries_cards_cache_write.py`, avec cartes de départ et ordre des paramètres protégés.
- ✅ **Écritures PositionsCache de `SQL.py`** (2026-07-15) : insert/update et lookups ring/tournoi déplacés dans `sql_queries_positions_cache_write.py`, avec sièges, position maximale et position courante protégés.
- ✅ **Maintenance SessionsCache/TourneysCache de `SQL.py`** (2026-07-15) : 34 requêtes de nettoyage, sélection, insertion, agrégation et rattachement déplacées dans `sql_queries_session_cache_write.py`, avec liens session et agrégats financiers protégés.
- ✅ **Administration DB de `SQL.py`** (2026-07-15) : commandes analyze/vacuum et verrous d'import déplacés dans `sql_queries_database_admin.py`, avec contrats MySQL/PostgreSQL/SQLite protégés.
- ✅ **Types de parties et tournois de `SQL.py`** (2026-07-15) : lookups, insertions et remappage `Gametypes`/`TourneyTypes` déplacés dans `sql_queries_game_types.py`, avec variantes SQLite/PostgreSQL/MySQL et dimensions modernes protégées.
- ✅ **Persistance des tournois de `SQL.py`** (2026-07-16) : lectures et écritures `Tourneys`/`TourneysPlayers`, résultats, bounties et réparation des références `HandsPlayers` déplacés dans `sql_queries_tournament_persistence.py`.
- ✅ **Artefacts de mains de `SQL.py`** (2026-07-16) : actions, stove/EV, showdown et cashout déplacés dans `sql_queries_hand_artifacts.py`, avec ordre des colonnes et placeholders multi-backend protégés.
- ✅ **Notes automatiques joueur de `SQL.py`** (2026-07-16) : écritures, recherches et agrégats `PlayerAutoNotes` déplacés dans `sql_queries_player_auto_notes.py`, avec identité règle/version et crochet de filtres dynamiques protégés.
- ✅ **Écritures auxiliaires d'import de `SQL.py`** (2026-07-16) : boards multi-run, pots et suivi des fichiers déplacés dans `sql_queries_import_auxiliary.py`, avec dimensions et compteurs d'import protégés.
- ✅ **Insertion racine des mains de `SQL.py`** (2026-07-16) : `store_hand` déplacé dans `sql_queries_hand_root_persistence.py`, avec alignement des 36 colonnes/paramètres, boards, pots par rue et bomb-pot protégés.
- ✅ **Insertion `HandsPlayers` de `SQL.py`** (2026-07-16) : l'insert pleine largeur déplacé dans `sql_queries_hand_player_persistence.py`, avec alignement `HANDS_PLAYERS_KEYS`, insert SQLite réel et colonnes EV/delayed-cbet/probe/cashout protégés.
- ✅ **Utilitaires de `SQL.py`** (2026-07-16) : commentaires/noms joueurs, compteurs DB et catalogue de dump déplacés dans `sql_queries_utility.py`, avec les 21 clés et placeholders multi-backend protégés.
- ✅ **HUD de la main courante de `SQL.py`** (2026-07-16) : `get_stats_from_hand` déplacé dans `sql_queries_hud_current_stats.py`, avec jointures joueur/gametype, borne `styleKey` et alias HUD principaux protégés.
- ✅ **HUD agrégé par niveaux de `SQL.py`** (2026-07-16) : `get_stats_from_hand_aggregated` déplacé dans `sql_queries_hud_aggregated_stats.py`, avec siège courant, bandes de blindes et scopes héros/adversaires protégés.
- ✅ **HUD de session de `SQL.py`** (2026-07-16) : variantes MySQL/PostgreSQL/SQLite de `get_stats_from_hand_session` déplacées dans `sql_queries_hud_session_stats.py`, avec casts, ordre des champs, table courante et scopes de sièges protégés.
- ✅ **Façade `SQL.py` sans SQL inline** (2026-07-16) : normalisation finale des placeholders déplacée dans `sql_query_placeholders.py`, commentaires orphelins supprimés et garde architecturale renforcée pour interdire tout retour de requête inline.
- ✅ **Chaînes multilignes des requêtes extraites** (2026-07-16) : les 27 chaînes SQL aplaties contenant des échappements `\\n` ont été réécrites en vrais littéraux multilignes lisibles, à valeur d'exécution identique ; les sources extraites et les catalogues finaux SQLite/PostgreSQL/MySQL sont protégés par régression.
- ✅ **Dossier moderne `fpdb/` clarifié** (2026-07-16) : package conservé pour l'abstraction active des fenêtres HUD multi-OS, frontière documentée, API `Platform` exportée, factory/singleton/géométrie testés et package complet ajouté au ratchet mypy.
- ✅ **Traductions compilées dans les builds** (2026-07-16) : CI et PyInstaller compilent tous les catalogues `.po`; Briefcase fusionne une source générée `.briefcase-resources/locale` qui conserve l'arborescence gettext, validée par chargement réel de `.mo`.
- ✅ **Dette source traçable** (2026-07-16) : les 73 `TODO/FIXME/HACK` sont inventoriés dans `TECHNICAL_DEBT.md`, avec identifiants stables, catégories et liens source ; la CI interdit que le registre diverge du code.
- ✅ **Second checker évalué et adopté** (2026-07-16) : Pyright contrôle en mode `basic` le package moderne et les outils typés, en complément de mypy ; seuls les imports natifs optionnels propres à chaque OS sont ignorés.
- **Qualité outillée restante** : Ruff, mypy et le ratchet Pyright sont verts ; traiter progressivement le registre de dette et élargir Pyright lorsque les annotations gagnent de nouveaux domaines.

**Effort** continu · **Impact** moyen.

---

## CI / packaging (transversal)

- **CI** : matrice OS + lint + mypy + tests non-Qt sur Linux/macOS/Windows ; suite Qt complète exécutée hors-écran sous Linux ; **compilation `.mo`** dans le build (Briefcase), et embarquer `locale/**/*.mo` dans les bundles.
- ✅ **Schémas DB réels en CI** (2026-07-16) : services PostgreSQL 16 et MySQL 8.4, exécution du catalogue DDL complet et vérification d'une contrainte étrangère réelle sur chaque backend ; le test a immédiatement corrigé la création MySQL de la table réservée `Rank`.
- **Migration DB** : étendre ces services aux migrations de données aller-retour ; la création du schéma n'est plus simulée.

---

## Roadmap (synthèse)

| Vague | Contenu | Effort | Valeur | Statut |
|---|---|---|---|---|
| **1** | Menus déclaratifs + réorg ; fondation i18n | ~3j | Élevée | ✅ Fait |
| **2** | i18n en largeur (sélecteur, marquage, formats) | ~5j | Élevée | ✅ Marquage fini |
| **3** | Abstraction de dialecte SQL | ~4-6j | Élevée | ✅ Quirks consolidés |
| **4** | Domaine poker (stats, parsers, equity) | ~1-2 sem | Moyen/élevé | ✅ Fait |
| **5** | Dette longue (god-modules, mypy, ruff) | continu | Moyen | À faire |
