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
- add odds calc (fast solution-> use Pokerprotools online WIP) -> prokerprotool is down (other option install on pc WIP)
>replayer
- not working ->fixed
- rethink the distribution of players around the table
>import
- correct bug on winamax (no SB)->Fixed
- correct bug go fast (adding holdhup(extra cash->special rake 10%), error collected pot>total pot)->fixed
- correct bug starting  hand razz guiringcashplayer
- PMU not working siteid error
>hud
- windows not working (error) -> Fixed
- mac disappear behind the table -> fixed(Big sur)
- linux disappear behind the table (ubuntu) -> Fixed
>ui
- dark theme
- more modern
>language
- not working
>site hud
- pokerstars working
- new winamax not working
- betclic.fr working
- PMU not working
>poker rooms on linux with wine (7.16 with winetricks Q4wine)
- Pokerstars (ok) - install libgl1-mesa-glx:i386, winbind
- Winamax new soft(ko) - wine wlauncher.exe --mode unattended --unattendedmodeui none --cmdlaunch poker - install libcanberra-gtk-module
- PMUPoker (ko) - install ole32,vcrun6 corefont with wintricks
- Unibet - 

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


