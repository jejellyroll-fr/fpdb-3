# fpdb-3 — Chantiers inachevés & plan de couverture

> Établi le 2026-07-25 sur la branche `bigbang` (HEAD `e8ae67f7`).
> Mesures réelles, pas d'estimation : suite complète exécutée deux fois
> (`-m "not qt and not perf"` puis `-m "not perf"`) avec `pytest-cov`.
> Aucun fichier de code modifié pendant cette analyse.

---

## 0. Résumé

**Santé actuelle.** La suite est verte : **4 608 tests passés, 0 échec** (18 skipped,
10 xpassed, 183 s). Ruff, mypy et le ratchet Pyright sont verts en CI. `SQL.py` est
entièrement démantelé, `Stats.py` aussi, les 26 parseurs sont typés.

**Deux faiblesses structurelles.**

1. **Trois chantiers laissés à mi-parcours**, tous datés du 2026-07-16 dans
   `IMPROVEMENT_PLAN.md`, plus deux bugs connus non corrigés découverts pendant le
   diagnostic Windows.
2. **La couverture n'était ni mesurée ni gardée** : aucun job CI ne la calculait,
   aucun seuil n'existait. Résultat mesuré : **53,6 %** (40 013 unités
   instruction+branche non couvertes sur 86 295), avec **34 modules à 0 %**
   représentant 5 271 instructions. *L'étape 1 du plan corrige ce point — voir
   Partie C.*

