# Plan d’amélioration des écrans macOS et de l’import HUD

Date : 22 septembre 2026. Périmètre : Study Explorer, Research Browser,
Study Dashboard et préférences HUD. Référence : les quatre captures utilisateur.

## Diagnostic établi

Les tailles des captures sont des pixels d’image : elles ne permettent pas de
déduire la surface Qt disponible en points logiques sur un écran Retina.
La validation doit mesurer la fenêtre et `QScreen.availableGeometry()`, qui
tient compte de l’espace disponible autour de la barre de menus et du Dock.

| Écran | Observation | Cause identifiée dans le code |
| --- | --- | --- |
| Study Explorer | Le contexte occupe l’essentiel de la hauteur ; les études et leur action passent sous le bas de la fenêtre. | `GuiStudyExplorer._build_ui` empile sept lignes de contexte et les catégories avant le splitter liste/détail, sans zone de défilement englobante. |
| Research Browser | Les filtres sont très espacés et les commandes inférieures ne sont plus accessibles. | `_build_filters_pane` donne un stretch de 1 au conteneur de lignes de filtres, sans alignement haut ni zone de défilement ; trois panneaux sont toujours côte à côte. |
| Préférences HUD | Les sections Dynamic Panels sont écrasées et les contrôles sont coupés. | Le dialogue impose au moins 1200 × 800 ; ses sections Dynamic Panels s’empilent sans défilement global. Les éditeurs Statistics et Popups imposent chacun un panneau gauche de 1000 px. |
| Import HUD | Erreur `reload_parent_config` après l’import. | `import_profile` sauvegarde et recharge le fichier puis appelle une méthode absente de `ModernHudPreferences`. Le test d’import remplaçait cette méthode par un faux callback. |

Le thème ajoute aussi du padding et une hauteur minimale aux champs. Les tests
doivent charger le thème réellement utilisé par l’application ; une interface
testée uniquement avec le style Qt par défaut ne couvre pas ces contraintes.

## Ordre de livraison

### Lot 0 — Réparer l’import HUD

- Implémenter le callback manquant dans le dialogue et l’utiliser aussi pour
  l’import PT4.
- Déléguer au `reload_config` du parent lorsqu’il existe ; permettre l’usage
  autonome du dialogue.
- Distinguer un import enregistré d’un échec de rafraîchissement du parent.
  Dans ce dernier cas, indiquer de redémarrer fpdb et éviter de demander de
  réimporter le même package.
- Exécuter le test avec le vrai dialogue, sans remplacer son callback : sans
  parent, avec parent et avec échec du parent. Vérifier profil sélectionné,
  profils secondaires, popups, affectation au jeu et contenu enregistré.

Statut : correctif implémenté avec tests dans la branche de travail.
Le parent conserve sa politique actuelle de rechargement : il peut demander un
redémarrage lorsque des onglets sont ouverts. Ce correctif ne garantit pas un
rechargement à chaud de tous les HUD déjà affichés.

### Lot 1 — Rendre toutes les commandes accessibles

Fichiers principaux : `GuiStudyExplorer.py`, `GuiResearchBrowser.py`,
`GuiStudyDashboard.py`, `modern_hud_preferences/main_dialog.py`.

- Dimensionner l’ouverture des dialogues selon la surface disponible de
  l’écran concerné, avec une marge pour les décorations de fenêtre.
- Remplacer les minima de fenêtre et de panneaux trop grands par des politiques
  de taille adaptées. Conserver des minima utiles pour les tableaux et dessins.
- Placer les formulaires longs dans des `QScrollArea` redimensionnables, alignés
  en haut. Les groupes gardent la hauteur nécessaire à leurs contrôles.
- Garder visibles les actions principales : Exécuter dans Research,
  Ouvrir l’étude dans Explorer, Annuler/Enregistrer dans les préférences.
- Donner l’espace restant aux résultats, listes et tableaux ; arrêter
  l’étirement vertical des lignes de formulaire.
- Permettre le défilement des barres d’onglets et le retour à la ligne des
  libellés longs. Réserver le défilement horizontal aux données larges et aux
  canevas HUD.

Critère : à 1280 × 720 points logiques, chaque champ est accessible au clavier
et par défilement, aucune section ne masque ses enfants et les actions
principales restent visibles.

### Lot 2 — Réorganiser Study Explorer et Research

**Study Explorer**

