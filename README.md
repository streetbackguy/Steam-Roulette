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

![image](https://github.com/user-attachments/assets/d02307aa-a84d-4a59-a211-a173c4949b26)

# To-Do
- Find a permanent way to calculate installation size for each game on each separate drive

# Virus Scan

https://www.virustotal.com/gui/file/6a9d2c759fed98b6d885036ccd4cfe7fe7510d997bc41aa764d5f88ade0ae29e/detection

The release version does seem to flag up as a Trojan according to a few antivirus software, but rest assured that this application is safe, and all the source code is visible in this repo, so consider them nothing more than false positives.
