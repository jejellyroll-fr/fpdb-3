# Plan d'implémentation — HUD PT4 multiblocs

Statut : ✅ FAIT (2026-07-25). Aucun fichier de code modifié pendant l'analyse initiale.
Branche : `bigbang`. Diff courant : ~600 lignes ajoutées sur 10 fichiers, non commitées.

---

## 0. Pourquoi on tourne en rond

Ce n'est pas un problème de diagnostic, c'est un problème de **méthode**.

Les trois itérations précédentes ont :

1. **Corrigé le symptôme visible dans la stack trace**, pas la cause. Le `KeyError: '5185'`
   a été traité en coercant les clés en `str` et en enveloppant la lecture dans un
   `.get(...)`. Cela a supprimé la trace mais a laissé la boucle de mise à jour se
   casser plus loin, sur une autre exception.
2. **Ajouté de la logique métier dans la couche vue.** `live_min_stack_bb` et
   `playershort` ont été implémentés en dur dans `SimpleStat.update`
   ([Aux_Hud.py:997](fpdb_3_legacy/Aux_Hud.py:997) et
   [Aux_Hud.py:1043](fpdb_3_legacy/Aux_Hud.py:1043)), alors que `Stats.py` est le
   registre canonique des stats — et que `playershort` **y existe déjà**
   ([Stats.py:473](fpdb_3_legacy/Stats.py:473)).
3. **Validé sur les tests unitaires** (« 47 tests passed »), alors qu'aucun test ne
   couvre le chemin d'exécution réel : création de fenêtre, boucle `update_gui`,
   positionnement. Les tests passent parce qu'ils ne touchent pas le code cassé.

Conséquence : chaque correction déplace le crash d'un cran sans jamais rétablir un
cycle de rendu qui va au bout. **Tant qu'une seule exception subsiste dans la boucle
`update_gui`, tous les symptômes en aval (stats figées, noms absents, HUD table
manquant) restent visibles — et paraissent être des bugs distincts alors qu'ils
n'en sont qu'un.**

La règle de travail pour la suite : **aucun correctif n'est déclaré valide tant
qu'un cycle complet de rafraîchissement n'a pas été observé sans exception**, sur
une vraie main, avec `FPDB_HUD_TRACE=1`.

---

## 1. Constats vérifiés

Chaque point ci-dessous a été confirmé par lecture du code ou du config, pas déduit.

### 1.1 — Le HUD table crashe de façon déterministe `[CONFIRMÉ]`

Deux défauts cumulés, dans le même bloc de code :

**a) `AttributeError` hors du `try`.**
[Aux_Hud.py:1000](fpdb_3_legacy/Aux_Hud.py:1000) lit `self.hud.hand_instance.handId`.
L'attribut n'existe pas : `Hand` expose `self.handid` (minuscule d,
[Hand.py:124](fpdb_3_legacy/Hand.py:124)). Cette ligne est **avant** le `try:` de la
ligne 1002 — l'exception n'est donc pas rattrapée localement.

De plus, `handid` contient `res["sitehandno"]` ([Hand.py:1052](fpdb_3_legacy/Hand.py:1052)),
c'est-à-dire le **numéro de main du site**, pas la clé primaire `Hands.id` que la
requête interroge (`WHERE h.id = ?`). Même corrigée en casse, la requête serait
sémantiquement fausse.

**b) Placeholder SQL incompatible.**
La requête utilise `%s` en dur. Le backend configuré est **SQLite**
(`db_server="sqlite"`, `~/.fpdb/HUD_config.xml:2651`), qui exige `?`. Le reste du
code passe par `self.sql.query["placeholder"]` pour cette raison.

**c) Contrat `self.number` violé.**
Le hack fixe `self.number = (True, "---")` — un 2-uple. Or `ClassicStat.update`
lit inconditionnellement `self.number[5]`, `[3]` et `[4]` à
[Aux_Classic_Hud.py:492](fpdb_3_legacy/Aux_Classic_Hud.py:492). Toute stat qui ne
renvoie pas le 6-uple attendu par `Stats.do_stat` lève un `IndexError`.

> Autrement dit : même en corrigeant (a) et (b), le HUD table crasherait encore sur (c).
> C'est la signature typique d'un correctif validé par des tests qui n'exécutent pas
> le chemin réel.

**Effet en cascade.** `create()` appelle `update_contents(window, "table")`
([Aux_Hud.py:566](fpdb_3_legacy/Aux_Hud.py:566)) sans `try`. La fenêtre table n'est
donc jamais construite. Ensuite, à chaque main, `update_gui` itère `m_windows` —
qui contient la clé `("table", idx)` — et relance l'exception. `HUD_main` la
rattrape et journalise `Error updating HUD for hand X` : **toutes les fenêtres
situées après la fenêtre table dans l'itération ne sont jamais mises à jour.**

