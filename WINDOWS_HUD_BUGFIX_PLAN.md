# Plan de correction — 4 bugs HUD/détection Windows (2026-07-22)

Analyse basée sur : le code (`fpdb_3_legacy/`), la config utilisateur (`%APPDATA%\fpdb\HUD_config.xml`),
la base SQLite (`%APPDATA%\fpdb\database\fpdb.db3`, mains du 2026-07-21), les logs
(`%APPDATA%\fpdb\log\HUD-errors.txt`) et les hand histories locales des clients.

---

## Constat transversal (bloquant pour le diagnostic) : la journalisation fichier est morte

- `fpdb-log.txt` ne contient **rien depuis le 03/07/2026** (une seule ligne : erreur de version DB),
  alors que des sessions complètes ont eu lieu le 21/07. Seul `HUD-errors.txt` (redirection stderr,
  niveau ERROR uniquement) capture quelque chose.
- Conséquence : tous les chemins de sortie « silencieux » (log.info / log.warning) sont invisibles,
  notamment `HUD not created yet, because hero is not seated` (INFO) et
  `Currently open windows: [...]` (WARNING, la liste des titres de fenêtres — exactement ce qu'il
  faut pour diagnostiquer les bugs 1 et 4).

**Étape 0 (à faire en premier)** — ✅ FAIT (2026-07-22)

Causes racines trouvées pendant l'implémentation :
- root logger à ERROR (`setup_logging`) + niveaux registry ≥ ERROR → seuls les ERROR
  atteignaient les fichiers ;
- `HUD-log.txt` écrit dans `~/.fpdb/log` (pas `%APPDATA%\fpdb\log`), niveau ERROR,
  et attaché au seul logger `hud_main` → les WARNINGs de `win_tables`/`table_window`
  (dont « Currently open windows ») n'atteignaient aucun fichier ;
- `doRollover` : un rename refusé (fichier verrouillé par le 2ᵉ process fpdb/HUD) laissait
  `rolloverAt` dans le passé → chaque emit() retentait la rotation, échouait → logging mort.

Fixes livrés : cap WARNING sur les niveaux appliqués par le registre (`cap_logger_level`),
root logger à WARNING (console inchangée à ERROR), HUD-log dans `CONFIG_PATH/log` avec
handler fichier partagé sur le root, rotation tolérante au verrouillage, et traces WARNING
pour chaque raison de skip HUD (table_info absent, héros non assis, fenêtre blacklistée).
Tests : `test/test_logging_diagnostics.py` (7 tests).
1. Diagnostiquer pourquoi `TimedSizedRotatingFileHandler` (`fpdb_3_legacy/loggingFpdb.py:1187`,
   config ~ligne 1457) n'écrit plus après la rotation du 03/07 (verrou multi-process Windows
   fpdb + HUD_main sur le même fichier est le suspect n°1 ; le nom de rotation
   `fpdb-log.txt-03-07-2026-part1.txt` avec mtime incohérent indique une rotation qui a mal tourné).
   - Fix probable : un fichier de log distinct par process (`fpdb-log.txt` / `HUD-log.txt`),
     et handler tolérant aux erreurs (ne jamais tuer silencieusement le logging).
2. Dans `HUD_main.pyw::read_stdin/_create_new_hud`, tracer **chaque raison de skip** en WARNING
   (une ligne : hand id, table, raison). En particulier passer le skip « hero is not seated »
   (HUD_main.pyw:841-843) de INFO à WARNING.
3. Quand `find_table_parameters()` échoue, la liste `Currently open windows` (WinTables.py:218-222)
   doit être visible dans un log persistant (elle donne les titres exacts → indispensable pour
   les bugs 1 et 4).

Tests : test unitaire de rotation du handler (simuler 2 process) ; test que chaque `return` de
`read_stdin`/`_create_new_hud` logge une raison.

---

## Bug 1 — PokerStars : cash game non détecté, tournoi OK — 🟡 DURCI, CONFIRMATION EN SESSION LIVE (2026-07-22)