> **Convention de mesure.** Tous les pourcentages de ce document sont ceux que
> coverage.py rapporte, **branches comprises** (c'est le chiffre qu'affiche
> `--cov-report=term` et qu'applique le cliquet). La couverture d'instructions
> seule, plus flatteuse, vaut 56,4 % : ne pas mélanger les deux.

Le point le plus grave n'est pas le chiffre global mais **sa répartition** : le code
qui écrit les caches statistiques (`database_caches.py`, **13 %**) et celui qui
reconstruit une main depuis la base (`Hand.select`, `Hand.to_canonical_dict`) sont
quasi non testés, alors que ce sont eux qui produisent les chiffres affichés dans le
HUD et les rapports.

---

## Partie A — Ce qui n'est pas fini

### A1. Découpage de `Database.py` — arrêté à 3/N 🟡

C'est le seul chantier explicitement marqué **en cours** dans `IMPROVEMENT_PLAN.md`.
Trois paliers livrés (caches, notes automatiques, tournois), puis plus rien depuis
9 jours.

État mesuré :

| | Lignes | Méthodes |
|---|---:|---:|
| Avant découpage | 6 621 | 143 |
| **Aujourd'hui** (`Database.py`) | **4 688** | **116** |
| Extraits (`database_caches` + `_auto_notes` + `_tournaments` + `_lambda_dict`) | 2 150 | 29 |

Domaines qui restent dans l'hôte, par ordre de taille des méthodes :

| Domaine | Méthodes principales | Lignes |
|---|---|---:|
| Données de référence / DDL | `fillDefaultData`, `create_tables`, `createAllForeignKeys`, `dropAllForeignKeys`, `dropAllIndexes`, `createAllIndexes`, `ensure_feature_tables`, `_ensure_table_columns` | ~750 |
| Import en masse | `prepareBulkImport`, `afterBulkImport`, `storeHand`, `storeHandsPlayers`, `storeHandsActions`, `resetBulkCache` | ~400 |
| Lecture HUD | `get_stats_from_hand`, `get_stats_from_hand_session`, `init_hud_stat_vars`, `get_hero_hudcache_start` | ~280 |
| Reconstruction de caches | `rebuild_cache`, `replace_statscache`, `cleanUpWeeksMonths` | ~380 |
| Connexion | `connect`, `do_connect`, `check_version`, `commit`, `get_last_insert_id` | ~270 |

`Database.py` reste inscrit au cliquet de complexité avec ses 4 règles
(`C901`, `PLR0912`, `PLR0915`, `UP031`) — la dette de complexité n'a pas baissé, elle
a été relocalisée (`database_caches.py` et `database_tournaments.py` sont eux aussi
inscrits au cliquet).

### A2. Deux bugs identifiés, documentés, non corrigés

**(a) iPoker : le hand id de la première main de chaque fichier est le code de session.**
Décrit en note de bas de chantier dans `WINDOWS_HUD_BUGFIX_PLAN.md`, laissé « à traiter
séparément ». **Toujours présent** : [`iPoker/base.py:247`](fpdb_3_legacy/iPoker/base.py:247)
compile `code="(?P<HID>[0-9]+)"`, motif que la chaîne `sessioncode="…"` satisfait aussi.
La première main d'une session porte donc un identifiant qui n'est pas le sien.

**(b) Bug 1 PokerStars cash (Windows) — 🟡 durci, jamais confirmé.**
`WINDOWS_HUD_BUGFIX_PLAN.md` le laisse en attente de validation live ; les trois autres
bugs de la série sont validés. Deux autres points attendent aussi une session live :
la synthèse de ring iPoker (PMU/bwin 6-max) et l'ancrage bas-centre sur un Twister
2/3-max.

### A3. i18n : la Vague 2 a laissé passer une génération de modules

La Vague 2 déclare « marquage `_()` de TOUS les modules GUI ». C'était vrai pour les
`Gui*` de 2026-07-12. Les modules écrits ou remaniés depuis n'ont **aucun marquage** :

| Module | Chaînes Qt littérales |
|---|---:|
| `ModernHudPreferences.py` | 94 |
| `ModernSitePreferences.py` | 27 |
| `swc_poker_console.py` | 24 |
| `ModernSeatPreferences.py` | 20 |
| `GuiCoinPokerCapture.py` | 16 |
| `ConfigReloadWidget.py` | 9 |
| `ring_stats/**` (4 vues + `__init__`) | 17 |
| `ThemeCreatorDialog.py` | 7 |

Pire : `ring_stats/` a des libellés **écrits en dur en français** (`"Nombre de mains : …"`,
assertion figée dans `test/test_ring_stats_starting_hands.py`), ce qui rend l'interface
bilingue quelle que soit la langue choisie. Les 13 langues autres que le français
restent par ailleurs non traduites (résidu déjà connu, hors dev).

### A4. Résidus assumés (rappel, pas des oublis)

- **Vague 3** : le quoting d'identifiants des requêtes n'est pas produit par le dialecte.
  Rendement décroissant, risque élevé — reste un choix défendable.
- **Vague 5** : 96 fichiers exemptés du cliquet de complexité (545 violations mesurées),
  `ModernHudPreferences.py` (4 488 lignes) n'a jamais été découpé alors qu'il dépasse
  aujourd'hui `Database.py`.
- **HUD PT4 / CoinPoker** : `HUD_PT4_IMPLEMENTATION_PLAN.md` et
  `COINPOKER_SPECIAL_HANDS_PLAN.md` décrivent des travaux **réalisés** (vérifié :
  `stats_table.live_min_stack_bb`, `Aux_Hud.block_positions`/`ref_layout_width`,
  `coinpoker_hand_builder` lit `dealerCardsRit`/`Rit2`/`DoubleBoard`/`splashPotAmount`,
  `Hands.splashPot` en schéma, filtres `Bomb`/`2xB`/`Splash` dans `GuiHandViewer`).
  Les fichiers ne sont simplement **pas marqués faits** — ils se lisent comme des
  chantiers ouverts alors qu'ils ne le sont plus. À clore par édition, pas par code.

---

## Partie B — Le trou de couverture

### B1. Mesure

| Sélection | Tests | Couverture |
|---|---:|---:|
| Sélection hors Qt (`not qt and not perf`) | 4 222 | **46,1 %** |
| Suite complète Qt incluse | 4 608 | **53,6 %** |

86 295 unités instruction+branche mesurées, **40 013 non couvertes**.
Le job `coverage` mesure désormais la réunion des deux sélections et le cliquet
interdit toute baisse.

### B2. Répartition par domaine (suite complète)

Découpage identique à celui du cliquet (`DOMAINS` dans `tools/coverage_ratchet.py`),
pour que ce tableau et `coverage-baseline.json` ne puissent pas diverger.

| Domaine | Unités | Couv. | Manquantes |
|---|---:|---:|---:|
| `gui` | 20 749 | 32,2 % | **14 077** |
| `parsers` | 17 652 | 64,1 % | 6 339 |
| `other` (Importer, logging, Config…) | 12 909 | 55,2 % | 5 779 |
| `database` | 5 799 | 54,2 % | 2 658 |
| `live-capture` | 7 367 | 66,5 % | 2 465 |
| `poker-domain` | 9 096 | 74,8 % | 2 296 |
| `tourney-summaries` | 3 532 | 53,4 % | 1 647 |
| `hud` | 4 579 | 65,3 % | 1 587 |
| `maintenance-scripts` | 1 759 | 17,9 % | 1 445 |
| `platform-pkg` | 1 069 | 17,1 % | 886 |

### B3. Les trous qui comptent vraiment

Le GUI domine en volume mais c'est le trou le moins dangereux : ce sont des vues, la
CI n'a pas d'écran, et une régression s'y voit. Les trous **à risque silencieux** sont
ceux où un chiffre faux passe inaperçu :

| Module | Couv. | Pourquoi c'est grave |
|---|---:|---|
| **`database_caches.py`** | **12,9 %** | `storeSessions` (176/253 lignes non couvertes), `storeSessionsCache` (110/140), `storeTourneysCache`, `storeCardsCache`, `storePositionsCache`. **C'est le code qui produit les agrégats affichés par le HUD et les rapports.** Extrait en 1/N sans qu'aucun test ne l'accompagne. |
| **`Hand.py`** (54 %) | | `select` (209/338) et `to_canonical_dict` (143/271) — relecture d'une main depuis la base et sérialisation canonique, deux chemins du replayer et de l'export. |
| **`Database.py`** (42 %) | | `get_stats_from_hand` (81 lignes), `prepareBulkImport`/`afterBulkImport` (112), `rebuild_cache` (43), `replace_statscache` (47), `cleanUpWeeksMonths` (43). Le chemin d'import en masse et la reconstruction de caches. |
| **`Importer.py`** (48 %) | | `_import_hh_file` (83 lignes non couvertes sur 335), `_import_summary_file` (44/87). Point d'entrée de tout import. |
| **`Configuration.py`** (59 %) | | `get_hud_ui_parameters` (140/341) et `set_hud_ui_parameters` (61/150) : lecture/écriture du `HUD_config.xml` de l'utilisateur. |
| **`HandDataReporter.py`** | **7,4 %** | 561 lignes non couvertes ; produit les rapports d'audit d'import. |
| **`loggingFpdb.py`** (34,8 %) | | 364 lignes ; « la journalisation fichier est morte » est un symptôme déjà rencontré dans le diagnostic Windows. |
| **`migration_helper.py`** | **0 %** | 256 instructions, migration inter-backends, jamais exécutée en test (le round-trip CI passe par `db_migrate`, pas par ce module). |

### B4. Parseurs : où sont les fixtures inexploitées

Le harnais golden (`test/test_live_parser_regression.py`) couvre 13 rooms. Les rooms
les moins couvertes ont pourtant un corpus disponible dans `regression-test-files/cash/` :

| Parseur | Couv. | Fixtures cash dispo | Dans le harnais golden ? |
|---|---:|---:|---|
| `BetfairToFpdb` | 17,8 % | 1 | ❌ |
| `MergeToFpdb` | 18,4 % | 34 | ❌ |
| `EnetToFpdb` | 21,8 % | 6 | ❌ |
| `EverestToFpdb` | 35,8 % | 5 | ❌ |
| `AbsoluteToFpdb` | 49,6 % | 13 | ❌ |
| `OnGameToFpdb` | 68,5 % | 17 | ❌ |
| `PkrToFpdb` | 77,8 % | 12 | ❌ |
| `WinningToFpdb` | 44,0 % | 46 | ✅ (fixtures `tests/`, corpus non exploité) |
| `FulltiltToFpdb` | 50,5 % | 54 | ✅ **1 seul fichier** |
| `PartyPokerToFpdb` | 47,7 % | 40 | ✅ (fixtures `tests/` seulement) |
| `MicrogamingToFpdb` | 68,9 % | 15 | ✅ **1 seul fichier** |
| `PokerTrackerToFpdb` | 72,6 % | 20 | ✅ **1 seul fichier** |
| `BossToFpdb` / `EverleafToFpdb` / `EntractionToFpdb` | 60–86 % | 14 / 11 / 6 | ✅ **1 seul fichier chacun** |
| `iPoker` (via `iPoker/`) | — | 30 | ✅ **1 seul fichier** |

**C'est le meilleur rendement du dépôt** : le harnais existe, il est générique
(`file_snapshot` + manifeste JSON), et ~250 fichiers de corpus déjà versionnés ne sont
pas branchés dessus. Élargir le manifeste ne demande pas d'écrire des assertions, juste
de générer les snapshots et de les relire.

Même remarque pour les résumés de tournoi : `iPokerSummary` 9,9 %,
`PokerTrackerSummary` 11,1 %, `WinningSummary` 19,3 %.

### B5. Modules à 0 %

34 modules, 5 271 instructions. Trois familles :

- **Points d'entrée GUI** (`fpdb.pyw` 1 147, `GuiSessionViewer` 406, `GuiLogView` 266,
  `GuiAutoNotesWorkbench` 524, `ModernSeatPreferences` 550…) — coût de test élevé,
  risque visible.
