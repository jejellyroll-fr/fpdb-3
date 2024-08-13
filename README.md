# FPDB 3

[![stars](https://custom-icon-badges.demolab.com/github/stars/jejellyroll-fr/fpdb-3?logo=star)](https://github.com/jejellyroll-fr/fpdb-3/stargazers "stars")
[![issues](https://custom-icon-badges.demolab.com/github/issues-raw/jejellyroll-fr/fpdb-3?logo=issue)](https://github.com/jejellyroll-fr/fpdb-3/issues "issues")
[![license](https://custom-icon-badges.demolab.com/github/license/jejellyroll-fr/fpdb-3?logo=law&logoColor=white)](https://github.com/jejellyroll-fr/fpdb-3/blob/main/LICENSE?rgh-link-date=2021-08-09T18%3A10%3A26Z "license MIT")

starting new project base on fpdb python3 adaptation of MegaphoneJon and update from ChazDazzle 
(tx to all previous contribs)

Feel free to clone it, and to participate to this development.

I'm not an expert python developer, this project, as a poker player, is for me to develop my skills in this language during my free time.

## Updating to python 3.11.9

FPDB is a poker tools - HUD - Replayer
Download your build directly on this repo: https://github.com/jejellyroll-fr/fpdb-3-builder

## understand architecture soft

- see fpdb.drawio (WIP) or use puml files (outdated) will be replace probably by mermais files

## To do
>code improve
- replace dict['key] per dict.get('key') to prevent crashes
- replace concatened string by Fstring

>unit test
- write unit tests to cover all code (POC works need to add more tests)

![example workflow](https://github.com/jejellyroll-fr/fpdb-3/actions/workflows/fpdb-3.yml/badge.svg)


>CI/CD
-working github actions

>database
- not working mysql connector on py3.1x -> will be not support 
- postgreSQL and SQLite3 tested OK
- try bdd on containers (TO DO) 
>translation-language
- not working translation -> from icu import Locale(TO DO: find better solution- OK - need to finish traduction)
>pokerstove
- add odds calc (fast solution-> use Pokerprotools online WIP) -> add last version poker-eval and pypoker (deprecated)
- update poker-eval lib (https://github.com/jejellyroll-fr/poker-eval)->added 5 cards PLO, 5 card PLO8 and 6 card PLO -> OK -> think to add short deck nl(done) and rewrie in C hand distributions c++ code from Atim(WIP)
- update pypoker-eval (https://github.com/jejellyroll-fr/pypoker-eval)->Python 3 ->OK (TO DO: add 6 and 5 cards plo) -( will not maintain this wrapper as is perhaps rewrite directly in cython)
- add POKENUM web api to do it: https://github.com/jejellyroll-fr/pokenum
>replayer
- rethink the distribution of players around the table (TO DO: WIP)
- add pot odds and equity(TO DO)
- will probably replace by web version(TO DO)

>handviewer(cash)
- Filter bug (player and site =not good working)
- will probably replace by web version(TO DO)
>import
- PMU not working siteid error(TODO: WIP)
- correct bug import from pokertracker summary (TODO)
- add SWC and so on (done)
- re add old dead sites
>graphviz
- improve visualization (TODO)
- will probably replace by web version(WIP)
>stats
- to verify
- add spin stats (TODO: CeV depending on calculation )
- will probably replace by web version(TO DO)
>hud
- windows not working (error) -> Fixed
- mac disappear behind the table -> fixed
- linux disappear behind the table (ubuntu) -> Fixed on winamax native linux app and KDE -> to Fix when use bottles
- mtt table detection - bug on ipoker, must investigate other rooms
- add ui for seat config per site (DONE)
- add ui for Hud config per games (DONE)
- edit config will probably replace by web version(TO DO)
>ui
- dark theme(DONE)
- more modern (perhaps use pyside6 in the future)
- add web server Flask+fastapi (WIP)
>notebook jupyter
- add some notebooks




>site hud

| X      |Os    |MTT| CG|Fast|SNG|SPIN|
|------- |------|---|---|----|---|----|
|winamax | win11, osx, linux| OK  | OK(except Floop-no HH text)| KO | OK| OK |
|winamax | osx big sur (intel)| OK  | OK(except Floop-no HH text)| KO | OK| OK |
|Pokerstars| Win11| OK  |OK (except Fusion-fixed)| KO | OK  | OK   |
|Pokerstars| osx big sur (intel)| OK  |OK (except Fusion-fixed)| KO | OK  | OK   |
|Betclic| Win11| OK | OK  | X|  KO  | KO   |
|Betclic| osx no HH| x | x  | X|  x  | x   |
|PMU| Win11| KO | KO  | KO|  KO  | KO   |
|Unibet| no handhistory| X | X  | X|  X  | X   |

>poker rooms on linux with bottles (https://docs.usebottles.com/)
- Pokerstars.fr (ok) 
- Winamax new soft(ok with native linux app)
- PMUPoker (ok) - must restart install exe
- Unibet.fr(ko) - must update exe
- betclic.fr (ko) - installment ko


## Requirement for dev 
Install the dependencies and devDependencies .
I Use anaconda with Python 3.11

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
or
```sh
pip install -r requirements_fpdb_web.txt
```

## Dev test
FPDB3
```Python
python fpdb.pyw
```
FPDB3 web
```Python
python start_fpdb_web.py 
```


## Bugs tracking

on windows:
- with  winamax on windows, detection position tables if play more than 1.
- swc tournement error import

## Bugs report and new hand support

you can report the bugs in the appropriate section
Specify your Os
you can send your HH in error by email jejellyroll.fr@gmail.com




**Free Software, Hell Yeah!**