C'est la cause unique et suffisante des trois symptômes rapportés : pas de HUD
table, stats figées, noms absents.

### 1.2 — Les positions manuelles sont écrasées à chaque main `[CONFIRMÉ]`

[`_position_and_show_block()`](fpdb_3_legacy/Aux_Classic_Hud.py:122) est appelée pour
**chaque fenêtre-bloc** d'un siège, à chaque `update_contents`. Elle calcule :

```python
pos_x = max(0, self.aw.positions[seat][0] + table_x)   # ligne 133
pos_y = max(0, self.aw.positions[seat][1] + table_y)   # ligne 134
...
self.move(pos_x, pos_y)                                 # ligne 147
```

`self.aw.positions[seat]` est **l'ancre du siège**, identique pour tous les blocs de
ce siège. La méthode ignore totalement `self.block_index`, `aw.block_positions` et le
store JSON. Chaque main, tous les blocs d'un siège sont donc empilés sur le même
point.

Cela explique d'un coup, sans autre hypothèse :

- « une seule boîte après une main » — elles sont superposées, pas disparues ;
- « placement manuel perdu » — le drag écrit bien dans le JSON, mais la main suivante
  réécrase la position à l'écran ;
- « retour à droite » — l'ancre du siège provient du layout de repli.

C'est le correctif à plus fort levier : **une seule méthode à réparer**.

### 1.3 — Trois espaces de coordonnées incompatibles coexistent `[CONFIRMÉ]`

| Chemin | Convention utilisée |
|---|---|
| `create()`, bloc non stocké ([Aux_Hud.py:495](fpdb_3_legacy/Aux_Hud.py:495)) | `create_scale_position(siège)` → espace **table**, puis `+ offset` brut → espace **layout**. Unités mélangées. |
| `create()`, bloc stocké | valeur du JSON (espace **layout**) utilisée telle quelle comme espace **table**. |
| `_move_block_windows()` | valeur du JSON **multipliée** par `scale_factors` ([Aux_Hud.py:463](fpdb_3_legacy/Aux_Hud.py:463)). |

Aggravant : `create_scale_position` divise par `self.hud.layout.width`
([Aux_Base.py:610](fpdb_3_legacy/Aux_Base.py:610)), mais `layout.width` est **muté**
en `table.width` à la fin du resize ([Hud.py:222](fpdb_3_legacy/Hud.py:222),
[Aux_Base.py:598](fpdb_3_legacy/Aux_Base.py:598)). Le facteur d'échelle vaut donc `1.0`
au deuxième appel. Pendant ce temps `scale_factors` utilise `ref_layout_width` (gelé).
Les deux dénominateurs divergent.

Résultat : `create()` et `_move_block_windows()` ne placent pas la même fenêtre au
même endroit, et un cycle resize A→B→A ne revient pas en A.

### 1.4 — L'importateur PT4 fabrique des cellules inexistantes `[CONFIRMÉ]`

Dans `~/.fpdb/HUD_config.xml`, le bloc `min_stack__table` contient :

```xml
<text _rowcol="(5,1)" label="STACK" .../>
<stat _rowcol="(5,2)" _stat_name="gp_2x" tip="GenerationPoker" click=""/>
```

L'éditeur PT4 (capture 4) montre que ce groupe possède **exactement 5 items** :
`Text: MIN`, `Stat: Live Min Stack BB`, `Text: GenerationPoker`,
`Text: Coaching & Staking`, `Text: STACK`. **Aucune stat `gp_2x`.**

L'importateur a inventé une cellule et lui a collé le `tip` du *texte voisin*. C'est
le même défaut, décalé d'un cran, que le `tip` mal aligné dans `villain_info_3h`
(`tip="AFq"` sur la stat `vpip`, `tip="SQ"` sur `pfr`). L'appariement
stat ↔ métadonnée est indexé de travers.

Effet secondaire : cette `gp_2x` parasite est une stat **joueur** dans un bloc
**table**, donc appelée avec `player_id=None`.

### 1.5 — Points contribuant, non bloquants

- Les libellés `VP` / `PFR` / `AFq` / `SQ` de `villain_info_3h` ont
  `fgcolor="#000000"` **et** `bgcolor="#000000"` : noir sur noir, invisibles.
- Les blocs `sb_3h`, `bb_3h`, `bu_3h` ont tous `x="0" y="0"`. Comme ils sont liés à
  une position (`SB`/`BB`/`BTN`), un seul est visible par siège : **ce n'est pas la
  cause** des superpositions. Cette piste, avancée précédemment, est **infirmée**.
- `HudStatsPersistence` et `Database.get_stats_from_hand` normalisent désormais les
  ID en `str` de façon cohérente. Ce travail est **correct et à conserver**.