- En-tête court : titre, recherche, contexte résumé.
- Contexte courant compact : jeu, format, taille de table, sujet. Placer joueur,
  limites et dates dans une section « Plus de filtres » repliable, avec compteur
  et résumé des filtres actifs même lorsqu’elle est repliée.
- Adapter les cartes de spots à la largeur : trois, deux ou une colonne.
- Donner la priorité à la liste d’études et à son détail ; afficher le détail
  sous la liste lorsque deux colonnes ne tiennent plus.
- Conserver recherche, sélection et filtres lors des changements de disposition.

**Research Browser et Study Dashboard**

- Bureau large : filtres compacts, résultats dominants, mains redimensionnables.
- Largeur intermédiaire : panneau de mains sous les résultats ; filtres
  repliables avec résumé visible.
- Petite largeur : vues Filtres / Résultats / Mains dans un sélecteur local,
  avec les mêmes widgets et le même état de requête.
- Dans le dashboard, rendre variables et filtres repliables et séparer
  graphiques et mains avec un splitter. Une grille 13 × 13 doit conserver sa
  lisibilité ; sa taille ne doit pas agrandir toute la fenêtre.
- Définir les changements de disposition à partir des `minimumSizeHint`
  mesurés avec le thème et les polices. Valider des plages initiales autour de
  1000 et 1400 points avant de fixer les seuils.

Critère : redimensionner ne lance pas de nouvelle requête, ne réinitialise pas
les filtres et ne modifie pas la sélection Hero/Field ni le drill-down.

### Lot 3 — Simplifier les préférences HUD

- En-tête compact : profil actif, Importer, Exporter ; regrouper Créer,
  Dupliquer et Supprimer dans un menu d’actions si la largeur manque.
- Dynamic Panels : liste des règles et éditeur de règle sélectionnée ; organiser
  l’éditeur en Conditions / Affichage / Aperçu. Les conditions avancées et le
  catalogue de statistiques deviennent des sections repliables.
- Adapter les champs de conditions à quatre, deux ou une colonne selon la
  largeur. Conserver un défilement principal pour le formulaire.
- Statistics / Popups : liste des panneaux, canevas et inspecteur ; l’inspecteur
  et l’aperçu passent sous le canevas ou dans un volet repliable selon la place.
- Préserver les edits non enregistrés lors de chaque changement de taille ou
  d’onglet. Préserver les règles importées après une sauvegarde ultérieure.

Critère : créer, modifier, prévisualiser et enregistrer une règle reste possible
sur une fenêtre de portable sans agrandir celle-ci au-delà de l’écran.

## Validation avant fusion

- Tailles de fenêtre en points logiques : 1024 × 640 (mode compact avec
  défilement), 1280 × 720, 1440 × 900 et 1728 × 1117.
- Qt offscreen avec thème de production clair/sombre, libellés français/anglais
  et taille de police augmentée. Mesurer géométries, minimums et plages de
  défilement ; tester l’accès aux actions et la conservation de l’état.
- Vérification visuelle sur macOS Retina avec Dock visible, fenêtre normale et
  maximisée, puis passage sur un second écran si disponible.
- Parcours : choisir un spot → ouvrir l’étude → filtrer un graphique → mains →
  replayer ; importer HUD → sélectionner → éditer → enregistrer → rouvrir.
- Captures reproductibles à chaque taille cible ; tests Qt et métier existants
  sur les deux arbres `tests/` et `test/`, puis CI Linux/macOS/Windows.
- Traiter les retours Codex/Codacy pertinents et attendre la CI verte avant
  fusion de chaque lot.

## État de la mise en œuvre

Lots 0 à 3 mis en œuvre dans la branche `codex/macos-layout-plan-hud-import`.

Trois tours ont suivi les captures de l’utilisateur, chacun après une nouvelle
capture montrant que l’adaptatif seul ne suffisait pas là où un choix de design
était en cause : un rail vertical pour les neuf panneaux du Study Dashboard et
des largeurs de panneau mesurées pour le Research Browser ; puis la barre du
Research Browser reprise par le Study Explorer et le Study Dashboard ; puis le
bloc de contexte de ces deux écrans devenu une zone de la même barre, à plat
plutôt qu’imbriquée. Ce qui suit décrit l’état final.

### Socle partagé

Nouveau module `fpdb_3_legacy/responsive_layout.py` :

