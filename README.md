# FPDB 3
starting new project base on fpdb python3 adaptation of MegaphoneJon (tx to all previous contibs)
## Updating to python 3.9
FPDB is a poker tools - HUD - Replayer

## understand architecture soft

- see fpdb.drawio (WIP)

## to do
>database
- not working mysql connector on py3.9 -> import MySQLdb
>translation
- mot working translation -> from icu import Locale
>pokerstove
- add odds calc (fast solution-> use Pokerprotools online WIP) 
>replayer
- not working ->fixed
- rethink the distribution of players around the table
>>import
- correct bug on winamax (no SB)->Fixed
- correct bug go fast (adding oldhup, error collected pot>total pot)->fixed
- correct bug starting  hand razz guiringcashplayer
>hud
-windows and mac not appear
-linuc disappear behind the table


## Requirement
```sh
cd dillinger
npm i
node app
```


## Installation


Install the dependencies and devDependencies and start the server.

```sh
cd dillinger
npm i
node app
```

For production environments...

```sh
npm install --production
NODE_ENV=production node app
```

## Plugins



|  |  |
|  | |


## Development



#### Building for source


## Docker



> Note: `--capt-add=SYS-ADMIN` is required for PDF rendering.

Verify the deployment by navigating to your server address in
your preferred browser.

```sh
127.0.0.1:8000
```

## License

MIT

**Free Software, Hell Yeah!**