- **Scripts d'exploitation** (`migration_helper` 256, `sync_databases` 132,
  `backfill_showdown` 149, `backfill_boards` 115, `fix_draw_starting_hands` 110) —
  **ils écrivent en base et personne ne les teste.** Risque élevé, coût faible.
- **Abstraction plateforme** (`fpdb/infrastructure/platform/` : macos 292, winamax_title_parser
  106, linux 91, permissions 77) — dont `winamax_title_parser`, pure logique de
  parsing de titre de fenêtre, testable en 20 lignes.

---

## Partie C — Plan

Ordonné par **rendement décroissant** (lignes couvertes ou risque levé par jour de
travail). Chaque étape est livrable seule.

### Étape 1 — Rendre la couverture visible et non-régressive — ✅ FAIT (2026-07-25)

Livré :

- **`tools/coverage_ratchet.py`** — lit un `coverage.json` et le compare aux planchers
  suivis. Même patron que `todo_inventory.py --check` : `--check` en CI, `--update`
  pour re-semer quand la couverture monte réellement.
- **`coverage-baseline.json`** — planchers versionnés, semés au niveau **mesuré**
  (total 53,6 %), jamais à un objectif fictif. Trois niveaux de garde :
  1. le **total**, qui empêche la dérive globale ;
  2. **11 domaines**, pour que le GUI (20 749 unités à 32 %) ne puisse pas diluer le
     noyau — une chute de `poker-domain` n'est pas rattrapable par une hausse du GUI ;
  3. **18 modules gardés individuellement** (`Database.py`, `database_*`, `Hand.py`,
     `DerivedStats.py`, `stats_*`, `Importer.py`, `Configuration.py`), parce qu'un
     plancher de domaine laisserait `database_caches.py` (12,9 %) pourrir en silence
     pendant que `sql_*` monte.