- `fit_window` dimensionne une fenêtre dans `QScreen.availableGeometry()` et
  abaisse un minimum explicite qui ne tient pas sur l’écran. Un minimum plus
  grand que l’écran est ce qui rendait le dialogue impossible à réduire.
- `wrap_in_scroll` place un contenu dans une `QScrollArea` dont le contenu
  garde sa hauteur naturelle et reste aligné en haut ; l’aire défilante
  annonce le petit minimum d’une fenêtre au lieu du grand minimum de son
  contenu.
- `ReflowGrid` repose ses éléments selon un nombre de colonnes calculé par
  `column_count` à partir de seuils mesurés.
- `labelled_field` place la légende d’un champ au-dessus de celui-ci, ce qui
  permet de replier le même champ en quatre, deux ou une colonne ; un
  `QFormLayout` met la légende dans une colonne à part et ne se replie pas.
- `ResponsiveSplitter` empile ses panneaux sous la largeur mesurée, mémorise
  l’arrangement large et le restaure au retour ; son signal `stacked_changed`
  annonce le changement d’arrangement (et lui seul).
- `PaneSwitcher` affiche une zone à la fois, avec une barre pour choisir
  laquelle : la zone choisie prend toute la place et la barre est le chemin de
  retour vers les autres. Elle reste cachée tant que les zones tiennent
  ensemble, là où le splitter est le meilleur outil, et ne cache rien tant que
  la fenêtre qu’elle sert n’est pas visible — une barre absente ne ramènerait
  pas la zone cachée. Une zone peut vivre **hors** du splitter, au-dessus de
  lui : le bloc de contexte qui explique un écran n’est pas un panneau des
  panneaux qu’il explique. Elle ne prend alors l’étendue que si le splitter —
  qui est ce qui grandit — s’efface, donc la barre cache le splitter dès que la
  zone affichée n’est pas l’un de ses enfants. `sizes` est l’arrangement à
  retrouver : celui du splitter, une entrée par panneau qu’il contient, et non
  une par zone. Les trois écrans qui empilent des panneaux s’en servent :
  Research Browser, Study Explorer et Study Dashboard.
- `cap_context_block` plafonne un bloc de contexte qui défile à un quart de la
  fenêtre. Un `QVBoxLayout` donne à un élément sans étirement sa taille
  souhaitée avant que l’élément étiré ne reçoive quoi que ce soit, et un bloc
  qui défile réclame quand même toute sa hauteur : l’en-tête du Study
  Dashboard demande 360 px et, sans plafond, les prenait sur une fenêtre de
  691 px en ne laissant que 260 aux zones. `capped=False` lève le plafond quand
  le bloc **est** la zone affichée : avec rien en dessous à écraser, un plafond
  ne ferait que le faire défiler pour rien.
- `CollapsibleSection` replie un bloc tout en affichant dans son en-tête ce
  qu’il contient, pour qu’un bloc replié ne cache pas un filtre actif.

### Mesures

Minimums mesurés hors écran, avec le thème de production, avant et après :

| Écran | Avant | Après |
| --- | --- | --- |
| Préférences HUD | 1064 × 1133 ; minimum imposé 1200 × 800 | 890 × 506 ; aucun minimum imposé, et 735 × 504 sous 900 px de large |
| Study Explorer | 667 × 898 | 410 × 186 ; une zone à la fois sous 669 px de haut ou sous 932 px de large (597 × 336 quand les trois sont visibles) |
| Research Browser | 1097 × 497 | 296 × 141 empilé (904 × 141 côte à côte) ; trois colonnes seulement au-delà de 1302 px de large |
| Study Dashboard | 454 × 1120 | 349 × 265 ; une zone à la fois sous 1109 px de haut, les trois au-dessus (454 × 554) |

Les minimums « après » sont ceux de la forme qu’un petit portable finit par
donner : une seule zone à la fois. C’est cette forme qui doit tenir dans
1024 × 640, et non celle où les trois zones se partagent la fenêtre.

Le seuil de 1024 × 640 est tenu par les quatre écrans. Les facteurs de hauteur
étaient l’onglet Dynamic Panels (880 px), l’onglet Profile Select (584 px), le
formulaire de contexte du Study Explorer (sept lignes) et les onglets du
dashboard (518 px, dont la grille 13 × 13).

### Par écran