Diagnostic hors ligne effectué en rejouant le chemin exact de read_stdin/_create_new_hud
sur les 2 mains « Isabella II » stockées en base :
- table_info OK, profil de jeu omahahi/ring OK, héros `jeje_sat` assis → True, stats OK
  (identique au contrôle ACR/Arimo qui fonctionne) → le pipeline données est SAIN ;
- aucune erreur « Can't find table » ni « HUD create: not found » dans les logs de la
  session (alors que ces chemins loggent en ERROR et l'ont fait pour CoinPoker/ACR le même
  jour) → la fenêtre a très probablement été TROUVÉE et le HUD créé, puis tué par le check
  de visibilité ou rendu invisible/mal placé. La ligne isolée « The window 984794 is not
  valid or visible » dans HUD-errors est compatible avec un kill précoce.
Suspect identifié : le commit cf615fdf (21/07 12:25, AVANT la session) a étendu le check
DWM-cloak à TOUS les sites — une fenêtre cloaked (autre bureau virtuel, transitions DWM)
tuait le HUD de n'importe quelle room.

Durcissements livrés :
1. `is_window_visible` (détecteur Windows) revient à la sémantique Win32 pure pour le poll
   générique ; le check cloak est isolé dans `is_window_displayed`, utilisé uniquement par
   les chemins CoinPoker (intention de cf615fdf préservée) et le filtre d'attache.
2. Trace WARNING « HUD attach: table/hwnd/title/geometry » à chaque création de HUD.
3. L'erreur « window not valid or visible » inclut désormais la table et la search string.
Avec l'étape 0, la prochaine session Stars cash produira soit un HUD fonctionnel, soit un
diagnostic complet (fenêtre matchée + raison du kill) dans HUD-log.txt.

**Faits établis**
- Mains importées (DB : `Isabella II`, ring omahahi, 21/07 12:38, heroSeat=2, fast=0,
  site `PokerStars.FR` activé, screen_name `jeje_sat` correct).
- Regex de recherche cash = `re.escape("Isabella II")` (PokerStarsToFpdb.py:2400) — devrait
  matcher un titre standard « Isabella II - €0.01/€0.02 EUR - Pot Limit Omaha ».
- **Aucune** erreur `Can't find table "Isabella II"` dans HUD-errors.txt alors que l'échec de
  détection fenêtre logge en ERROR (TableWindow.py:204-207 et HUD_main.pyw:849-858).
  → Le code n'est probablement **jamais arrivé à la recherche de fenêtre** : le HUD a été
  sauté par un chemin silencieux en amont. Candidats (par ordre de probabilité) :
  a) `hero is not seated` (HUD_main.pyw:841) — stat_dict sans le héros (INFO, invisible) ;
  b) `_get_table_info()` → None (course DB : main pas encore commitée quand le HUD lit) —
     retour silencieux sans retry (HUD_main.pyw:902-904) ;
  c) titre de fenêtre réellement différent (client Stars récent) — alors l'ERROR apparaîtra
     une fois le logging réparé.

**Implémentation**
1. Dépend de l'Étape 0 : rejouer une session cash Stars et lire la raison tracée.
2. Fix (b) préventif, quelle que soit l'issue : dans `read_stdin`, si `table_info` est None,
   re-tenter (2-3 essais espacés de ~0.5 s) avant d'abandonner — le cache ne mémorise déjà pas
   les None (HUD_main.pyw:663-668), il manque juste le retry.
3. Fix (a) si confirmé : examiner `get_stats_from_hand` pour un gametype fraîchement créé
   (HudCache pas encore peuplé) — le stat_dict doit toujours contenir les joueurs de la main
   courante même sans historique.
4. Fix (c) si confirmé : élargir `PokerStarsToFpdb.getTableTitleRe` (cash) au nouveau format de
   titre constaté (et test unitaire avec les titres réels capturés).

Fichiers : `HUD_main.pyw`, `PokerStarsToFpdb.py`, `Database.py` (si (a)).
Test : session live Stars cash + tournoi (non-régression kickoff).

---

## Bug 2 — PMU (iPoker) : cash détecté mais HUD placé n'importe où ; twister OK — ✅ FAIT (2026-07-22)

