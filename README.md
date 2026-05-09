# Steam-Roulette
Random game picker from your installed Steam games. Mainly to help indecisive people who want to play a game, but no idea which one to play.

# Installation
`pip install vdf`

`pip install Pillow`

`pip install requests`

`pip install steam`

`pip install tk`

You can run the script as it is through CMD, or you can compile it to an EXE with pyinstaller.

# Pyinstaller Compilation
`pyinstaller --onefile --noconsole --icon=SteamRouletteIcon.ico --add-data "SteamRouletteIcon.ico;." --add-data "SteamRouletteLogo.png;." SteamRoulette.py`

# Usage
To use this application, you will need your Steam API key. This cannot be provided and is different for each person.

You can either edit the base script to add a constant for your API_KEY or you can enter it into the 'Enter Steam API Key' button dialogue box.

To get your Steam API Key, visit https://steamcommunity.com/dev/apikey and login. Remember to keep your API Key confidential and only for your eyes.

# Features
- This application will launch the chosen game for you directly from the Steam client.
- With each game chosen, it will display the Steam Header image for that game from the Steam servers. If no image is found on the server, it will look for a local Header file instead.
- This application has a button that will bring you to the games Store Page on https://steampowered.com/.
- If you're not particularly happy with one game, you can reroll with the reroll button.
- There is now an animation for when the wheel is spinning.
- Ability to set the number of games to spin through.
- Set your own API Key via the Set API Key button. This key will persist in a local text file so you only have to enter it once.
- Now an ability to switch between a light and dark theme, depending on your preferences.
- Preloads Steam game header images to a cache so you won't have to fetch them through the Steam API each time.
- Feature to now include games you own that are not installed in the spin list
- Exclude games/items you don't want to be included in the spin
- Log window to see for any errors downloading Game images/icons

<img width="602" height="782" alt="image" src="https://github.com/user-attachments/assets/e32c25be-9fa6-47f3-92ee-22af2de56971" />

# To-Do
- Fix issue where some games images on the wheel are unavailable

# Virus Scan

https://www.virustotal.com/gui/file/f12f47273cb672a6f69022c9c5ed712420c36cc3c7c6ff1a73d15588ac385b9c/detection

The release version does seem to flag up as a Trojan according to a few antivirus software, but rest assured that this application is safe, and all the source code is visible in this repo, so consider them nothing more than false positives.
