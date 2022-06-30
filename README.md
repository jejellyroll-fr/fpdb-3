# FPDB 3

starting new project base on fpdb python3 adaptation of MegaphoneJon and update from ChazDazzle 
(tx to all previous contribs)

## Updating to python 3.10

FPDB is a poker tools - HUD - Replayer

## understand architecture soft

- see fpdb.drawio (WIP)

## To do

>database
- not working mysql connector on py3.10 -> import MySQLdb
>translation
- mot working translation -> from icu import Locale
>pokerstove
- add odds calc (fast solution-> use Pokerprotools online WIP) 
>replayer
- not working ->fixed
- rethink the distribution of players around the table
>import
- correct bug on winamax (no SB)->Fixed
- correct bug go fast (adding holdhup(extra cash->special rake 10%), error collected pot>total pot)->fixed
- correct bug starting  hand razz guiringcashplayer
>hud
- windows not working (error)
- mac disappear behind the table
- linux disappear behind the table
>ui
- dark theme
- more modern
>language
- not working


## Requirement for dev 

```sh
pip install -r requirements.txt
```


## Installation

Install the dependencies and devDependencies .
 Use anaconda Python 3.10
```sh
conda activate
```


## Plugins



## Development


#### Building for source


```

## License

MIT

**Free Software, Hell Yeah!**


