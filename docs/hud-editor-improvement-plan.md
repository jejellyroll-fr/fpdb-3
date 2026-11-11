# Plan d'implémentation — éditeur « HUD Preferences »

Objectif : rendre la composition d'un HUD visuelle (glisser-déposer, catalogue de
statistiques), corriger les défauts de l'éditeur actuel et relever la couverture
de tests, **sans changer le format `HUD_config.xml` ni la disposition générale**
(Panels · Group Properties · Item Properties · Design · HUD Preview).

Périmètre du code : `fpdb_3_legacy/modern_hud_preferences/`
(`main_dialog.py` 4451 lignes, `dialogs.py`, `design_canvas.py`, `preview_widgets.py`).

Les défauts ci-dessous sont établis par lecture du code ; aucun n'a encore été
reproduit dans l'application. Le lot 0 les fige par des tests avant correction.

## 1. Constat

### 1.1 Ce qui manque

| Manque | Où |
|---|---|
| Aucun glisser-déposer : `_CanvasChip` n'émet qu'un clic, le canevas n'accepte aucun dépôt | `design_canvas.py:22-35` |
| Les cellules vides ne sont pas des widgets : rien sur quoi déposer | `design_canvas.py:89-129` |
| Position réglée par deux listes Row / Column dans une fenêtre modale | `dialogs.py:137-148` |
| Catalogue codé en dur : 108 noms dont 16 n'existent pas dans `Stats.STATLIST` (`3bet`, `hands`, `agg`, `bb100`, `cb_flop`…), et 92 valides sur 281 | `dialogs.py:157-268` |
| Les stats analytiques ne s'ajoutent que depuis l'onglet Dynamic Panels | `main_dialog.py:3561`, `3972` |
| `rich_text`, `font_size`, `xpad`, `ypad`, échelles de police : lus par le HUD, absents de l'éditeur | `config_hud_layouts.py:367-383` |
| Pas de renommage de profil, pas de redimensionnement de grille, pas d'annulation | `main_dialog.py:2118-2189` |
| Préfixe, suffixe, libellé affiché, info-bulle, action au clic : non éditables | `main_dialog.py:2031-2100` |

### 1.2 Défauts relevés