- **Job CI `coverage`** (ubuntu) — exécute les deux sélections (hors-Qt puis Qt
  offscreen) en `--cov-append`, publie `coverage.json` + `htmlcov` en artefact, puis
  applique le cliquet.
- **`test/test_coverage_ratchet.py`** — 13 tests : appartenance aux domaines dans
  l'ordre de déclaration, calcul branch-aware, hausse acceptée, baisse refusée
  (module *et* domaine), tolérance, module gardé disparu, module gardé nouveau.
- `[tool.coverage.run] source` inclut désormais `fpdb` en plus de `fpdb_3_legacy` ;
  `coverage.json` est git-ignoré, `coverage-baseline.json` versionné.

**Deux décisions à connaître.**

*Tolérance de 0,5 point.* Découper la suite en deux passes déplace déjà le total de
4 lignes, et une exécution n'est pas bit-stable. La tolérance absorbe ce bruit ; elle
autorise en théorie une érosion lente, que le re-semis à chaque hausse corrige.

*Le paquet `platform-pkg` a une tolérance élargie à 3 points* : sa factory sélectionne
une implémentation par OS, or le cliquet tourne sur Linux tandis qu'un développeur
re-sème depuis macOS ou Windows. Les autres modules OS-dépendants ne posent pas ce
problème — `macos.py`, `linux.py`, `XTables.py` et `OSXTables.py` sont à 0 % partout
(jamais importés), les autres sont importés avec des handles natifs simulés, et les
deux seuls tests conditionnés par plateforme sont gated sur `win32`, qu'aucun des deux
runners n'est.

⚠️ **Planchers semés sur macOS.** Vérifié : sélection de tests identique entre macOS
et Linux. Si le premier passage CI échoue malgré tout sur `platform-pkg`, re-semer
depuis l'artefact Linux (`--update coverage.json`) plutôt que baisser un plancher.