**Préférences HUD** — `fit_window(self, 1400, 900)` remplace le minimum imposé ;
les onglets Dynamic Panels, Profile Select et Reference HUDs défilent ; les
minima de panneau passent de 1000 à 560 px ; la barre de profils perd ses cinq
planchers de 120 px et la barre de popups son plancher de 360 px.

**Préférences HUD — en-tête** — les cinq boutons de profil et le sélecteur
fixaient à eux seuls la largeur minimale du dialogue à 890 px, ce qui interdisait
de le poser à côté d’une table. Sous 900 px de large, les cinq mêmes actions
passent derrière un bouton « Profile actions » ; le minimum tombe à 735 px, la
largeur restante étant celle de l’onglet Popup Windows.

**Préférences HUD — éditeur Dynamic Panels** — les 32 sélecteurs de « When this
is the spot » et les 7 champs de « Then show » sont désormais des grilles qui se
replient (4 colonnes au-delà de 1000 px, 3 au-delà de 840, 2 au-delà de 600, 1
en dessous), avec la légende au-dessus du champ. L’ancienne grille à quatre
colonnes fixes imposait la légende dans sa propre cellule et l’ensemble vivait
dans une seconde aire défilante haute de 190 px : cette aire imbriquée est
supprimée, l’onglet défile une seule fois. La case « Enabled » occupait la
cellule (1, 6) d’une grille pleine, une position que le layout pouvait perdre ;
elle a maintenant sa propre ligne. Le catalogue de statistiques analytiques est
replié par défaut et son en-tête annonce ce qu’il contient (« 27 available »),
le plancher de 320 px du sélecteur étant remplacé par une longueur de contenu
minimale.

**Study Explorer** — l’en-tête, le contexte, les spots et les études récentes
sont dans une aire défilante ; les quatre champs qui décident du contenu
tiennent sur une ligne qui se replie (4/2/1 colonnes) ; joueur, limites et
dates passent dans une section « More filters » repliée par défaut, dont
l’en-tête résume les filtres actifs ; les cartes de spots se replient en 3/2/1
colonnes ; liste et détail s’empilent sous 900 px ; les deux points d’entrée
secondaires restent épinglés en bas.

Empilés, la liste et le détail se partageaient la hauteur : à 700 × 640 la liste
n’en avait que 90 px, trois lignes de titres. Une barre Studies / Detail, visible
seulement dans cet arrangement, donne au panneau choisi la hauteur entière
(338 px à cette taille). Choisir une étude bascule sur Detail — c’est le motif
maître-détail des écrans étroits — mais la bascule est déclenchée par
`itemClicked` et `itemActivated`, jamais par `currentItemChanged` : la page
sélectionne une ligne elle-même à chaque reconstruction de la liste (recherche,
catégorie, changement de jeu) et le détail prendrait alors l’écran sans que
personne ne l’ait demandé. Le parcours au clavier reste donc sur la liste :
parcourir n’est pas choisir.

Le bloc de contexte est ensuite devenu une zone comme les autres. Il réclame
357 px à lui seul, et une part de fenêtre pour lui, une pour la liste et une
pour le détail, c’est un formulaire de trois lignes au-dessus d’une liste de
trois titres. Une **seule** barre à plat porte donc les trois zones — Filters,
Studies, Detail — et non une barre par région : elle apparaît sous
`SWITCH_BELOW_HEIGHT = 357 + 213 + 99 = 669` px de haut, ou sous
`STACK_BELOW_WINDOW_WIDTH = 900 + 2 × 16 = 932` px de large (les marges de la
page que le splitter ne reçoit pas), et s’efface dès que la page tient. La zone
d’ouverture est Studies, pas Filters : le lecteur vient pour les études, le bloc
au-dessus est ce qui les filtre. À 700 × 640 la liste passe ainsi de 338 à
544 px, et la zone Filters prend ces 544 px quand on la choisit.

Deux pièges de mesure ont été corrigés au passage. `sizes` était renseigné avec
une entrée par zone, alors que c’est l’arrangement du splitter qu’il décrit :
Qt ignore les valeurs excédentaires, donc la taille en trop était une fiction
silencieuse. Et la page décidait d’après `is_stacked()`, lu sur le splitter :
quand le bloc de contexte est la zone affichée, le splitter est caché, et un
widget que le layout saute garde la largeur — donc l’orientation — qu’il avait
avant d’être caché. La page décide désormais d’après sa propre largeur, dérivée
du même seuil.