| # | Défaut | Conséquence | Où |
|---|---|---|---|
| B1 | `AddStatDialog.get_stat()` renvoie toujours seuils 20/60 et couleurs rouge/vert, appliqués par `ref.update()` | Éditer une stat sans couleur lui en impose | `dialogs.py:465`, `main_dialog.py:2786` |
| B2 | Aucun contrôle d'occupation à l'ajout ni à l'édition | Deux éléments sur la même cellule ; au rechargement `Stat_sets` indexe par `(row,col)` et n'en garde qu'un | `main_dialog.py:2738-2787`, `config_hud_layouts.py:396-399` |
| B3 | Seuils en `QSpinBox` entier 0–100, réécrits à chaque changement de propriété | Décimales tronquées, valeurs > 100 ramenées à 100 (bb/100, nombre de mains) | `main_dialog.py:347-353`, `2053`, `2086` |
| B4 | Renommer un panneau ou changer sa position réécrit `bgcolor` en `rgba(0,0,0,opacité)` même s'il était vide | Fond noir imposé sans que l'utilisateur l'ait demandé | `main_dialog.py:1892-1902` |
| B5 | Un stat-set à un seul `<block>` est chargé comme grille plate (`len(blocks) > 1`) | Libellés, lignes, titre et couleurs du bloc perdus à l'enregistrement ; état atteignable en supprimant des panneaux | `main_dialog.py:1009` |
| B6 | « Add Label » / « Add Line » sur un profil plat écrit dans `profile["texts"]`, que ni le canevas ni l'enregistrement ne lisent | L'élément disparaît sans message | `main_dialog.py:1709`, `2829`, `3025` |
| B7 | Cancel et Échap appellent `reject()` sans passer par `closeEvent` | Modifications perdues sans confirmation | `main_dialog.py:858`, `943` |
| B8 | `has_unsaved_changes` ignore les règles de profil et les règles de panneaux | Fermer après les avoir modifiées ne demande rien | `main_dialog.py:921-932` |
| B9 | Un profil nouveau ou dupliqué n'écrit pas `xpad`, `ypad`, `rich_text`, `font_size`, échelles | La copie d'un profil rich-text redevient standard | `main_dialog.py:1045-1073`, `4155-4191` |
| B10 | Barre d'état et attributs `rows`/`cols` du `<ss>` calculés sur l'agrégat `profile["stats"]`, jamais mis à jour en multi-panneaux | Compteur faux, dimensions périmées dans le XML | `main_dialog.py:895-907`, `4180` |
| B11 | Chaque modification reconstruit table, liste, canevas et aperçu ; la sélection revient au premier élément | Rend toute manipulation directe pénible | `main_dialog.py:1520-1678`, `2000` |
| B12 | `_refresh_after_group_edit` renomme l'entrée « (single grid) » en « (unnamed) » | Libellé faux après édition d'un élément de profil plat | `main_dialog.py:1908-1910` |
| B13 | `_canvas_add_item` passe `max_rows=max(cols, row+1)` ; « − » supprime l'élément le plus à droite sans confirmation | Liste de lignes incohérente, suppression accidentelle | `main_dialog.py:1752`, `1762` |
| B14 | `_add_panel_stat_to_block` place la stat en `(len(stats), 0)` | Grille gonflée de lignes vides | `main_dialog.py:3984` |
| B15 | « Text » d'une stat édite son nom interne en saisie libre ; « Popup » est un champ libre | Nom ou popup inexistant accepté sans contrôle | `main_dialog.py:2047`, `2082`, `326` |
| B16 | Libellés non traduits (« Group Properties », « Only current position », étiquettes de formulaire, boîtes de message) | i18n incomplète | `main_dialog.py:200`, `273-297` |
| B17 | Création de profil avec nom vide ou déjà pris : rien ne se passe | Aucun retour utilisateur | `main_dialog.py:2150`, `2167` |
| B18 | `title_font_scale` / `heading_font_scale` d'un `<block>` ne sont ni chargés ni réécrits | Perdus au premier enregistrement d'un profil multi-panneaux qui les porte | `main_dialog.py:1019-1041`, `2989-3000` |

### 1.3 Couverture actuelle (`coverage.json` local)

| Fichier | Couverture | Lignes non couvertes |
|---|---|---|
| `dialogs.py` | 16 % | 318 |
| `main_dialog.py` | 68 % | 619 |
| `preview_widgets.py` | 87 % | 66 |
| `design_canvas.py` | 97 % | 3 |

`tests/test_modern_hud_preferences.py` ne couvre que quatre cas de seuil vide.
La suite `qt` est désélectionnée par défaut et ne tourne que sur la CI Linux :
la logique doit donc être testable sans Qt.

## 2. Cible

Disposition conservée, un seul remplacement : la liste **Items** devient
**Available Stats** (la grille Design montre déjà le contenu du panneau).

```
┌ Panels ─┬ Group Properties ┬ Available Stats ┬ Item Properties ┐  ┌ HUD Preview ┐
│         │                  │ recherche       │ Item | Color    │  │             │
│         │                  │ catégories      │                 │  │             │
├─────────┴──────────────────┴─────────────────┴─────────────────┤  │             │
│ Design — grille à cellules, glisser-déposer                    │  │             │
│ [+ Row] [+ Column] [Edit Stat] [Remove] [Add Label] [Add Line] │  │             │
└────────────────────────────────────────────────────────────────┘  └─────────────┘
```

Règles d'interaction :

- Catalogue → cellule vide : ajoute la stat. Catalogue → cellule occupée : refusé, message dans la barre d'état.
- Élément → cellule vide : déplace. Élément → cellule occupée : échange les deux.
- Dépôt sous la dernière ligne : ajoute la ligne.
- Un élément large (`colspan`) n'est déposé que si toutes ses cellules sont libres ou appartiennent à l'élément échangé ; sinon refus.
- Une ligne de séparation occupe sa ligne entière et ne se déplace que verticalement.
- Clavier : flèches pour la sélection, Alt+flèches pour déplacer, Suppr pour retirer, Ctrl+Z / Ctrl+Maj+Z.
- Double-clic ou « Edit Stat » : dialogue d'édition, sans champs Row / Column.

