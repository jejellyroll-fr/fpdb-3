# Plan — Run It Twice, Bomb Pot (double board), Splash Pot & EV Cashout (CoinPoker)

Statut : ✅ FAIT (2026-07-25).
Objectif : pouvoir **filtrer** dans le Hand Viewer et **afficher** dans le Replayer les
mains CoinPoker de type *run it twice*, *bomb pot / double board*, *splash pot* et
*EV cashout* — et surtout **capturer** ces cas depuis le flux CoinPoker (aujourd'hui
ignorés à l'import).

---

## 1. Analyse — qui capture / supporte quoi

Presque tout l'aval est déjà prêt. **Le seul trou : le builder CoinPoker jette ces
données** (`coinpoker_hand_builder._build_one` ne lit que `dealerCards`).

| Maillon | RIT | Double board / bomb pot | Splash pot | EV cashout |
|---|---|---|---|---|
| **Protocole CoinPoker** (events) | ✅ `dealerCardsRit`, `dealerCardsRit2`, `winnerInfo.rit` | ✅ `dealerCardsDoubleBoard`, `winnerInfo.doubleBoard`, `Hands.bombPot` | ✅ `cumulativeWinnerInfo.splashPotAmount`, `isMegaSplash` | ✅ `winnerList[].isInsured` |
| **Objet `Hand` fpdb** | ✅ multi-board, `runItTimes` | ✅ multi-board, `bombPot` | ❌ pas de champ | ✅ `cashedOut` / `isCashOut` / `cashOutFees` / `cashOutAmounts` |
| **Schéma DB** | ✅ table `Boards`, `Hands.runItTwice` | ✅ `Boards`, `Hands.bombPot` | ❌ pas de colonne | ✅ `HandsPlayers.isCashOut` / `cashOutFee`, table `HandsCashout` |
| **Hand Viewer (filtres)** | ✅ case `RIT` câblée SQL (`h.runItTwice = 1`) | ❌ à ajouter | ❌ à ajouter | ✅ case `CO$` câblée (`EXISTS … HandsCashout`) |
| **Replayer** | ✅ rend déjà les runs multiples (couleurs par run) | ✅ multi-board géré | ❌ pas d'affichage du montant | partiel |

**Constat base actuelle** : `runItTwice=0`, `bombPot=0`, `isCashOut=0`, table `Boards`
vide — parce que l'import CoinPoker ne peuple aucun de ces champs.

**Références clés**
- `fpdb_3_legacy/coinpoker_hand_builder.py:151` et `:224` — ne lisent que `dealerCards`.
- Events porteurs : `game.dealer_cards` et `game.rabbit_run` →
  `dealerCards`, `dealerCardsRit`, `dealerCardsRit2`, `dealerCardsDoubleBoard`,
  `rabbitRunCards`, `rabbitRunCardsDoubleBoard`.
- `game.winnerInfo` → `rit`, `doubleBoard`, `winnerDataList[].winnerDetails.winnerList[].isInsured`.
- `game.cumulativeWinnerInfo` → `splashPotAmount`, `isMegaSplash`.
- `fpdb_3_legacy/Hand.py` — `board`/`storeBoards` (multi-board), `runItTimes`,
  `bombPot`, `cashedOut`/`isCashOut`/`cashOutFees`/`cashOutAmounts`.
- `fpdb_3_legacy/GuiHandViewer.py:190-249` — cases `AI`/`SD`/`RIT`/`CO$` + clauses SQL.
- `fpdb_3_legacy/GuiReplayer.py:221,288` — rendu run-it (couleurs par run).

---

## 2. Plan d'implémentation

### Phase 1 — Extraction dans le builder CoinPoker (le cœur)
`fpdb_3_legacy/coinpoker_hand_builder.py` → `_build_one`, émettre de nouveaux champs
`hand_data` :
- **Boards multiples** : lire `dealerCardsRit` / `dealerCardsRit2` (RIT) et
  `dealerCardsDoubleBoard` → produire une liste `boards` (au lieu d'un `community`
  unique). Flag RIT depuis `winnerInfo.rit` (ou présence de `Rit2`).
- **`run_it_times`** : 1 / 2 / 3 selon les boards présents.
- **`bomb_pot`** : détecter (pas de blinds preflop + ante forcé, ou marqueur dans
  `pre_hand_start_info` / `dealer_chat` — à confirmer sur une vraie main bomb pot).
- **`double_board`** : présence de `dealerCardsDoubleBoard`.
- **`splash_pot`** : `cumulativeWinnerInfo.splashPotAmount` (+ `isMegaSplash`).
- **`cashout`** : par joueur depuis `winnerList[].isInsured` (+ montants / fees).

### Phase 2 — Mapping vers `Hand` (`http_capture_hand_builder.py`)
- `build_fpdb_hand` : support **multi-board** (`addBoard` par run au lieu du seul
  `setCommunityCards`), poser `hand.runItTimes`, `hand.bombPot`,
  `hand.cashedOut`/`cashOutFees`/`cashOutAmounts`, et le splash pot.
- `_community_cards_by_street` → généraliser en `_boards()` (liste de boards).

### Phase 3 — Schéma : splash pot (seule vraie migration)
- Ajouter `Hands.splashPot` (montant en cents, 0 = non) via `sql_schema_*` +
  migration idempotente (`db_migrate.py`). Peuplé par `DerivedStats` / `storeHand`.
- Double board & bomb pot : pas de migration (déjà `bombPot` + `Boards`).

### Phase 4 — Filtres Hand Viewer (`GuiHandViewer.py`)
Même modèle que `RIT` / `CO$` (`GuiHandViewer.py:242`) :
- `Bomb` → `h.bombPot > 0`
- `2xB` (double board) → `(SELECT COUNT(*) FROM Boards b WHERE b.handId = h.id) >= 2`
- `Splash` → `h.splashPot > 0`

### Phase 5 — Replayer (`GuiReplayer.py`)
- Multi-board RIT déjà rendu (couleurs par run). Ajouter : label **« Splash pot: X »**
  et **« Bomb pot »** dans l'overlay ; vérifier le rendu **double board** simultané
  (2 boards côte à côte, pas 2 runs séquentiels).

### Phase 6 — Tests
- `test/test_coinpoker_converter.py` : fixtures RIT / double board / splash / cashout →
  vérifier `boards`, `runItTimes`, `bombPot`, `splashPot`, cashout dans le `hand_data`
  et le `Hand` construit.
- Filtres `GuiHandViewer` (clauses SQL).

---

## 3. À valider avant de coder
La fixture actuelle (`test/data/coinpoker_hand_events.json`) n'a **pas** de main
*bomb pot* ni de *cashout* réel : on a les noms de champs mais pas d'exemple de valeurs.
→ Idéalement, **capturer 1 main de chaque cas** (RIT, bomb pot double board, splash,
cashout) pour caler l'extraction sur des données réelles ; sinon coder sur la structure
des champs et ajuster aux tests.

## 4. Ordre suggéré
Phase 1 + 2 en premier (extraction + mapping, testables en dry-run, sans toucher au
schéma), puis Phase 3 (splash), puis 4 (filtres), puis 5 (replayer). Chaque phase est
livrable indépendamment.