Cause exacte trouvée : seul le 1er "hand split" d'un fichier contient l'en-tête de session,
donc seul lui passe par le chemin regex standard (qui lit `<tablesize>`). Toutes les mains
suivantes (blocs `<game>` nus — c.-à-d. TOUTES les mains de l'auto-import live) passent par
`_parse_xml_format`, qui ne lisait pas `<tablesize>` → `guessMaxSeats()` → 10 (iPoker numérote
les sièges d'une 6-max jusqu'à 10). Fix : `_parse_xml_format` lit `<tablesize>` depuis le
header de session et renseigne `info["seats"]` (même contrat que le chemin standard).
Validé sur les fichiers réels du 21/07 : Sea Lake → 6 sur les 5 mains ; Twister → 3 sur les
9 mains. Tests : `test/test_ipoker_maxseats_incremental.py` (5 tests).
Note : les `€` corrompus (`Twister 0.25�`) viennent du client PMU lui-même (le fichier
contient U+FFFD) — rien à corriger côté fpdb ; le client bwin plus récent écrit des `€` valides.

**Cause racine (prouvée par la DB)**
- Table « Sea Lake » = 6-max, or les Gametypes des mains importées oscillent :
  1ʳᵉ main `maxSeats=6`, les suivantes `maxSeats=10`.
- Mécanique : `<tablesize>6</tablesize>` n'existe que dans l'en-tête `<session>` du XML.
  Sur les mains suivantes (import incrémental), `re_max_seats` ne matche pas le bloc `<game>`
  et le fallback `whole_file` (iPoker/base.py:534-538) ne fonctionne pas dans tous les chemins
  → `guessMaxSeats()` (HandHistoryConverter.py:832) prend le **numéro de siège max occupé** ;
  or iPoker numérote les sièges d'une 6-max jusqu'à 10 (cf. layout `max="6"`
  `hist_seat="1,3,5,6,8,10"` dans HUD_config) → renvoie **10**.
- Conséquences HUD : layout `max=10` appliqué à une table 6-max → positions des stats fausses
  (« en dehors de la table ») + churn kill/recreate du HUD à chaque flip 6↔10
  (`new_max_seats`, HUD_main.pyw:713-735). Le twister passe par le layout tour 3-max → OK
  (même si ses gametypes montrent aussi le flip 3→10 : même bug parser, symptôme masqué).

**Implémentation**
1. `fpdb_3_legacy/iPoker/hand_info.py` + `base.py` :
   - mémoriser `self.maxseats` dès que `<tablesize>` est lu (1ʳᵉ passe du fichier) et le
     réutiliser pour toutes les mains suivantes de la même session/fichier (le champ existe :
     `self.maxseats`, mais n'est renseigné que pour les tournois — l'étendre au ring,
     hand_info.py:310-324) ;
   - vérifier que **tous** les chemins de `determineGameType` utilisent le fallback
     `whole_file` pour `re_max_seats` (il y a deux chemins : base.py:526 et base.py:1094) ;
   - en dernier recours ring iPoker : ne jamais « deviner » via le n° de siège max ; mapper
     l'ensemble des sièges occupés sur les numérotations iPoker connues
     ({1..10} clairsemé → 6-max si sièges ⊆ {1,3,5,6,8,10}, etc.).
2. Nettoyage DB utilisateur (optionnel, doc) : les Gametypes 10-max erronés existants
   continueront d'être réutilisés pour les vieilles mains ; les nouvelles mains iront sur le bon.
3. Bonus robustesse HUD : quand `new_max_seats` change plusieurs fois pour une même table cash,
   SmartHudManager devrait refuser le 2ᵉ restart dans un intervalle court (anti-churn).

Tests : test unitaire parsant le XML « Sea Lake » réel en deux temps (fichier complet puis
main ajoutée avec `index > 0`) → `maxseats == 6` sur toutes les mains ; idem twister → 3.
Encodage : au passage corriger le `€` mal décodé dans les noms twister (`Twister 0.25�` en DB —
vérifier le codepage de lecture des XML iPoker).

---

## Bug 3 — bwin.fr (migré iPoker) : aucune détection de main ni de table — ✅ FAIT (2026-07-22)

Livré :
1. Migration idempotente dans `Config.__init__` (`_migrate_entain_fr_sites_to_ipoker`) :
   network PartyPoker→iPoker, hhc → iPokerToFpdb/iPokerSummary, HH_path/TS_path repointés
   vers `%LOCALAPPDATA%\bwin Poker France\data\<compte>\History\Data`, screen_name corrigé
   depuis le nom du dossier compte, layout_set party_default → ipoker_default (répare aussi
   les configs semi-migrées). Sauvegarde `.backup` avant réécriture.
2. Dispatcher iPoker : indicateurs de chemin « bwin poker france » / « bwinfr » ajoutés au
   skin BwinFrIPoker (sinon les mains tombaient sur le site générique « iPoker »).
3. DetectInstalledSites : alias de dossier Windows (`WINDOWS_IPOKER_DATA_DIR_ALIASES`).
4. IdentifySite : résolution de skin iPoker par chemin (`_select_ipoker_skin_site`,
   généralisation du helper WPN).
La config réelle de l'utilisateur a été migrée (original conservé :
`HUD_config.xml.bak-premigration-bwin-20260722`). Vérifié sur les fichiers bwin réels du
21/07 : skin « Bwin.fr Poker », site_id 40, ring omahahi 6-max sur les 6 mains.
Tests : `test/test_bwin_fr_ipoker_migration.py` (13 tests).