Classes de HUD — trois notions à ne pas confondre :

| Notion | Portée | Emplacement dans l'UI |
|---|---|---|
| Présentation du profil (`rich_text`, `font_size`, `xpad`, `ypad`) | `<ss>` | Bandeau du profil, onglet Statistics |
| Gestionnaire de fenêtre (`ClassicHud`, `Simple_HUD`) | `<game aux=…>` | Affiché en lecture seule ; édition hors périmètre |
| Classe de popup | `<pu>` | Onglet Popup Windows, inchangé |

Les propriétés sans effet dans le mode choisi sont masquées, pas grisées.

## 3. Architecture

Nouveaux modules, tous dans `modern_hud_preferences/` :

| Module | Rôle | Qt |
|---|---|---|
| `layout_model.py` | Opérations sur un panneau : cellules occupées (avec `colspan`), `can_place`, `add`, `move`, `swap`, `remove`, `insert_row/col`, `delete_row/col`, `resize`, `normalize` | non |
| `profile_io.py` | `Stat_sets` ↔ dict éditeur ↔ nœuds XML, extrait de `_profile_from_stat_set` et `_write_profile_stats` | non (minidom) |
| `stat_catalog.py` | Catalogue : `Stats.STATLIST` + `Stats.get_valid_stats()` + `hud_panel_editor.stat_choices()`, catégorisé, filtrable | non |
| `stat_catalog_widget.py` | Recherche + arbre par catégorie, source de glisser | oui |
| `design_canvas.py` | Cellules vides réelles, `QDrag`, dépôt, clavier | oui |
| `undo.py` | Pile d'instantanés du profil courant (deepcopy, bornée à 50) | non |

Deux types MIME : `application/x-fpdb-hud-item` (déplacement) et
`application/x-fpdb-hud-stat` (copie depuis le catalogue).

