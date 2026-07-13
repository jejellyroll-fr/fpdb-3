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
- Traduire les chaînes dans les 13 autres langues (travail traducteurs ; `.pot` prêt).
- Re-valider en masse les `.po` de 2011 (qualité).
- Formats localisés : nombres / devises / dates dans stats et graphes (feature distincte).
- Traduire les nouvelles chaînes dans les 13 autres langues (travail traducteurs ; workflow Weblate/Crowdin).
- Re-valider en masse les `.po` de 2011.
- Formats localisés : nombres / devises / dates dans stats et graphes (€/$/BB selon locale).

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

## Vague 4 — Domaine poker ♠️ — 🟡 EN COURS

**Fait (2026-07-12)**
- ✅ **Suite de tests remise au vert** : 10 échecs pré-existants (depuis l'import initial) corrigés → **3095 passed, 0 failed**. Diagnostics : mocks PokerStars périmés (`readHoleCards`/`readCommunityCards` lisent désormais `holeStreets`/`handText` — board recovery), assertion `markStreets` (`\r\n`→`\n`), garde `hudcache` (comptait `CACHE_KEYS` sans `HUDCACHE_EXTRA_KEYS` → 253 vs 257 corrects), index absolus fragiles (`isCashOut`), seuil arbitraire (200→400), fixture `tourneysummary` avec BOM UTF-16 accidentel.

**Reste à faire**
- **Stats** (`Stats.py`) : compléter les stats modernes / par rue (3bet/4bet/squeeze par position, fold-to-cbet turn/river, WWSF, WTSD, ranges) + **tests de valeurs** sur mains connues.
- **Parsers** (26 sites) : harnais de **tests de régression par fichier de main** (fixtures) pour détecter les dérives de format ; prioriser les formats vivants (GGPoker, PokerStars, Winamax), marquer *legacy* les sites morts.
- **Équité / ranges** : intégrer proprement `pypoker-eval/` (dépendance optionnelle) pour equity/EV dans le replayer et les rapports.

**Effort** ~1-2 sem · **Impact** moyen/élevé.

---

## Vague 5 — Dette technique longue 🧹

- **Découper les god-modules** : `SQL.py` (requêtes par domaine / fichiers `.sql`), `Database.py` (connexion / DDL / cache HUD / requêtes), `Stats.py` (par famille). Incrémental, avec tests de non-régression.
- **Qualité outillée** : résorber la dette `ruff` (~2900) par paliers (règle par règle, `--fix`, baseline) ; introduire **mypy/pyright** en mode progressif ; convertir les 78 `TODO/FIXME` en tâches traçables ; clarifier/supprimer le dossier `fpdb/`.

**Effort** continu · **Impact** moyen.

---

## CI / packaging (transversal)

- **CI** : matrice OS (cf. correctifs Windows récents) + lint + mypy + tests + **compilation `.mo`** dans le build (Briefcase), et embarquer `locale/**/*.mo` dans les bundles.
- **Migration DB** : tests d'intégration réels PostgreSQL/MySQL en CI (services conteneurisés) — la couverture multi-backend actuelle est mockée.

---

## Roadmap (synthèse)

| Vague | Contenu | Effort | Valeur | Statut |
|---|---|---|---|---|
| **1** | Menus déclaratifs + réorg ; fondation i18n | ~3j | Élevée | ✅ Fait |
| **2** | i18n en largeur (sélecteur, marquage, formats) | ~5j | Élevée | ✅ Marquage fini |
| **3** | Abstraction de dialecte SQL | ~4-6j | Élevée | ✅ Quirks consolidés |
| **4** | Domaine poker (stats, parsers, equity) | ~1-2 sem | Moyen/élevé | 🟡 En cours |
| **5** | Dette longue (god-modules, mypy, ruff) | continu | Moyen | À faire |
