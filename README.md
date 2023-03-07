# FPDB 3

starting new project base on fpdb python3 adaptation of MegaphoneJon and update from ChazDazzle 
(tx to all previous contribs)

Feel free to clone it, and to participate to this development.

I'm not an expert python developer, this project, as a poker player, is for me to develop my skills in this language during my free time.

## Updating to python 3.11

FPDB is a poker tools - HUD - Replayer
installment bugs -> copy logging.conf,HUD_config.xml ... on C:\Users\your_user_name\AppData\Roaming\fpdb

## understand architecture soft

- see fpdb.drawio (WIP) or use puml files

## To do

>database
- not working mysql connector on py3.10 -> import MySQLdb (TO DO: find solution )
- psql not tested (TO DO)
- try bdd on containers (TO DO) 
>translation-language
- not working translation -> from icu import Locale(TO DO: find better solution)
>pokerstove
- add odds calc (fast solution-> use Pokerprotools online WIP) -> prokerprotool is down (TO DO: other option install on pc, or use other lib ploev,treys... WIP)
- update poker-eval lib (https://github.com/jejellyroll-fr/poker-eval)->added 5 cards PLO, 5 card PLO8 and 6 card PLO -> OK
- update pypoker (https://github.com/jejellyroll-fr/pypoker-eval)->Python 3 ->OK (TO DO: add 6 and 5 cards plo)
>replayer
- not working ->fixed
- rethink the distribution of players around the table (TO DO: WIP)
- add pot odds and equity(TO DO)
- dev specific web front (TO DO: stay with python, exemple django or other laguage like js, exemple react.js)
>handviewer(cash)
- Filter bug (player and site =not good working)
>import
- correct bug on winamax (no SB)->Fixed 
- correct bug go fast (adding holdhup(extra cash->special rake 10%), error collected pot>total pot)->fixed(TO DO REWORK: include Chaz's methode, better way to do)
- correct bug starting  hand razz guiringcashplayer
- PMU not working siteid error(TODO)
- correct bug import from pokertracker summary (TODO)
>graphviz
- use more modern lib (plotty ...)
- improve visualization (TODO)
>stats
- to verify
- add spin stats (TODO: CeV depending on calculation )
>hud
- windows not working (error) -> Fixed
- mac disappear behind the table -> fixed(Big sur)->regression Bug :( 
- linux disappear behind the table (ubuntu) -> Fixed -> not working with bottles
- mtt table detection - bug on ipoker, must investigate other rooms
- add ui for seat config per site (TODO)
- add ui for Hud config per games (TODO)
>ui
- dark theme
- more modern (perhaps use pyside6 in the future)
>notebook jupyter
- add some notebooks

>site hud

| X      |Os    |MTT| CG|Fast|SNG|SPIN|
|------- |------|---|---|----|---|----|
|winamax | win11| OK  | OK(except Floop-no HH text)| KO | OK| OK |
|winamax | osx big sur (intel)| OK  | OK(except Floop-no HH text)| KO | OK| OK |
|Pokerstars| Win11| OK  |OK (except Fusion-fixed)| KO | OK  | OK   |
|Pokerstars| osx big sur (intel)| OK  |OK (except Fusion-fixed)| KO | OK  | OK   |
|Betclic| Win11| KO | OK  | X|  KO  | KO   |
|Betclic| osx no HH| x | x  | X|  x  | x   |
|PMU| Win11| KO | KO  | KO|  KO  | KO   |
|Unibet| no handhistory| X | X  | X|  X  | X   |

>poker rooms on linux with bottles (https://docs.usebottles.com/)
- Pokerstars.fr (ok) 
- Winamax new soft(ok)
- PMUPoker (ok) - must restart install exe
- Unibet.fr(ko) - must update exe
- betclic.fr (ko) - installment ko


## Requirement for dev 
Install the dependencies and devDependencies .
I Use anaconda with Python 3.10

or Pip

```sh
pip install -r requirements.txt
```
or 
```sh
pip install -r requirements_linux.txt
```
or
```sh
pip install -r requirements_macos.txt
```

## Installation
no release yet

## Bugs report and new hand support

you can report the bugs in the appropriate section
Specify your Os
you can send your HH in error by email jejellyroll.fr@gmail.com

## Images
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpdb3_home.png)
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpdb3_grahspin.png)
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpdb3_graphcg.png)
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpdb3_handreplayer.png)
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpdb3_session_stats.png)
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpdb3_session_stats.png)
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpd3_handviever.png)
![alt text](https://github.com/jejellyroll-fr/fpdb-3/blob/main/fpdb3_oddcalc.png)

## License

MIT

**Free Software, Hell Yeah!**