Le canevas ne modifie jamais les données : il émet `move_requested`,
`add_requested`, `remove_requested` ; le dialogue appelle `layout_model`, puis
un rafraîchissement ciblé (canevas + aperçu + barre d'état) qui restaure la
sélection par identité de l'élément.

Compatibilité : `stat_table`, `_row_items` et `group_items_list` portent
aujourd'hui l'état de sélection et sont lus par `tests/test_pt4hud_import.py`.
Ils restent jusqu'au lot 4, alimentés par le même modèle, puis sont retirés et
ce test est adapté.

## 4. Lots

Un lot = une PR sur `development`, branche `feature/issues-N`.

### Lot 0 — Filet de sécurité
- Fixture `hud_config_copy` : copie temporaire de `HUD_config.xml.example`, jamais la configuration réelle.
- Test d'aller-retour : chaque `<ss>` livré, chargé puis enregistré sans modification, donne un `Stat_sets` équivalent (stats, blocs, textes, lignes, attributs).
- Tests de caractérisation marqués `xfail(strict=True)` pour B1 à B10, B14 et B18.
- Fabrique de dialogue hors écran avec `QMessageBox`, `QColorDialog`, `QInputDialog` remplacés ; aucun `.exec()` réel.

### Lot 1 — Modèle et intégrité des données
- `layout_model.py`, `profile_io.py`.
- Corrige B2, B4, B5, B6, B9, B10, B14, B18.
- Tout profil est représenté en blocs en mémoire ; un profil à un seul bloc sans titre ni couleur ni libellé reste écrit en `<stat>` plats, pour ne produire aucun diff sur les configurations existantes.
- Tests purs : chaque opération, `colspan`, collisions, bornes, aller-retour XML.

### Lot 2 — Sélection, rafraîchissement, modifications non enregistrées
- Sélection unique `(bloc, élément)` ; rafraîchissement ciblé ; fin de la reconstruction complète.
- `reject()` passe par la même confirmation que `closeEvent`.
- `has_unsaved_changes` couvre règles de profil, règles de panneaux, bascule dynamique.
- Indicateur « modifications non enregistrées » dans la barre d'état.
- Corrige B7, B8, B11, B12, B17 ; ajoute le renommage de profil.

### Lot 3 — Catalogue « Available Stats »
- `stat_catalog.py` et son widget à la place de la liste Items.
- Stats analytiques incluses avec leurs attributs `data_*` (réutilise `stat_entry_attributes`).
- Double-clic : ajout dans la première cellule libre du panneau sélectionné.
- Test : tout nom du catalogue est dans `STATLIST` ou est un choix analytique ; aucun doublon.
- Catégories : reprendre la table existante des popups catégorisés si elle couvre les stats, sinon table de préfixes dans `stat_catalog.py`. À trancher en début de lot.
- Corrige le catalogue codé en dur.

### Lot 4 — Glisser-déposer
- Cellules vides, `QDrag` avec aperçu de la puce, surbrillance de la cible, refus visible.
- Déplacement, échange, ajout depuis le catalogue, ajout de ligne par dépôt.
- Clavier, annuler / rétablir.
- `+ Row`, `+ Column`, suppression de ligne ou colonne vide ; retrait des boutons « + / − » par ligne (B13).
- Retrait de `stat_table`, `_row_items`, `group_items_list`.
- Tests : `QDropEvent` synthétiques sur les cellules (pas de `QDrag.exec`), résultat vérifié dans le modèle **et** dans le XML enregistré.

### Lot 5 — Propriétés et dialogue d'édition
- Dialogue « Edit Stat » sans position ; n'écrit que les champs modifiés (B1).
- Seuils en `QDoubleSpinBox` sans plafond à 100, case « utiliser des seuils » ; une stat non modifiée garde sa valeur d'origine au caractère près (B3).
- Statistique choisie dans le catalogue, popup dans la liste des popups existants (B15).
- Champs ajoutés : libellé affiché, préfixe, suffixe, info-bulle, action au clic.

### Lot 6 — Présentation du profil
- Bandeau : mode Standard / Rich text, taille de police, `xpad`, `ypad`.
- Gestionnaire de fenêtre du jeu affiché en lecture seule avec renvoi vers la configuration des jeux.
- Aperçu rendu selon le mode.

### Lot 7 — Finitions
- Passage de tous les libellés par `_()` (B16), mise à jour de `locale/`.
- Canevas de l'onglet Popup Windows : réordonnancement par glisser, à la place de Up / Down.
- `tools/capture_wiki_screenshots.py`, pages wiki, `coverage-baseline.json`.

## 5. Couverture visée

| Fichier | Aujourd'hui | Cible |
|---|---|---|
| `layout_model.py`, `profile_io.py`, `stat_catalog.py`, `undo.py` | — | ≥ 95 %, suite par défaut (sans Qt) |
| `design_canvas.py` | 97 % | ≥ 90 % après ajout du glisser-déposer |
| `dialogs.py` | 16 % | ≥ 80 % |
| `main_dialog.py` | 68 % | ≥ 80 % |

Chaque défaut B1–B17 a un test nommé qui échoue avant le correctif. Les tests
Qt sont lancés hors écran avec limite de temps avant chaque push.

## 6. Risques

| Risque | Parade |
|---|---|
| Régression d'écriture XML sur les configurations existantes | Aller-retour du lot 0 sur tous les `<ss>` livrés et sur les paquets `hud-packages/` |
| `QDrag.exec()` bloque en test | Dépôts synthétiques ; logique dans le modèle pur |
| Dialogue modal qui suspend la suite Qt | Aucune nouvelle fenêtre `.exec()` ; édition en ligne ou dialogues remplacés en test |
| Import `.fpdbhud` / PT4 dépend de la forme des dicts | `profile_io` garde les mêmes clés ; tests d'import existants conservés |
| `main_dialog.py` trop gros pour être revu | Extraction limitée à ce que chaque lot touche |

## 7. Décisions à confirmer

1. Remplacer la liste Items par Available Stats (retenu ici) plutôt que l'ouvrir dans un panneau séparé.
2. Dépôt du catalogue sur une cellule occupée : refus (retenu) plutôt que remplacement.
3. Choix du gestionnaire de fenêtre par jeu : lecture seule dans ce chantier (retenu), édition dans un chantier distinct.