**Research Browser** — les trois panneaux sont dans un `ResponsiveSplitter` ;
chaque panneau défile, ce qui ramène son minimum à celui d’une fenêtre ; le
conteneur de lignes de filtres ne prend plus l’étirement vertical — c’est ce qui
étirait chaque ligne et poussait Exécuter hors du panneau. Empilés, les trois
panneaux se partageaient la hauteur et chacun n’en recevait qu’un tiers : une
barre Filtres / Résultats / Mains, visible seulement dans cet arrangement, donne
au panneau choisi la hauteur complète. C’est ce motif qui a été extrait en
`PaneSwitcher` et repris par les deux autres écrans.

La largeur des panneaux est mesurée sur leur contenu, et non plus divisée en
tiers. Les lignes de filtres réclament 624 px, le tableau de résultats 402 et la
liste de mains 260 : le splitter donnait auparavant à chacun le tiers de ce qu’il
avait, si bien qu’à 1600 px le panneau des filtres était encore amputé de 33 px —
« Add breakdown » et « Save / Delete » restaient à moitié hors du panneau sur un
écran assez large pour les montrer. `PANE_WIDTHS = (624, 402, 260)` ouvre
désormais chaque panneau à sa largeur naturelle, l’espace excédentaire d’un grand
écran étant partagé. L’arrangement ne se replie qu’en dessous de 1302 px, la
somme des trois largeurs et des deux poignées (`STACK_BELOW_WIDTH`) : trois
colonnes ne sont proposées que lorsque les trois sont lisibles, et en dessous la
barre prend le relais, un panneau à la fois en pleine largeur. Le défilement
horizontal du panneau des filtres ne sert plus que de filet de sécurité pour une
fenêtre plus étroite que ses propres lignes ; les largeurs mémorisées pour le
retour à l’arrangement large sont bien des largeurs, et non les hauteurs de
l’empilement.

**Study Dashboard** — l’en-tête (titre, contexte, variables, comparaison,
filtres croisés) défile ; les variables deviennent un bloc repliable dont
l’en-tête indique combien sont définies ; panneaux et mains partagent la
hauteur par un splitter au lieu de deux étirements égaux, et le panneau des
onglets défile pour que la grille 13 × 13 ne fixe plus la hauteur de l’onglet.

Les neuf panneaux d’une étude PLO ne tiennent pas dans une barre d’onglets : leur
libellé réclame 1121 px de bande, et à 1080 px de large la barre n’en a que 1030,
si bien que « Source hands » disparaissait derrière la flèche `▶` de défilement.
Le minimum du widget ne bougeait pas pour autant — Qt fait défiler la bande au
lieu de la comprimer —, ce qui explique que les tests précédents ne l’aient pas
vu. Les onglets sont remplacés par une liste verticale (`QListWidget` +
`QStackedWidget`) posée à gauche du contenu, à l’extérieur de l’aire défilante :
la largeur du rail est celle de son libellé le plus long (190 px pour neuf
panneaux, bornée à 150–280 px), les neuf noms restent lisibles sans défilement
horizontal ni vertical, et le contenu garde toute la largeur restante. Les
panneaux indisponibles sont désactivés avec la raison en infobulle, comme
l’étaient les onglets désactivés.

Deux zones se partageaient la hauteur : les panneaux et les mains. Elles
réclament 360 px et 330, et le splitter n’en a que 420 dans une fenêtre de
691 px — soit une zone de panneaux déjà collée à son plancher de 200 px et un
tableau de 228. Une barre Panels / Hands apparaît donc sous 698 px de haut et
donne à la zone choisie les 420 px entiers ; au-dessus, le splitter reprend ses
droits et les deux restent visibles.

L’en-tête est ensuite devenu la troisième zone, pour la même raison que dans le
Study Explorer : une part de fenêtre pour lui, une pour les panneaux et une pour
les mains, c’est trois zones qui n’en montrent aucune. La barre est donc à plat
— Filters, Panels, Hands — et son seuil est la hauteur à laquelle les trois
peuvent se lire ensemble, `SWITCH_BELOW_HEIGHT = 360 + 360 + 330 + 59 = 1109` px.
La zone d’ouverture reste Panels : le lecteur vient pour l’étude, le bloc
au-dessus est ce qui la filtre. À 1080 × 691 la zone des panneaux passe de 200 à
626 px. Le déclencheur est la hauteur de la fenêtre et non celle du splitter :
celle-ci n’est plus lisible quand le bloc de contexte est la zone affichée, le
splitter étant alors caché.