### 1.6 — Ce qui reste non vérifié `[À INSTRUMENTER]`

- La sémantique exacte de `layout.hh_seats[seat]` (siège visuel → siège HH) vs. la clé
  `seatNo` de `get_seat_players`. Un décalage ici casserait la résolution du nom, mais
  le repli sur `stat_dict[player_id]["screen_name"]` le masquerait.
- L'absence du nom sur la capture 3 ne peut pas être attribuée à une ligne précise :
  cette capture est antérieure aux correctifs d'ID. **Ne pas conclure sans trace.**

---

## 2. Décision d'architecture

> **Recommandation : revenir en arrière sur les hacks de la couche vue, conserver les
> corrections de la couche données.**

Le diff actuel mélange du bon travail et des rustines. Continuer à empiler dessus est
exactement ce qui produit l'effet « je tourne en rond ».

| À **conserver** | À **retirer / réécrire** |
|---|---|
| `Database.get_seat_players()` | `SimpleStat.update` : branches `live_min_stack_bb` et `playershort` ([Aux_Hud.py:997-1060](fpdb_3_legacy/Aux_Hud.py:997)) |
| Normalisation `str` des ID (`Database.py`, `HudStatsPersistence.py`) | `_position_and_show_block()` (réécriture complète) |
| Le concept de store JSON `HUD_layout_positions.json` | La propriété `scale_factors` (doublon incohérent de `create_scale_position`) |
| `scope` / `audience` / `id` sur `StatBlock` | La déduplication `_last_processed_hands` (masque le double cycle au lieu de le supprimer) |
| Le mode `FPDB_HUD_TRACE=1` | Le mappage `gp_2x` parasite dans l'importateur |

Raison : une stat **doit** être une fonction de `Stats.py` respectant le contrat du
6-uple. Une position **doit** avoir un seul espace de coordonnées. Tout le reste est
une conséquence.

---

## 3. Plan d'exécution

Les phases sont ordonnées par **dépendance de vérification** : chacune doit être
observable avant de passer à la suivante. Ne pas paralléliser.

### Phase 0 — Rendre l'échec observable (prérequis absolu)

Sans ceci, les phases suivantes ne sont pas vérifiables.

1. Abaisser le logger HUD au niveau `INFO` (il est à `ERROR`, ce qui a filtré toutes
   les traces de position émises en `WARNING` — d'où un `HUD-log.txt` muet depuis le
   3 juillet).
2. Dans `HUD_main.idle_update`, journaliser l'exception **avec la clé de fenêtre en
   cours** avant de la rattraper. Actuellement on ne sait pas quelle fenêtre a crashé.
3. Ajouter un compteur : nombre de fenêtres mises à jour / nombre attendu. Si les deux
   diffèrent, la boucle a été interrompue.

**Critère de sortie :** sur une main réelle, le log indique `N/N fenêtres mises à jour`
ou nomme précisément la fenêtre fautive.

### Phase 1 — Rétablir un cycle de rendu qui va au bout

Objectif : zéro exception dans `update_gui`. Rien d'autre.

1. Supprimer les branches `live_min_stack_bb` et `playershort` de `SimpleStat.update`.
   `playershort` retrouve ainsi son implémentation canonique
   ([Stats.py:473](fpdb_3_legacy/Stats.py:473)).
2. Retirer la stat parasite `gp_2x` du bloc `min_stack__table` (corriger l'importateur
   en Phase 3 ; d'ici là, corriger le XML).
3. Isoler la mise à jour de chaque fenêtre dans son propre `try/except` avec log
   nominatif, afin qu'une fenêtre fautive n'empêche plus les autres de se rafraîchir.

**Critère de sortie :** stats et noms se mettent à jour sur les blocs joueur, à chaque
main, sans `Error updating HUD for hand`. Le HUD table peut encore être absent.

> C'est ici que les symptômes « stats figées » et « noms absents » doivent disparaître.
> S'ils persistent, l'hypothèse 1.1 est fausse et **il faut s'arrêter et réanalyser**,
> pas ajouter un correctif.

### Phase 2 — Un seul espace de coordonnées

1. Définir la convention unique : **coordonnées canoniques relatives au coin haut-gauche
   de la table, exprimées dans l'espace du layout de référence** (`ref_layout_width` /
   `ref_layout_height`, gelés à la première initialisation).
2. Une seule fonction de conversion `canonical → écran`, utilisée par `create()`,
   `_move_block_windows()` et `_position_and_show_block()`. Supprimer `scale_factors`
   et ne plus muter `layout.width` / `layout.height`.
3. Réécrire `_position_and_show_block()` pour qu'elle lise
   `aw.block_positions[(seat, self.block_index)]` — **jamais** `aw.positions[seat]`.
