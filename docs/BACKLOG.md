# Backlog

État au 2026-08-06, après la 3.4.1. Chaque tâche porte la preuve qui l'a fait
remonter, de quoi la vérifier, et ce qui peut mal tourner.

Ordonné par rendement : ce qui lève un risque réel pour peu de travail d'abord.

---

## 1. Purger la liste `known_failures` — les 10 tests passent

**Problème.** `tests/conftest.py:95` marque 10 tests en `xfail` via une liste
codée en dur, avec le motif « Known legacy failure present in master branch ».
Les 10 passent aujourd'hui.

Le hook `pytest_collection_modifyitems` est au niveau session : il s'applique
donc aussi aux fichiers de `test/`, pas seulement à `tests/`. D'où les 9 `XPASS`
de chaque exécution ; le dixième
(`test_rangechartpopup_is_popup_subclass`) porte le marqueur `qt` et n'apparaît
pas dans la suite par défaut.

**Pourquoi ça compte.** Ces `xfail` ne sont pas `strict`. Une régression réelle
sur l'un de ces 10 tests serait rapportée comme échec *attendu*, et la CI
resterait verte. Dix tests protègent donc actuellement du vide.

**À faire.** Supprimer le bloc `known_failures` et le `add_marker` associé. Si
un test s'avère réellement instable, le marquer individuellement dans son
fichier avec `strict=True` et une raison datée — pas dans une liste centrale
que personne ne relit.

**Vérifier.**

```bash
python -m pytest test tests -q -rX
```

Zéro `XPASS` attendu, et le total de `passed` augmente de 9.

**Risque.** Faible. Si un test échoue vraiment après retrait, c'est une
information qu'on n'avait pas.

---

## 2. `uncalledbets` : un signal écrit 37 fois, jamais lu

**Problème.** 16 parsers appellent `hand.setUncalledBets(...)` et
`fpdb_3_legacy/iPoker/base.py` écrit l'attribut directement. Le setter est
`Hand.py:1444`, l'initialisation `Hand.py:143`. Aucune lecture nulle part :

```bash
git grep -n "uncalledbets" -- '*.py' '*.pyw' | grep -vE "uncalledbets\s*="
```

ne retourne rien.

**Pourquoi ça compte.** Les parsers signalent si la room a déjà retiré les mises
non suivies, et le signal est jeté. C'est exactement la décision que
`Hand.totalPot()` prend à l'aveugle dans `handle_leftover` (`Hand.py:1555`) en
comparant `totalcollected` au pot — la logique qui s'est mal branchée sur
PartyPoker et a fait enregistrer un pot entier en rake pendant des mois.

**Attention.** Le rapprochement est plausible, pas démontré. Avant de câbler le
drapeau sur `handle_leftover`, il faut retracer l'intention d'origine : le
comportement actuel est *deviné* mais correct sur les 85 goldens PartyPoker et
tout le corpus. Deux issues défendables :

- brancher le drapeau et vérifier qu'aucun golden ne bouge (s'il en bouge, on
  aura trouvé d'autres rooms mal parsées) ;
- ou constater qu'il ne sert plus et supprimer les 37 appels plus le setter.

Ce qu'il ne faut pas faire : le laisser en l'état, où il donne l'illusion d'un
mécanisme actif.

**Vérifier.** Suite complète plus les goldens, avant/après :

```bash
python -m pytest test/test_live_parser_regression.py -q
```

**Risque.** Moyen si on câble : touche la comptabilité des pots de toutes les
rooms. Nul si on supprime.

---

## 3. 12 tests `perf` n'ont aucun point d'exécution

**Problème.** `test/test_popup_performance.py` porte `pytestmark =
pytest.mark.perf`. `pytest.ini` déselectionne `perf` dans ses `addopts`, et les
deux invocations pytest de la CI (`.github/workflows/ci.yml:348` et `:416`)
portent `-m "not qt and not perf"`. Aucune étape ne les lance — contrairement
aux tests `qt`, qui ont la leur.

**État.** Ils passent aujourd'hui (12/12, vérifié le 2026-08-06), mais rien ne
le garantirait s'ils cessaient de le faire.

**À faire.** Soit ajouter une étape CI `-m perf` sur le modèle de l'étape `qt`,
soit les supprimer. Un test de performance sans seuil ni exécution ne mesure
rien.