**Cause racine (prouvée par la config)** — la config utilisateur est antérieure à la migration :
```xml
<site site_name="Bwin.fr Poker" enabled="True" screen_name="jejsat76"
      HH_path="C:\Users\jd\AppData\Local\PMU Poker\data\tripsfountain99\...\Tables"  ← dossier PMU !
      network="PartyPoker">
<hhc site="Bwin.fr Poker" converter="PartyPokerToFpdb"/>                             ← ancien parser
```
Le nouveau client écrit bien des XML iPoker dans :
`C:\Users\jd\AppData\Local\bwin Poker France\data\jejesat76\History\Data\Tables\*.xml`
(vérifié : mains du 21/07 15:18, table « Smithton », nickname `jejesat76` — noter le **typo**
`jejsat76` dans la config). Le repo est déjà correct (HUD_config.xml racine : network iPoker +
`iPokerToFpdb`, skin `BwinFrIPoker` site_id 40, DetectInstalledSites connaît « Bwin.fr Poker »).
Il manque la **migration des configs existantes** et la détection du chemin Windows.

**Implémentation**
1. `ConfigurationManager`/démarrage : étape de migration idempotente —
   si `site_name="Bwin.fr Poker"` a `network="PartyPoker"` ou `<hhc ... converter="PartyPokerToFpdb">`,
   réécrire : `network="iPoker"`, hhc → `iPokerToFpdb`/`iPokerSummary`, et si le HH_path ne
   contient pas `bwin`, proposer/appliquer le chemin détecté
   (`AppData\Local\bwin Poker France\data\<pseudo>\History\Data\Tables`, TS → `...\Tournaments`,
   screen_name = nom du dossier `<pseudo>`).
2. `DetectInstalledSites.py` : ajouter le chemin **Windows** du skin « Bwin.fr Poker »
   (`%LOCALAPPDATA%\bwin Poker France\data\<user>\History\Data\...`) — aujourd'hui seul le
   conteneur macOS est géré (lignes ~490-511).
3. `IdentifySite.py` : résolution de skin iPoker **par chemin** (comme
   `_select_winning_skin_site`, ligne 260) avant le sniffing de contenu `detectiPokerSkin`
   (le XML bwin n'a aucun marqueur de skin → aujourd'hui il serait attribué à « iPoker »
   générique, voire « PMU Poker »). Priorité : HH_path configuré le plus spécifique.
4. Réparer la config de l'utilisateur (à la main ou via la migration 1) + corriger le typo
   `jejsat76` → `jejesat76`.

