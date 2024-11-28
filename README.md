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

![image](https://github.com/user-attachments/assets/493f27ac-49e3-4c13-8117-7364d8930fb8)

# To-Do
- Find a permanent way to calculate installation size for each game on each separate drive