**Critère de sortie atteint** : une PR qui baisse la couverture d'un module gardé ou
d'un domaine échoue en CI, avec le nom du coupable et l'écart au plancher.

### Étape 2 — Brancher le corpus existant sur le harnais golden · ~2 j

Le meilleur ratio du dépôt (~250 fixtures déjà versionnées, harnais générique déjà écrit).

1. Ajouter au manifeste **tous** les fichiers de `regression-test-files/cash/` des rooms
   déjà présentes dans `ROOMS`/`CASES` (Fulltilt 54, iPoker 30, PokerTracker 20,
   Microgaming 15, Boss 14, Everleaf 11, Entraction 6) — aujourd'hui 1 fichier chacune.
2. Ajouter les rooms absentes du harnais : Merge (34), OnGame (17), Absolute (13),
   PKR (12), Enet (6), Everest (5), Betfair (1).
3. Générer les snapshots, **les relire un par un** avant de les figer : un snapshot
   faux gèle un bug. Tout écart suspect devient un test nommé, pas une ligne de JSON.
4. Étendre le même patron aux résumés de tournoi les plus faibles (`iPokerSummary`,
   `PokerTrackerSummary`, `WinningSummary`).

**Gain attendu** : parseurs 66,9 % → ~85 %, soit ~1 800 lignes, sans écrire d'assertion
métier. **Effet de bord attendu et souhaité** : cette étape trouvera des bugs.

### Étape 3 — Tester les caches statistiques · ~2-3 j

Le trou le plus dangereux (`database_caches.py`, 12,9 %) et il est désormais isolé dans
son propre module, donc testable sans instancier tout `Database`.

1. Base SQLite temporaire + jeu de mains connu → `storeSessions`, `storeSessionsCache`,
   `storeTourneysCache`, `storeCardsCache`, `storePositionsCache`, `appendHandsSessionIds`.
2. Vérifier les **valeurs** agrégées, pas seulement l'absence d'exception : c'est
   exactement ce que la Vague 4 a fait pour `Stats.py`.
3. Ces tests sont le filet de sécurité qui manque à l'étape 5 (suite du découpage).

**Gain** : ~450 lignes, et surtout la garantie que les chiffres du HUD sont justes.

### Étape 4 — Sécuriser les scripts d'exploitation · ~1 j

`migration_helper` (256), `sync_databases` (132), `backfill_showdown` (149),
`backfill_boards` (115), `fix_draw_starting_hands` (110), `backfill_autonotes` (40,5 %).
Ils écrivent en base et sont à 0 %. Un test de bout en bout sur SQLite temporaire par
script — pas de la couverture cosmétique, la vérification qu'ils ne corrompent rien.

⚠️ Contrainte connue : ces tests ne doivent **jamais** toucher le `HUD_config.xml` réel
de l'utilisateur — copie temporaire obligatoire.

**Gain** : ~700 lignes, risque de corruption de données levé.

### Étape 5 — Reprendre le découpage de `Database.py` (4/N → N/N) · ~3-4 j

À faire **après** l'étape 3, pour la même raison que les paliers précédents ont réussi :
déplacer du code non testé est un pari.

Ordre proposé, du moins couplé au plus couplé :

1. **4/N — DDL & données de référence** (`fillDefaultData`, `create_tables`,
   `create/dropAllForeignKeys`, `create/dropAllIndexes`, `ensure_feature_tables`) → ~750 lignes.
   Domaine autonome, s'appuie sur les catalogues `sql_schema_*` déjà extraits.
2. **5/N — import en masse** (`prepareBulkImport`, `afterBulkImport`, `storeHand`,
   `storeHandsPlayers`, `storeHandsActions`, `resetBulkCache`) → ~400 lignes.
3. **6/N — lecture HUD** (`get_stats_from_hand*`, `init_hud_stat_vars`) → ~280 lignes.
4. **7/N — connexion** (`connect`, `do_connect`, `check_version`) → ~270 lignes.

Méthode inchangée, elle a fait ses preuves : déplacement **au mot près** vérifié par
comparaison d'AST, emprunts à l'hôte déclarés explicitement dans le mixin, annotations
reflétant ce que l'hôte déclare réellement.