Le HUD suivra ensuite le chemin iPoker standard (titres « Smithton » = même logique que PMU ;
la regex twister inclut déjà l'alternative `Spins` utilisée par les skins FR).

Tests : unitaire de migration (config PartyPoker → iPoker) ; IdentifySite sur un XML bwin réel
avec HH_path bwin configuré → site « Bwin.fr Poker » ; import bout-en-bout du fichier du 21/07.

---

## Bug 4 — ACR : cash OK, Spinz importé mais table non détectée / HUD absent — ✅ FAIT (2026-07-22)

Cause plus profonde que prévu : les fichiers `SPINZID` n'étaient pas reconnus comme un type
de tournoi (absents de `re_File2` et du bloc nom-de-tournoi de `_readHandInfo2`) →
`Tourneys.tourneyName` restait NULL → impossible de distinguer un Spinz d'un MTT au moment
de construire la regex de titre. Livré :
1. `WinningToFpdb` : prise en charge de SPINZID (isSng, isLottery, tourneyName depuis le
   nom de fichier avec décodage `{FULLSTOP}`/`{BACKSLASH}`, buy-in) ; la couche DB backfille
   `tourneyName` sur les tournois existants au prochain import.
2. `getTableTitleRe` accepte `tourney_name` ; pour un nom contenant Spinz/Jackpot, regex en
   alternance : format MTT classique | marque (Spinz|Jackpot)+numéro de tournoi |
   marque+montant du buy-in (séparateur `.` ou `,`). Les MTT/cash gardent la regex actuelle
   à l'identique (y compris les anciens tournois avec tourneyName NULL).
Itération 2 (2026-07-22 soir) : titre réel capturé par le logging étape 0 —
`$0.25 - No Limit - 10 / 20 Hold'em (35548425)` — aucune marque « Spinz » dans le titre.
Ajout de l'alternative décisive : numéro de tournoi entre parenthèses `\(tourno\)`
(sûr pour un Spinz : table unique, pas de fenêtre lobby de tournoi ; les MTT gardent le
format strict). Vérifié contre les titres réels de la session du 22/07 (table matchée,
lobby ACR/fenêtres HUD non matchés).
Tests : `test/test_winning_spinz.py` (18 tests).

**Cause racine (prouvée par HUD-errors.txt)**
```
Can't find table "35539941 1" with search string ", Table 1\s\-.*\s\(35539941\)"
```
La regex tournoi de `WinningToFpdb.getTableTitleRe` (WinningToFpdb.py:1818-1834) exige le format
historique « ..., Table 1 - ... (35539941) ». Le client ACR actuel ne titre pas les tables Spinz
ainsi (HH : `Tournament #35539941`, `TN-$0.25 Spinz Holdem`, table « 1 » 3-max). Le MTT classique
du même jour (35528538) n'apparaît pas en erreur → le format Spinz est le cas divergent
(équivalent du cas « Twister » déjà spécial-casé côté iPoker, iPoker/base.py:1327-1342).

**Implémentation**
1. `WinningToFpdb.getTableTitleRe` :
   - accepter le paramètre `tourney_name` (le wrapper `getTableTitleRe` filtre déjà les kwargs
     selon la signature — HandHistoryConverter.py:1080-1089 — et TableWindow le transmet) ;
   - si `tourney_name`/`table_name` contient `spinz`/`jackpot` (insensible à la casse) :
     regex alternative `(?:<tourney_name échappé>|Spinz.*?<tourno>|<tourno>)` au lieu du
     format « , Table N - ... (tourno) » ;
   - conserver le format historique en alternative pour ne pas casser les MTT.
2. Capturer le titre réel (Étape 0 : `Currently open windows` enfin visible) et ajuster la
   regex sur le vrai format avant de figer le test.
3. Vérifier `getTableNoRe` (multi-tables Spinz improbable : 3-max, table unique — le
   `tableno_re` par défaut `tourno.+(?:Table|Torneo) (\d+)` ne matchera pas le titre Spinz ;
   `has_table_title_changed` doit rester inoffensif quand il ne matche pas → c'est le cas,
   `get_table_no()` renvoie False).

Tests : unitaires `getTableTitleRe` Winning — MTT (format actuel inchangé), Spinz (nouveau),
cash (inchangé) ; session live Spinz pour valider le titre réel.

---

## Ordre d'exécution proposé

| # | Tâche | Dépend de | Effort |
|---|-------|-----------|--------|
| 0 | Réparer logging + traces de skip HUD | — | 0.5-1 j |
| 1 | Bug 2 PMU maxseats (parser iPoker + tests) | — | 0.5-1 j |
| 2 | Bug 3 bwin.fr (migration config + chemin Windows + skin par chemin) | — | 1 j |
| 3 | Bug 4 ACR Spinz (regex Winning + tourney_name) | 0 (titre réel) | 0.5 j |
| 4 | Bug 1 Stars cash (diagnostic puis fix ciblé) | 0 | 0.5 j + session de repro |

Chaque fix = commit séparé avec test de non-régression ; validation finale = une session live
par room (Stars cash+tournoi, PMU cash+twister, bwin.fr cash, ACR cash+Spinz).

---

## Bilan de validation live (2026-07-22 soir)

- ✅ Bug 2 PMU maxseats — validé par l'utilisateur.
- ✅ Bug 3 bwin.fr — validé (log : `HUD attach: table='Sea Lake, 560237915' site=Bwin.fr Poker`).
- 🟡 Bug 1 Stars cash — durci ; le log du 22/07 montre un attach réussi
  (`HUD attach: table='Gyas' site=PokerStars.FR`, titre réel
  `Poker Time Left: 166h:52m Gyas - Pot Limit Omaha €0.01/€0.02 EUR - Logged In as jeje_sat`).
- ✅ Bug 4 ACR Spinz — itération 2 (`0b965769`) après capture du titre réel ; à revalider
  au prochain spin.

---

## À FAIRE — chantiers découverts pendant le diagnostic

### A. iPoker (PMU/bwin) : mains anonymisées « Player N » quand le héros ne joue pas — ✅ FAIT (2026-07-22, modèle corrigé)

**Modèle réel (prouvé sur le fichier bwin `5870214435.xml`, table « Scone ») :** une main
iPoker est anonymisée (`Player N` partout) **uniquement quand le héros n'est PAS distribué**.
Dès qu'il joue la main, tous les noms sont réels. « Player N » = « Player \<siège\> »
exactement, et **aucune carte n'est jamais révélée** :
```
main 9026868234  héros absent  -> 3=Player 3, 5=Player 5, 6=Player 6, 8=Player 8, 10=Player 10
main 9026877611  héros présent -> 1=jejesat76, 3=CR7012, 5=Moula42, 8=TheDarkRaise, 10=confusius5
```
Il n'y a donc **jamais de héros anonyme à récupérer** : les mains anonymes sont exactement
celles que le héros a sautées. (La 1ʳᵉ approche « retrouver le héros par ses cartes » était
fondée sur une hypothèse fausse — abandonnée.)

Livré (`fpdb_3_legacy/iPoker/hand_info.py`, passe de dé-anonymisation en tête de
`readHandInfo`, avant que `markStreets`/`readBlinds`/`readAction`/`readHoleCards`/
`readCollectPot` ne relisent les noms — une réécriture unique de `hand.handText`) :
1. **Table siège→vrai nom de session** (`_session_seat_names`) apprise depuis les mains
   nommées du fichier (`whole_file`). Un siège qui montre deux noms différents dans la
   session (occupant changé) est écarté comme ambigu plutôt que deviné.
2. **Mains anonymes** : chaque « Player \<siège\> » est remappé sur le vrai nom du siège
   (CR7012, Moula42…) → les stats adverses **fusionnent** avec les mains nommées. Siège
   inconnu/ambigu → `anon_<sessioncode>_<siège>` (pas de pollution inter-session ; la base
   indexe par (site_id, name)). **Aucun héros injecté** dans une main anonyme (un siège qui
   était celui du héros dans une main nommée est scopé, jamais renommé en héros).
3. **Mains nommées** (héros distribué) : intactes — vrais noms déjà présents, héros présent,
   HUD et check « hero is not seated » fonctionnent nativement.
4. **Ordre live** : les mains anonymes qui arrivent AVANT la 1ʳᵉ main du héros n'ont pas
   encore de table de sièges → tout est scopé (sans pollution) ; une fois le héros passé,
   les mains anonymes suivantes récupèrent les vrais noms. En ré-import batch (fichier
   complet), tout est résolu d'un coup.

Tests : `test/test_ipoker_anonymized_players.py` (6 tests) — table de sièges apprise, main
nommée intacte, opposants anonymes récupérés (siège inconnu scopé), héros jamais ressuscité,
tout scopé sans table de sièges, siège ambigu scopé. Validé bout-en-bout sur le fichier bwin
réel : mains anonymes → CR7012/Moula42/TheDarkRaise/confusius5 (+ `anon_..._6`), mains
nommées → `hero=jejesat76`.

Note (hors chantier, à traiter séparément) : `re_hand_info` (`code="(?P<HID>…)"`) matche
`sessioncode="…"` → la 1ʳᵉ main de chaque fichier de session (celle qui contient l'en-tête)
prend le **code de session** comme hand id au lieu de son `gamecode`. Bug pré-existant,
indépendant de l'anonymisation.

### B. Système de sièges iPoker pas au point (numérotation clairsemée 1..10) — ✅ FAIT (2026-07-22, chemin « milieu »)

Le client iPoker numérote les sièges d'une 6-max sur une grille 10-max (1,3,5,6,8,10) et le
config ne portait de `hist_seat` que pour max=6 et max=9. Combiné à `fav_seat=0` par défaut
(aucune rotation), le héros n'était en bas que par coïncidence, et les tailles sans
`hist_seat` (Twister 2/3-max, 5-max…) plantaient (`Error finding hero seat`) → HUD posé sur
les mauvais sièges.

Refonte livrée dans [`Aux_Base.AuxSeats.adj_seats`](fpdb_3_legacy/Aux_Base.py:820) (rotation
ordre-based, ancrage héros toujours actif) :
1. **Ancrage héros = bas-centre par défaut.** Le slot bas-centre est calculé sur la géométrie
   du layout (`_bottom_center_slot` : y max, x le plus proche du centre) au lieu d'un entier
   `fav_seat` à saisir par taille. Un `fav_seat` explicite non nul reste prioritaire (override
   utilisateur). **Changement de comportement** : `fav_seat=0` ne signifie plus « pas de
   rotation » mais « auto = bas-centre » — le héros est désormais toujours en bas, sur tous
   les sites (comme le rend le client).
2. **Ring siège→slot robuste** (`_effective_hh_seats`). On garde le ring configuré quand il
   couvre les sièges occupés (iPoker 6/9-max, tous les sites standards). Sinon on **synthétise**
   un ring à partir des sièges occupés triés → les tailles sans `hist_seat` mappent les joueurs
   au lieu de planter. `layout.hh_seats` est réécrit par main pour que `get_id_from_seat`
   (choix du joueur) et la rotation des positions restent cohérents.
3. **heroSeat=0** : résolu par le chantier A. [`heroSeat`](fpdb_3_legacy/DerivedStats.py:539)
   se remplit via `hand.hero == player[1]` ; le héros portant maintenant son vrai nickname,
   le siège est renseigné.

Tests : `test/test_hud_seat_mapping.py` (7 tests) — bas-centre géométrique, héros ancré quel
que soit son siège (iPoker 6-max, héros siège 10), rotation sur site standard `fav_seat=0`,
override `fav_seat` explicite, taille clairsemée sans `hist_seat` synthétisée, ring configuré
préféré quand il couvre, héros absent → identité sans exception. Suite complète : 3989 OK.

À valider en session live PMU/bwin (6-max) + un Twister (2/3-max), là où la synthèse de ring
et l'ancrage bas-centre n'ont pas de couverture hors-ligne.

Reste hors périmètre (non retenu ici, voir proposition « refonte complète ») : coordonnées
normalisées 0..1 + offset décoration par OS (Win/X11/Cocoa) + round-trip GUI↔XML sans
double-scaling. Le placement reste en pixels re-scalés par ratio ; l'ancrage héros et la
synthèse de ring corrigent la fiabilité inter-room et le « héros pas en bas », pas la
distorsion d'aspect-ratio ni la dérive GUI↔XML.