L’en-tête a dû être plafonné au passage. Il défile, donc il n’a pas besoin de
toute sa hauteur, mais il la réclamait quand même : 360 px pris sur une fenêtre
de 691 px, laissant 260 aux deux zones — l’inverse de « seuls les panneaux et
les mains grandissent ». `cap_context_block` le borne au quart de la fenêtre
(plancher 200 px) tant qu’il partage la fenêtre avec les autres zones ; quand il
est la zone affichée, le plafond est levé (`capped=False`) puisqu’il n’a plus
rien à écraser, et il prend les 626 px.

### Tests

`tests/qt/test_responsive_layout.py` : 42 tests, tous verts. Ils couvrent les
helpers (dimensionnement, défilement, reflow, bascule d’orientation et le signal
qui l’annonce, sélecteur de zone, plafond du bloc de contexte, repli avec
résumé, légende au-dessus du champ) et les quatre écrans, en vérifiant pour
chacun que le minimum tient dans 1024 × 640, que les commandes du bas restent
atteignables, et que redimensionner ne change ni la recherche, ni la sélection,
ni les filtres. Dix-sept d’entre eux portent sur les réorganisations des quatre
tours :

- éditeur Dynamic Panels : repli des colonnes sans perte de sélecteur, absence
  de seconde aire défilante, champs « Then show » et case « Enabled »
  atteignables, catalogue replié avec son compte ;
- `PaneSwitcher` : un seul panneau à la fois, retour à l’arrangement et aux
  tailles du splitter, rien de caché tant que la fenêtre n’est pas visible, la
  zone hors du splitter qui prend l’étendue en le faisant s’effacer, et le
  refus d’un `sizes` qui ne décrit pas le splitter ;
- `cap_context_block` : le plafond laisse la place à ce qui grandit, suit une
  fenêtre plus haute, et est levé quand le bloc est la zone affichée ;
- Research Browser : un seul panneau à la fois en arrangement empilé, retour aux
  trois panneaux et à leurs tailles en arrangement large, largeurs mesurées sur
  le contenu avec trois colonnes seulement au-dessus de 1302 px, largeurs larges
  conservées à travers un aller-retour par l’empilement, et défilement horizontal
  du panneau des filtres dans une fenêtre plus étroite que ses lignes ;
- Study Explorer : une barre à plat Filters / Studies / Detail qui s’efface
  quand la page tient, une zone à la fois quand elle ne tient pas, la zone
  Filters qui prend la place en faisant s’effacer le splitter, et le détail qui
  prend l’écran au clic mais ni sur une reconstruction de la liste ni en la
  quittant ;
- Study Dashboard : une barre à plat Filters / Panels / Hands sous 1109 px de
  haut, les trois zones au-dessus, la zone Filters qui prend la place en faisant
  s’effacer le splitter, et un en-tête plafonné quand il partage la fenêtre mais
  pas quand il l’a pour lui ;
- Préférences HUD : les cinq actions de profil passent derrière un menu sous
  900 px, ce qui abaisse le minimum du dialogue.

Les fenêtres sont rétrécies par paliers de 200 px, comme un glissement de bord :
tant que les panneaux sont côte à côte, la somme de leurs largeurs minimales
(904 px) borne la largeur de la fenêtre, et Qt applique cette borne avant que le
layout n’ait empilé les panneaux. Un saut direct sous ce total laisse donc la
fenêtre à l’ancien minimum ; un glissement réel ne saute jamais.

Suites existantes vérifiées hors écran : `tests/qt` (195 tests, tous marqués
`qt`), `tests/test_dynamic_panels_tab.py` et `tests/test_hud_panel_editor.py`
(64 : 35 sans écran, 29 en `-m qt`), `test/test_aof_hud_package.py`,
`test/test_modern_hud_preferences.py`, `test/test_plo4_hud_package.py`,
`test/test_hud_profiles.py`, `test/test_pt4hud_import.py` (57 : 24 sans écran,
33 en `-m qt`).

### Reste à faire

- Validation visuelle sur macOS Retina avec Dock visible, puis sur un second
  écran, et parcours complet import HUD → sélection → édition → enregistrement.
- Traitement des retours Codex/Codacy et CI verte avant fusion.

