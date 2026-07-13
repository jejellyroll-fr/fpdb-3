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

**Reste à faire**
- ✅ **Stats** (`Stats.py`) : alias modernes WWSF/fold-to-cbet par rue, 3bet/4bet/squeeze par position (BB, SB, BTN, CO, MP, EP), et ranges observées exactes (action / mains distribuées), avec tests de valeurs sur mains connues.
- ✅ **Parsers** (26 sites) : harnais golden étendu à 13 convertisseurs (52 fichiers / 395 mains ; identité, gametype, joueurs, board, actions, gains, pot/rake) et matrice actif/legacy documentée. PartyPoker est hermétique ; BetOnline, iPoker et SwC sont couverts depuis leur corpus public. La fixture Unibet Banzai a été restaurée avec son symbole euro réel.
- ✅ **Équité / EV** : `pypoker-eval` compilé et validé sous Python 3.13/macOS ARM, derrière `fpdb_3_legacy/equity.py` (chargement optionnel sûr, validation des cartes, boards incomplets explicitement complétés, équités normalisées `0..1`, compteurs win/tie/loss, exhaustif/Monte-Carlo et part attendue du pot). `DerivedStats` détecte l'action all-in réelle, transmet le board cumulé à cette rue et stocke `allInEV` comme profit attendu en monnaie/chips ×100. Le replayer affiche pot odds, équité et edge lorsque toutes les mains actives sont connues ; `HandDataReporter` expose la valeur brute et lisible par joueur. L'absence du moteur ou de cartes adverses reste non bloquante.

**Effort** ~1-2 sem · **Impact** moyen/élevé.

---

## Vague 5 — Dette technique longue 🧹

- ✅ **Premier ratchet Ruff** (2026-07-13) : suppression globale des 23 `F541` (f-strings sans interpolation) et des 5 `F601` (clés de dictionnaire dupliquées), avec job CI `quality` empêchant leur retour. Une duplication réelle de l'alias HUD `three_b` écrasait silencieusement l'échantillon `4.4` par `9.0`. Les modules modernisés de la Vague 4 sont vérifiés avec l'ensemble des règles Ruff actives. Dette passée de 3334 à 3306 diagnostics ; les règles seront absorbées une par une pour garder des diffs révisables.
- ✅ **Ruff complet** (2026-07-13) : dette active résorbée règle par règle, imports étoile supprimés, tests masqués restaurés et CI passée de cliquets partiels à `ruff check` sur tout le dépôt. Les exceptions historiques (`E402`, `E501` et huit modules de formatage `%` sensible) sont documentées dans `pyproject.toml`.
- 🟡 **Typage progressif** (2026-07-13) : mypy activé en CI sur `equity.py`, `dialects.py`, `pt4_adapter/`, l'ensemble du domaine HTTP capture/OFC/SwC, la détection des rooms installées, les fondations menus/i18n (dont le contrat historique `L10n`), l'infrastructure DB découplée, les adaptateurs de statistiques/AutoNotes, le domaine complet des thèmes/popups modernes et les utilitaires CLI/régression (quarante-quatre modules), avec imports externes ignorés et corps non annotés vérifiés. Le périmètre sera élargi par domaine sans imposer immédiatement le typage aux god-modules.
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
| **4** | Domaine poker (stats, parsers, equity) | ~1-2 sem | Moyen/élevé | ✅ Fait |
| **5** | Dette longue (god-modules, mypy, ruff) | continu | Moyen | À faire |