**Vérifier.**

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -m perf -q
```

**Risque.** Faible. À noter s'ils entrent en CI : ce sont des mesures de temps,
donc sensibles à la charge du runner. Prévoir des seuils larges.

---

## 4. iPoker : mains dupliquées sur les bases déjà importées

**Problème.** Le correctif du hand id iPoker (2026-07-25) a déplacé
`re_hand_info` de `sessioncode="…"` vers `gamecode="…"` — le premier motif
matchait aussi l'en-tête `<session sessioncode="…">` qui ouvre chaque fichier,
donnant à la première main de chaque fichier l'identifiant de session. Mesuré à
l'époque : 9 fichiers sur 9 touchés.

**Ce qui reste.** Le code est corrigé, **les données ne le sont pas**. Sur une
base déjà importée, la première main de chaque fichier iPoker porte encore
l'ancien identifiant. Un ré-import l'insère sous le bon sans écraser l'ancienne
ligne : une main dupliquée par fichier importé.

Aucun script ne traite ça — les trois `backfill_*` couvrent boards, showdown et
autonotes, pas les identifiants.

**À faire.** Un script de maintenance qui repère, pour chaque fichier iPoker
importé, la main dont le `siteHandNo` égale un `sessioncode` du corpus, et la
supprime ou la réconcilie. À faire tourner une fois, avec un mode `--dry-run`.

**Risque.** Élevé : il supprime des lignes en base. Impose un `--dry-run` par
défaut, un décompte affiché avant action, et une sauvegarde documentée.

---

## 5. Découpage de `Database.py` — arrêté en cours de route

**État.** 2 413 lignes, plancher de couverture 48,6 % (`coverage-baseline.json`).
C'était le seul chantier explicitement marqué « en cours » dans les plans
supprimés. Plusieurs domaines ont bien été extraits — `database_bulk_import`,
`database_caches`, `database_hud_stats`, `database_schema`,
`database_tournaments` — mais l'hôte reste gros.

**À faire.** Poursuivre par domaine, en vérifiant à chaque extraction que le
cliquet de complexité de `pyproject.toml` ne grossit pas : une extraction
déplace la dette, elle ne doit pas en créer.

```bash
ruff check --select C901,PLR0912,PLR0915 --isolated <fichiers>
```

**Risque.** Moyen. `Database.py` est au centre de l'import et du HUD ; toute
extraction doit laisser la suite complète verte.

---

## 6. Couverture du domaine `gui` — 37 %, le plus bas

**État.** `coverage-baseline.json` donne 37,0 % pour `gui`, contre 83,6 % pour
`poker-domain` et 86,6 % pour `platform-pkg`. Tiré vers le bas par les points
d'entrée : `fpdb.pyw`, `GuiSessionViewer`, `GuiLogView`,
`GuiAutoNotesWorkbench`, `ModernSeatPreferences`.

**À faire.** Cibler ce qui est testable sans fenêtre : la logique de sélection,
de formatage et de filtrage, en la séparant du câblage Qt. Le harnais `qt`
offscreen existe déjà et tourne en CI.

**Risque.** Faible, mais le rendement décroît vite — l'essentiel du code GUI
restant est du câblage.

---

## 7. Points en attente de validation live

Ni corrigeables ni vérifiables sans une session de jeu réelle :

- **Bug PokerStars cash sous Windows** — durci, jamais confirmé. Les trois
  autres bugs de la même série sont validés.
- **Synthèse ring iPoker** (PMU / bwin 6-max).
- **Ancrage bas-centre du HUD** sur un Twister 2/3-max.

À traiter quand l'occasion se présente ; rien à faire d'ici là.

---

## 8. Traductions

13 des 14 locales livrées ne sont pas traduites — seul le français l'est. Le
pipeline gettext, le sélecteur de langue et l'extraction fonctionnent : il ne
manque que le contenu des catalogues. Tâche de traduction, pas de
développement.

---

## Vérifié comme fait, malgré ce que disaient les plans supprimés

Relu depuis l'historique git avant suppression :

- **i18n** — `modern_hud_preferences/` porte 167 appels `_()`, et les libellés
  écrits en dur en français dans `ring_stats/` ont disparu.
- **Scripts d'exploitation** — passés de 0 % à un plancher de 44,5 %
  (`tests/test_maintenance_scripts.py`).
- **Hand id iPoker** — corrigé côté code ; seule la migration des données reste
  (tâche 4).
- **Version affichée par les binaires** — l'ancien repli `"3.0.0alpha"` de
  `fpdb.pyw` a été supprimé en `a5c3a435` ; `_resolve_version()` retombe sur
  `fpdb_3_legacy.__version__`.