**Objectif** : `Database.py` sous 2 500 lignes, et surtout **sortir des entrées du
cliquet de complexité** au lieu de les relocaliser — ce que les paliers 1 à 3 n'ont
pas fait.

### Étape 6 — Fermer les bugs connus · ~0,5 j

1. **iPoker hand id** : rendre `re_hand_info` insensible au préfixe (`\bcode="…"` ou
   ancrage sur `<game gamecode=`), + un test sur un fichier de session réel vérifiant
   que la première main porte son `gamecode`.
2. **Bug 1 PokerStars cash Windows** : session live, ou fermeture explicite du point
   dans `WINDOWS_HUD_BUGFIX_PLAN.md` si les traces du 22/07 suffisent.
3. **Marquer faits** `HUD_PT4_IMPLEMENTATION_PLAN.md` et
   `COINPOKER_SPECIAL_HANDS_PLAN.md` (travaux vérifiés en Partie A4), pour que le
   dépôt cesse d'annoncer des chantiers clos comme ouverts.

### Étape 7 — Rattraper l'i18n des modules récents · ~1,5 j

1. Marquer `_()` : `ModernHudPreferences` (94), `ModernSitePreferences` (27),
   `ModernSeatPreferences` (20), `GuiCoinPokerCapture` (16), `ConfigReloadWidget` (9),
   `ThemeCreatorDialog` (7), `swc_poker_console` (24).
2. **`ring_stats/`** : retirer le français en dur (`"Nombre de mains : …"`), passer par
   `_()`, mettre à jour `test/test_ring_stats_starting_hands.py` qui fige aujourd'hui
   la chaîne française.
3. Régénérer `locale/fpdb.pot` (`tools/update_pot.py`) et compléter le catalogue `fr_FR`.
4. Ajouter un test de garde : aucun nouveau module Qt ne doit contenir de chaîne
   littérale dans un appel `setText`/`setWindowTitle`/`addTab`/`QLabel(...)`.

### Étape 8 — Continu

- `ModernHudPreferences.py` (4 488 lignes) : plus gros module du dépôt, jamais découpé,
  60 % couvert. Prochain god-module après `Database.py`.
- Sortir progressivement les 96 fichiers du `per-file-ignores` de complexité.
- `fpdb/infrastructure/platform/winamax_title_parser.py` (0 %, 106 instructions,
  logique pure) : gain immédiat pour un coût nul.

---

## Récapitulatif

| # | Étape | Effort | Gain couverture | Risque levé |
|---|---|---:|---:|---|
| 1 | ✅ Cliquet de couverture en CI | fait | — | Empêche la dérive |
| 2 | Corpus → harnais golden | 2 j | ~1 800 l. | Régressions parseurs |
| 3 | Tests des caches statistiques | 2-3 j | ~450 l. | **Chiffres HUD faux** |
| 4 | Scripts d'exploitation | 1 j | ~700 l. | **Corruption de base** |
| 5 | `Database.py` 4/N → N/N | 3-4 j | — | Dette de complexité |
| 6 | Bugs connus + clôture des plans | 0,5 j | — | Hand id iPoker faux |
| 7 | i18n des modules récents | 1,5 j | — | UI bilingue |
| 8 | Continu (`ModernHudPreferences`, cliquets) | — | — | — |

**Chemin critique recommandé : 1 → 3 → 2 → 4 → 5.** L'étape 1 protège tout le reste ;
l'étape 3 avant l'étape 5 parce qu'on ne déplace pas du code non testé.

---

## Annexe — Reproduire la mesure et manipuler le cliquet

Mesurer comme le fait la CI (les deux sélections, un seul rapport combiné) :

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -p no:pytest-qt -m "not qt and not perf" --cov --cov-report=
```

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -m qt --cov --cov-append --cov-report=
```

Produire le rapport puis vérifier les planchers :

```bash
.venv/bin/python -m coverage json -o coverage.json && .venv/bin/python tools/coverage_ratchet.py --check coverage.json
```

Re-semer les planchers — **uniquement** après une hausse réelle ; le diff de
`coverage-baseline.json` doit alors ne montrer que des montées :

```bash
.venv/bin/python tools/coverage_ratchet.py --update coverage.json
```

Rapport HTML pour lire les lignes manquantes d'un module :

```bash
.venv/bin/python -m coverage html -d htmlcov
```
