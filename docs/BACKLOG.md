# Backlog

État au 2026-08-07, après la 3.4.2. Chaque tâche porte la preuve qui l'a fait
remonter, de quoi la vérifier, et ce qui peut mal tourner.

Ordonné par rendement : ce qui lève un risque réel pour peu de travail d'abord.

---

## 1. iPoker : mains dupliquées sur les bases déjà importées

**Problème.** Le correctif du hand id iPoker (2026-07-25) a déplacé
`re_hand_info` de `sessioncode="…"` vers `gamecode="…"` — le premier motif
matchait aussi l'en-tête `<session sessioncode="…">` qui ouvre chaque fichier,
donnant à la première main de chaque fichier l'identifiant de session. Mesuré à
l'époque : 9 fichiers sur 9 touchés.

**Ce qui reste.** Le code est corrigé, **les données ne le sont pas**. Sur une
base déjà importée, la première main de chaque fichier iPoker porte encore
l'ancien identifiant. Un ré-import l'insère sous le bon sans écraser l'ancienne
ligne : une main dupliquée par fichier importé.

**Ne pas confondre avec l'outil livré en 3.4.2.**
`fpdb_3_legacy/fix_ipoker_duplicate_session_hands.py` (#193) travaille sur les
**fichiers XML du disque** : il repère les sessions dont tous les `gamecode`
sont déjà couverts par un fichier précédent et les supprime, de façon
déterministe. C'est utile *avant* import, et ça ne touche pas la base. La
migration des lignes déjà insérées n'existe toujours pas — les trois
`backfill_*` couvrent boards, showdown et autonotes, pas les identifiants.

**À faire.** Un script de maintenance qui repère, pour chaque fichier iPoker
importé, la main dont le `siteHandNo` égale un `sessioncode` du corpus, et la
supprime ou la réconcilie. À faire tourner une fois, avec un mode `--dry-run`.

**Risque.** Élevé : il supprime des lignes en base. Impose un `--dry-run` par
défaut, un décompte affiché avant action, et une sauvegarde documentée. À noter
que l'outil de 3.4.2 a fait le choix inverse — `--dry-run` y est un drapeau
optionnel, pas le défaut — parce qu'il ne touche que des fichiers que l'import
sait régénérer. Ce raisonnement ne tient plus dès qu'on écrit en base.

---

## 2. Découpage de `Database.py` — arrêté en cours de route

**État au 2026-08-07.** 2 231 lignes (2 413 avant la 3.4.2), plancher de
couverture 48,6 % (`coverage-baseline.json`, inchangé). `database_players` a
été extrait en #194, ce qui porte à sept les domaines sortis :
`database_aof`, `database_auto_notes`, `database_bulk_import`,
`database_caches`, `database_hud_stats`, `database_players`,
`database_schema`, `database_tournaments`. L'hôte reste gros.

**À faire.** Poursuivre par domaine, en vérifiant à chaque extraction que le
cliquet de complexité de `pyproject.toml` ne grossit pas : une extraction
déplace la dette, elle ne doit pas en créer.

```bash
ruff check --select C901,PLR0912,PLR0915 --isolated <fichiers>
```

**Risque.** Moyen. `Database.py` est au centre de l'import et du HUD ; toute
extraction doit laisser la suite complète verte.

---

## 3. Couverture du domaine `gui` — 37 %, le plus bas

**État.** `coverage-baseline.json` donne toujours 37,0 % pour `gui`, contre
83,6 % pour `poker-domain` et 86,6 % pour `platform-pkg`. Tiré vers le bas par
les points d'entrée : `fpdb.pyw`, `GuiSessionViewer`, `GuiLogView`,
`GuiAutoNotesWorkbench`, `ModernSeatPreferences`.

**Ce qui a bougé.** #195 a ajouté des tests unitaires sur le formatage et la
logique métier GUI (`tests/test_gui_formatting_and_business_logic.py`), et #197
un test Qt de non-régression sur les cartes de site. Le plancher n'a pas été
re-cliqueté : la valeur ci-dessus est le seuil, pas la couverture réelle
d'aujourd'hui. La régénérer fait partie du travail.

**À faire.** Cibler ce qui est testable sans fenêtre : la logique de sélection,
de formatage et de filtrage, en la séparant du câblage Qt. Le harnais `qt`
offscreen existe déjà et tourne en CI. Puis :

```bash
python tools/coverage_ratchet.py --update coverage.json
```

**Risque.** Faible, mais le rendement décroît vite — l'essentiel du code GUI
restant est du câblage.

---

## 4. `Configuration` lit son XML avec minidom

**Problème.** `Configuration.py` parse et réécrit la configuration avec
`minidom`, le parseur XML le plus lent de la stdlib. Sur un `HUD_config.xml` de
300 Ko, mesuré le 2026-08-06 :

| | |
|---|---|
| `defusedxml.minidom.parse` | 18,6 ms |
| `ElementTree.parse` | 2,7 ms |

Un seul `Config()` fait 566 000 appels de fonction, dont 244 000 dans
`_get_elements_by_tagName_helper` — `getElementsByTagName` étant une descente
récursive de tout le sous-arbre à chaque appel.

**Pourquoi ce n'est pas urgent.** #197 a supprimé l'essentiel du coût : les
deux parsings de l'exemple par `Config()` sont mis en cache, et `Config()`
s'exécute désormais une à deux fois par session au lieu de 27. Le gain restant
est donc de l'ordre de 16 ms, une fois.

**Pourquoi c'est quand même listé.** 12 fichiers de `fpdb_3_legacy/` (39 dans
tout le dépôt) manipulent le DOM, dont le **chemin d'écriture** de la
configuration ; `Configuration.py` à lui seul porte 134 appels DOM. C'est un
refactor transverse, pas une optimisation — délibérément écarté de #197 pour
cette raison.