4. Le clamp écran s'applique **uniquement à l'affichage**, jamais à la valeur persistée.

**Critère de sortie :**
- Déplacer un bloc du siège 1 ne déplace aucun bloc d'un autre siège.
- Un cycle resize A→B→A restitue les coordonnées A **au pixel près**.
- Après 20 mains puis redémarrage, toutes les positions sont identiques.

### Phase 3 — Importateur PT4 fidèle

1. Corriger l'appariement stat ↔ `tip` (décalage d'index) et **cesser d'émettre des
   cellules absentes du fichier PT4**. Un enregistrement PT4 produit au plus une stat.
2. Ajouter un test de fidélité : pour `Min Stack (Table)`, l'importateur doit produire
   **exactement 5 items** et zéro `<stat>` autre que `live_min_stack_bb`.
3. Corriger les couleurs noir-sur-noir des libellés.

**Critère de sortie :** un test compare le nombre et le type d'items importés à
l'inventaire attendu du fichier PT4, groupe par groupe.

### Phase 4 — `live_min_stack_bb` comme vraie stat

Implémenter dans `Stats.py`, pas dans la vue.

1. Signature conforme : renvoie le 6-uple standard.
2. Requête via `self.sql.query["placeholder"]`, jamais `%s` en dur.
3. Utiliser la **clé primaire** `Hands.id`, pas `hand.handid` (numéro de main du site).
4. Sémantique PT4 : minimum des stacks de **fin de main** de la main précédente
   importée, joueurs éliminés exclus, divisé par la grosse blind.
5. La donnée est calculée **une fois par main** et injectée dans `stat_dict`, pas
   requêtée depuis `update()` — qui s'exécute sur le thread UI, une fois par label.

**Critère de sortie :** le HUD table s'affiche, reste visible avec
`show_hero_hud=false`, et affiche une valeur numérique.

### Phase 5 — Cycle déterministe

1. Supprimer le double cycle `create/update/resize` de `HUD_main`
   ([HUD_main.pyw:919](fpdb_3_legacy/HUD_main.pyw:919)) plutôt que de le masquer via
   `_last_processed_hands`.
2. Repositionner **uniquement** sur un vrai changement de géométrie de table.

### Phase 6 — Non-régression

1. Stabiliser les **4 échecs préexistants** de changement de stat-set avant d'ajouter
   de nouveaux tests (ils masqueraient les régressions).
2. Ajouter les tests d'acceptation ci-dessous.

---

## 4. Critères d'acceptation

Ces critères ne sont **pas** satisfaits par des tests unitaires seuls. Ceux marqués
`[RUNTIME]` exigent une observation sur une table réelle avec `FPDB_HUD_TRACE=1`.

| # | Critère | Vérification |
|---|---|---|
| 1 | Aucune exception dans `update_gui` sur 20 mains consécutives | `[RUNTIME]` |
| 2 | 3-handed : 2 vilains × 4 groupes joueur + 1 groupe table, aucun HUD héros | `[RUNTIME]` |
| 3 | Heads-up : 4 groupes vilain + 1 groupe table | `[RUNTIME]` |
| 4 | `Potila06` apparaît dans `Villain Info 3H`, avec Notes et grille conforme | `[RUNTIME]` |
| 5 | Déplacer une boîte n'en déplace aucune autre | `[RUNTIME]` |
| 6 | Après 20 mains + redémarrage, positions identiques au pixel près | `[RUNTIME]` |
| 7 | Resize A→B→A restitue exactement A | test unitaire |
| 8 | `Min Stack (Table)` importe exactement 5 items, 1 seule stat | test unitaire |
| 9 | Les HUD legacy mono-bloc restent inchangés | test unitaire |
| 10 | Les 4 échecs de stat-set préexistants sont corrigés | test unitaire |

---

## 5. Ce que ce plan refuse explicitement de faire

- **Ne pas** ajouter de `try/except` supplémentaire pour faire taire une exception sans
  en avoir identifié la cause.
- **Ne pas** implémenter de logique de stat dans `Aux_Hud.py` ou `Aux_Classic_Hud.py`.
- **Ne pas** déclarer une phase terminée sur la seule foi de `pytest`. Les 47 tests
  passaient déjà pendant que le HUD table crashait à chaque main.
- **Ne pas** toucher `~/.fpdb/HUD_config.xml` de l'utilisateur sans sauvegarde
  horodatée préalable : c'est sa configuration de travail, et une réimportation l'a
  déjà écrasée une fois.

---

## 6. Prochaine action

Phase 0, étape 1 : abaisser le niveau du logger HUD et instrumenter `idle_update`
pour nommer la fenêtre fautive. Sans cette trace, les phases 1 à 5 seront à nouveau
validées à l'aveugle.
