# FPDB 3

[![stars](https://custom-icon-badges.demolab.com/github/stars/jejellyroll-fr/fpdb-3?logo=star)](https://github.com/jejellyroll-fr/fpdb-3/stargazers "stars")
[![issues](https://custom-icon-badges.demolab.com/github/issues-raw/jejellyroll-fr/fpdb-3?logo=issue)](https://github.com/jejellyroll-fr/fpdb-3/issues "issues")
[![license](https://custom-icon-badges.demolab.com/github/license/jejellyroll-fr/fpdb-3?logo=law&logoColor=white)](https://github.com/jejellyroll-fr/fpdb-3/blob/main/LICENSE?rgh-link-date=2021-08-09T18%3A10%3A26Z "license MIT")

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
>unit test
-write unit tests to cover all code

![example workflow](https://github.com/jejellyroll-fr/fpdb-3/actions/workflows/fpdb-3.yml/badge.svg)


>CI/CD
-working github actions

>database
- not working mysql connector on py3.1x -> import MySQLdb (TO DO: find solution )
- psql not tested (Tested OK)
- try bdd on containers (TO DO) 
>translation-language
- not working translation -> from icu import Locale(TO DO: find better solution- rework - need to finish)
>pokerstove
- add odds calc (fast solution-> use Pokerprotools online WIP) -> prokerprotool is down (TO DO: other option install on pc, or use other lib ploev,treys... WIP)
- update poker-eval lib (https://github.com/jejellyroll-fr/poker-eval)->added 5 cards PLO, 5 card PLO8 and 6 card PLO -> OK
- update pypoker (https://github.com/jejellyroll-fr/pypoker-eval)->Python 3 ->OK (TO DO: add 6 and 5 cards plo)
>replayer
- not working ->fixed
- rethink the distribution of players around the table (TO DO: WIP)
- add pot odds and equity(TO DO)

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
- add ui for seat config per site (DONE)
- add ui for Hud config per games (DONE)
>ui
- dark theme
- more modern (perhaps use pyside6 in the future)
>notebook jupyter
- add some notebooks

>data viz
- idea sql -> APi -> front web (must POC)


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
pip install -r requirements_win.txt
```
or
```sh
pip install -r requirements_macos.txt
```

## Installation
no release yet

## Bugs tracking

on windows:
- with  winamax, detection position tables if play more than 1.
- swc tournement error import

## Bugs report and new hand support

you can report the bugs in the appropriate section
Specify your Os
you can send your HH in error by email jejellyroll.fr@gmail.com




**Free Software, Hell Yeah!**