**À faire.** Si c'est entrepris : sa propre PR, avec une couverture de
round-trip dédiée (lire → modifier → écrire → relire) avant de toucher au
parseur. La motivation réelle est la lisibilité et la sûreté du code de config,
pas la vitesse.

**Risque.** Élevé sur la persistance de la configuration utilisateur.

---

## 5. Provisionner les secrets de signature/notarisation macOS

**État.** Le workflow sait signer les releases avec Developer ID, hardened
runtime et entitlement Apple Events, puis notariser/stapler les deux variantes.
Il refuse désormais une release ad-hoc ou sans Team ID. Les builds ordinaires de
PR restent volontairement ad-hoc, les secrets n'étant pas exposés au code non
fiable.

**Effet mesuré.** Les traces de profilage d'une session 3.4.1 montrent les
chemins `/private/var/…/AppTranslocation/…` : chaque première ouverture d'une
fenêtre paie la validation Gatekeeper des ressources qu'elle charge.

**À provisionner.** Les six secrets décrits dans `docs/macos-gatekeeper.md`, en
utilisant le même certificat Developer ID Application pour PyInstaller,
PyOxidizer et toutes les releases suivantes.

**Pourquoi.** Une signature ad-hoc a une designated requirement liée au CDHash
du build. Même avec un `CFBundleIdentifier` stable, TCC ne peut donc pas
réutiliser les autorisations Screen Recording/Accessibility entre versions.

---

## 6. Points en attente de validation live

Ni corrigeables ni vérifiables sans une session de jeu réelle :

- **Bug PokerStars cash sous Windows** — durci, jamais confirmé. Les trois
  autres bugs de la même série sont validés.
- **Synthèse ring iPoker** (PMU / bwin 6-max).
- **Ancrage bas-centre du HUD** sur un Twister 2/3-max.

À traiter quand l'occasion se présente ; rien à faire d'ici là.

---

## 7. Traductions

13 des 14 locales livrées ne sont pas traduites — seul le français l'est. Le
pipeline gettext, le sélecteur de langue et l'extraction fonctionnent : il ne
manque que le contenu des catalogues. Tâche de traduction, pas de
développement.

À noter depuis la 3.4.2 : #198 a corrigé la résolution de langue elle-même —
une configuration sans `ui_language` retombe sur `system` et non sur l'anglais,
donc les configs anciennes ne sont plus épinglées aux chaînes non traduites.

---

## Fait en 3.4.2

Vérifié dans l'arbre, pas seulement dans les messages de commit :

- **Liste `known_failures` purgée** (#190) — `tests/conftest.py` ne contient
  plus le bloc ; la suite ne rapporte plus aucun `XPASS` (7 394 passed contre
  7 328 passed + 9 xpassed avant).
- **`uncalledbets` supprimé** (#191) — plus aucune occurrence dans le code
  applicatif ; seule une mention subsiste dans un docstring de
  `tests/helpers/mock_hand.py`. La branche « supprimer » a été retenue plutôt
  que « câbler sur `handle_leftover` », et `tests/test_uncalled_bets_real_hands.py`
  couvre désormais la comptabilité sur mains réelles.
- **Les tests `perf` ont un point d'exécution** (#192) —
  `.github/workflows/ci.yml:368` lance `python -m pytest -m perf`, sur Linux
  seulement et en `continue-on-error`. Les budgets en temps mural sont trop
  sensibles à la charge des runners partagés pour bloquer un merge, mais le
  résultat apparaît dans le log.
- **Attribution PartyPoker** (#196) — les mains vont au skin configuré et non
  au dernier `<hhc>` du fichier de config.
- **Performance des popups** (#197) — profilage passé en opt-in
  (`FPDB_PROFILE=1`), Site Preferences ne balaie plus le disque par carte,
  la connexion base survit au rechargement de config.

---

## Vérifié comme fait, avant la 3.4.2

Relu depuis l'historique git avant suppression des anciens plans :

- **i18n** — `modern_hud_preferences/` porte 167 appels `_()`, et les libellés
  écrits en dur en français dans `ring_stats/` ont disparu.
- **Scripts d'exploitation** — passés de 0 % à un plancher de 44,5 %
  (`tests/test_maintenance_scripts.py`).
- **Hand id iPoker** — corrigé côté code ; seule la migration des données reste
  (tâche 1).
- **Version affichée par les binaires** — l'ancien repli `"3.0.0alpha"` de
  `fpdb.pyw` a été supprimé en `a5c3a435` ; `_resolve_version()` retombe sur
  `fpdb_3_legacy.__version__`.
