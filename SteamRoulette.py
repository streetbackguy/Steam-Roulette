import os
import io
import random
import platform
import webbrowser
import requests
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk
from io import BytesIO
import json
import vdf
import sys
from concurrent.futures import ThreadPoolExecutor
import time
import winreg
import threading

def create_cache_directory():
    """Ensure the cache directory exists."""
    # Define the path to store cached images
    cache_dir = os.path.join(os.path.dirname(sys.executable), "image_cache")
    
    # Check if the directory exists, create it if it doesn't
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
        print(f"Cache directory created at: {cache_dir}")
    else:
        print(f"Cache directory already exists at: {cache_dir}")
    
    return cache_dir

def get_steam_install_path():
    try:
        # Open the registry key where Steam installation path is stored
        registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        # Get the value of "SteamPath"
        steam_path, _ = winreg.QueryValueEx(registry_key, "SteamPath")
        return steam_path
    except FileNotFoundError:
        print("Steam installation not found in the registry.")
        return None
    
def find_steam_path_fallback():
    common_paths = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        os.path.expanduser("~\\AppData\\Local\\Steam"),  # Potential user-specific path
    ]
    
    for path in common_paths:
        if os.path.exists(os.path.join(path, "steam.exe")):
            return path
    return None

def resource_path(relative_path):
    """Get the absolute path to the resource, works for both development and PyInstaller."""
    try:
        base_path = sys._MEIPASS  # PyInstaller temp directory
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))  # Development mode
        
    resolved_path = os.path.join(base_path, relative_path)
    
    print(f"Resolved path for {relative_path}: {resolved_path}")  # Debugging output
    return resolved_path

# Constants
STEAM_PATH = get_steam_install_path() or find_steam_path_fallback()
ICON_PATH = resource_path("SteamRouletteIcon.ico")
IMAGE_PATH = os.path.dirname(os.path.abspath(__file__))
PLACEHOLDER_IMAGE_DIMENSIONS = (600, 300)

# Utility Functions
def parse_vdf(file_path):
    """Parse a VDF file and return its content."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = vdf.parse(file)
            # Extract library folders from the parsed VDF
            libraries = content.get("libraryfolders", {})
            return {key: value.get("path") for key, value in libraries.items() if isinstance(value, dict) and "path" in value}
    except Exception as e:
        print(f"Error parsing VDF file: {e}")
        return {}

def fetch_game_data(acf_path, library_path):
    """Extract game data from an ACF file and include the library path."""
    try:
        with open(acf_path, "r", encoding="utf-8") as file:
            content = vdf.parse(file).get("AppState", {})
        game_data = {
            "app_id": content.get("appid"),
            "name": content.get("name"),
            "path": library_path  # Include the path to the game
        }
        return game_data
    except Exception as e:
        print(f"Error reading ACF file {acf_path}: {e}")
        return {}

def fetch_header_image(app_id, cache_dir, timeout=10):
    """Fetch game header image from Steam or return a placeholder."""
    cache_file_path = os.path.join(cache_dir, f"{app_id}.jpg")

    if os.path.exists(cache_file_path):
        print(f"Using cached image for app_id {app_id}")
        return Image.open(cache_file_path)  # Open the cached image

    # If not cached, fetch from Steam
    urls = [
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/page_bg.jpg",
    ]
    for url in urls:
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content))
                img.save(cache_file_path, "JPEG")  # Save it to the cache
                return img
        except Exception as e:
            print(f"Error fetching image for app_id {app_id}: {e}")

    print(f"No valid image found for app_id {app_id}. Using placeholder.")
    return create_placeholder_image("Image Unavailable")

def create_placeholder_image(text):
    """Generate a placeholder image."""
    img = Image.new("RGB", PLACEHOLDER_IMAGE_DIMENSIONS, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Use textbbox to calculate text size
    bbox = draw.textbbox((0, 0), text, font=font)
    text_size = (bbox[2] - bbox[0], bbox[3] - bbox[1])

    # Position the text in the center of the image
    draw.text(
        ((img.width - text_size[0]) / 2, (img.height - text_size[1]) / 2),
        text,
        font=font,
        fill="black",
    )
    return img

def get_installed_games(steam_path):
    """Scan for installed games in Steam library."""
    library_folders = parse_vdf(os.path.join(steam_path, "steamapps", "libraryfolders.vdf"))
    installed_games = []
    for library_path in library_folders.values():
        if library_path and isinstance(library_path, str):
            steamapps_path = os.path.join(library_path, "steamapps")
            if os.path.exists(steamapps_path):
                for acf_file in filter(lambda f: f.endswith(".acf"), os.listdir(steamapps_path)):
                    game = fetch_game_data(os.path.join(steamapps_path, acf_file), library_path)
                    if game and game.get("app_id"):  # Validate app_id here
                        installed_games.append(game)
                    else:
                        print(f"Excluded invalid game: {game}")
    return installed_games

def fetch_steam_user_id(self, api_key):
    """Automatically fetch the Steam User ID using the API key."""
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    params = {
        "key": api_key,
        "steamids": "76561197960287930"  # This is a placeholder; we will replace it dynamically
    }

    try:
        # Request the player summary
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()  # Check if the response is successful
        data = response.json()

        # Check if we received valid player data
        if "response" in data and "players" in data["response"]:
            player_info = data["response"]["players"][0]
            steam_id = player_info.get("steamid")
            print(f"Successfully fetched Steam User ID: {steam_id}")
            return steam_id
        else:
            print("Could not fetch Steam User ID.")
            return None
    except Exception as e:
        print(f"Error fetching Steam User ID: {e}")
        return None

def get_all_games(api_key, steam_id):
    """Fetch all games owned by the user via the Steam API."""
    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": api_key,
        "steamid": steam_id,
        "include_appinfo": True,  # Include app info (app_id, name, etc.)
        "include_played_free_games": True  # Include free-to-play games
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Log the full response to check if app_id exists
        print(f"Full Response from Steam API: {data}")

        if "response" in data and "games" in data["response"]:
            games = data["response"]["games"]
            print(f"Fetched {len(games)} games from the Steam API.")
            return games
        else:
            print("No games found in the response.")
            return []
    except Exception as e:
        print(f"Error fetching games from Steam API: {e}")
        return []
    
def get_steam_app_list():
    """Fetch the complete list of Steam app IDs."""
    url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "applist" in data and "apps" in data["applist"]:
            app_list = {str(app["appid"]): app["name"] for app in data["applist"]["apps"]}
            return app_list
        else:
            print("Error: No apps found in the response.")
            return {}
    except Exception as e:
        print(f"Error fetching app list from Steam API: {e}")
        return {}
    
def get_uninstalled_games_from_api(api_key, steam_id, installed_games):
    """Fetch uninstalled games using the Steam API."""
    all_games = get_all_games(api_key, steam_id)
    
    if not all_games:
        print("No games fetched from Steam API.")
        return []
    
    installed_ids = {str(game["app_id"]) for game in installed_games}
    uninstalled_games = [
        {"app_id": str(game["appid"]), "name": game["name"]}
        for game in all_games
        if str(game["appid"]) not in installed_ids
    ]
    
    print(f"Uninstalled games detected via API: {len(uninstalled_games)}")  # Debugging line
    return uninstalled_games

def get_uninstalled_games(installed_games, all_games):
    """Identify uninstalled games based on the library paths."""
    # Log the installed and all games data for debugging
    print(f"Installed games: {len(installed_games)} games")
    print(f"All games: {len(all_games)} games")
    
    # Strip spaces and ensure app_id is consistently formatted
    installed_ids = {str(game.get("app_id")).strip() for game in installed_games if game.get("app_id")}
    print(f"Installed game IDs: {installed_ids}")  # Log installed game IDs
    
    uninstalled_games = []

    for game in all_games:
        # Safely check if 'app_id' exists in the game dictionary
        app_id = str(game.get("app_id")).strip()  # Convert to string and strip spaces
        if app_id and app_id not in installed_ids:
            uninstalled_games.append(game)

    print(f"Uninstalled games identified: {len(uninstalled_games)}")  # Log number of uninstalled games
    return uninstalled_games

def get_drives():
    """Detect all available drives on the system."""
    if platform.system() == "Windows":
        return [f"{chr(i)}:\\" for i in range(65, 91) if os.path.exists(f"{chr(i)}:\\")]
    elif platform.system() == "Linux":
        return [line.split()[0] for line in os.popen("df -h --output=source").readlines()[1:]]
    elif platform.system() == "Darwin":  # macOS
        return [line.split()[2] for line in os.popen("mount").readlines()]
    return []

# GUI Class
class SteamRouletteGUI:
    def __init__(self, root, installed_games, drives):
        self.root = root
        self.installed_games = installed_games
        self.excluded_games = []
        self.uninstalled_games = []
        self.selected_game = None
        self.drives = drives
        self.api_key = self.load_api_key()
        self.cache_dir = create_cache_directory()

        # Define color schemes
        self.light_mode_bg = "#ffffff"
        self.dark_mode_bg = "#2e2e2e"
        self.light_mode_fg = "#000000"
        self.dark_mode_fg = "#ffffff"

        # Preload the images
        self.preloaded_images = {}
        # Preload Header Images
        self.preload_images()
        # Load saved Game Exclusions
        self.load_exclusions()

        self.canvas_frame = tk.Frame(root, bg=self.light_mode_bg)
        self.canvas_frame.pack(pady=5)

        # Path to the folder containing the header images
        if getattr(sys, 'frozen', False):  # If running as an executable
            base_path = sys._MEIPASS
        else:  # If running as a script
            base_path = os.path.dirname(os.path.abspath(__file__))

        # Initialize animation speed (starting value)
        self.initial_animation_speed = 50  # Adjust this as needed
        self.animation_speed = self.initial_animation_speed

        # Create a frame to contain the game name label and other elements
        frame = tk.Frame(self.root, bg=self.light_mode_bg)
        frame.pack(side="top", pady=5)

        # Apply light mode to the frame
        self.update_theme(frame, self.light_mode_bg, self.light_mode_fg)

        # Set initial animation speed
        self.animation_speed = 200  # Controls the distance moved per frame
        self.frame_delay = 16  # Controls the speed of the animation (time between frames)

        self.root.title("Steam Roulette")
        width = 600
        height = 750

        # get screen width and height
        ws = root.winfo_screenwidth()
        hs = root.winfo_screenheight()

        # calculate x and y coordinates for the Tk root window
        x = (ws/2) - (width/2)
        y = (hs/2) - (height/2)

        self.root.geometry('%dx%d+%d+%d' % (width, height, x, y))
        self.root.resizable(False, False)
        

        # Define the relative path to the 'header_images' folder
        self.header_images_folder = os.path.join((sys.executable), "image_cache")

        # Try to load images locally, if they don't exist, fallback to Steam API
        if os.path.exists(self.header_images_folder) and os.listdir(self.header_images_folder):
            self.header_images = self.load_header_images(self.header_images_folder)

        # Canvas
        self.canvas = tk.Canvas(self.root, width=600, height=300, bg="black")
        self.canvas.pack(pady=1)
        print(f"Canvas initialized: {self.canvas}")

        # Display a random header image on startup
        self.display_random_header_image()

        # Label displaying "Games Found on Drives"
        self.label_game_count = tk.Label(root, text=self.generate_games_found_text(), font=("Arial", 10))

        # Get the width of the window and place the label in the top-right corner
        window_width = root.winfo_width()  # Get current width of the window
        self.label_game_count.place(x=window_width - 5, y=5, anchor='ne')  # 10px from the right and 10px from the top

        # Label displaying copyright notice in the top-left corner
        self.copyright_notice = tk.Label(root, text="© Streetbackguy 2024", font=("Arial", 8))
        self.copyright_notice.place(relx=0.0, rely=0.0, anchor='nw', x=5, y=5)

        # Welcome label
        self.label_welcome = tk.Label(frame, text="Welcome to Steam Roulette!", font=("Arial", 16), bg=self.light_mode_bg)
        self.label_welcome.grid(row=1, pady=5)

        # Game name label
        self.label_game_name = tk.Label(frame, text="", wraplength=600, font=("Arial", 20), bg=self.light_mode_bg)
        self.label_game_name.grid(row=2, pady=5)

        # Initial theme mode (light mode by default)
        self.is_dark_mode = False

        # Create a frame for the lower-left corner buttons
        self.button_frame = tk.Frame(root, bg=self.light_mode_bg)
        self.button_frame.pack(pady=5)
        self.button_frame.place(relx=0.0, rely=1.0, anchor='sw', x=2, y=-2)  # Padding for the frame

        # Button to set the API Key
        self.button_set_api_key = tk.Button(self.button_frame, text="Set API Key", command=self.set_api_key, state=tk.NORMAL, font=("Arial", 10))
        self.button_set_api_key.grid(row=0, column=0, pady=2, padx=2)

        # Create a button to set the Steam User ID manually
        self.button_set_user_id = tk.Button(self.button_frame, text="Set Steam User ID", command=self.set_user_id_key, state=tk.NORMAL, font=("Arial", 10))
        self.button_set_user_id.grid(row=0, column=1, pady=2, padx=2)

        # Button to toggle dark mode
        self.button_toggle_theme = tk.Button(self.button_frame, text="Toggle Dark Mode", command=self.toggle_theme, font=("Arial", 10))
        self.button_toggle_theme.grid(row=0, column=2, pady=2, padx=2)

        try:
            # Set the window and taskbar icon
            self.root.iconbitmap(ICON_PATH)  # Set .ico for the window
            self.root.iconphoto(True, tk.PhotoImage(file=ICON_PATH))  # Set taskbar icon

        except Exception as e:
            print(f"Error setting window icon: {e}")

        # Create a frame to contain the game name label and other elements
        utility_frame = tk.Frame(self.root, bg=self.light_mode_bg)
        utility_frame.pack(pady=5)

        # Apply light mode to the utility frame
        self.update_theme(utility_frame, self.light_mode_bg, self.light_mode_fg)

        # Button to spin the wheel
        self.selected_num_games = None
        self.button_spin = tk.Button(utility_frame, text="Spin the Wheel", command=self.spin_wheel, font=("Arial", 14))
        self.button_spin.grid(row=0, column=0, pady=10, padx=10, sticky="n", columnspan=2)

        # Button to launch the selected game
        self.button_launch = tk.Button(utility_frame, text="Launch/Install Game", command=self.launch_game, state=tk.DISABLED, font=("Arial", 10))
        self.button_launch.grid(row=1, column=0, pady=5, padx=4)

        # Button to go to the Steam store for the selected game
        self.button_store = tk.Button(utility_frame, text="Steam Storepage", command=self.open_store, state=tk.DISABLED, font=("Arial", 10))
        self.button_store.grid(row=1, column=1, pady=5, padx=4)

        # Create a container frame to hold the button and label
        self.frame_controls = tk.Frame(self.root)
        self.frame_controls.place(anchor='w', x=4, y=625)

        # Configure columns for centering
        for col in range(3):  # Assuming a grid with 3 columns for flexibility
            self.frame_controls.grid_columnconfigure(col, weight=1)

        # Add a button that triggers the popup to input the number of games
        self.button_set_number_of_games = tk.Button(
            self.frame_controls, text="Set Number of Games", command=self.set_number_of_games
        )
        self.button_set_number_of_games.grid(row=0, column=1, pady=2)  # Centered in row 0, column 1

        # Label to show the number of games selected (initially empty)
        self.label_number_of_games = tk.Label(
            self.frame_controls, text="Number of games to spin:\nAll Games", font=("Arial", 8)
        )
        self.label_number_of_games.grid(row=1, column=1, pady=2)  # Centered in row 1, column 1

        # Exclude Games Button
        self.button_exclude = tk.Button(
            self.frame_controls, text="Exclude Games", command=self.exclude_games, font=("Arial", 10)
        )
        self.button_exclude.grid(row=2, column=1, pady=2)  # Centered in row 2, column 1

        # Excluded Games Count Label
        self.excluded_label = tk.Label(
            self.frame_controls, text=f"Excluded Games:\n{len(self.excluded_games)}", font=("Arial", 8)
        )
        self.excluded_label.grid(row=3, column=1, pady=2)  # Centered in row 3, column 1

        # Create a frame to contain the game name label and other elements
        self.yes_no_frame = tk.Frame(self.root, bg=self.light_mode_bg)
        self.yes_no_frame.place(relx=1.0, rely=1.0, anchor='se', x=-2, y=-2)  # Padding for the frame

        # Label for Selecting whether to include uninstalled games or not
        self.label_include_uninstalled_games = tk.Label(self.yes_no_frame, text="Include Uninstalled Games?", font=("Arial", 8))
        self.label_include_uninstalled_games.grid(row=0, column=0, columnspan=2, pady=2)

        # Yes button
        self.button_yes = tk.Button(self.yes_no_frame, text="Yes", command=self.on_yes_click)
        self.button_yes.grid(row=1, column=0, pady=2, padx=2)
        
        # No button
        self.button_no = tk.Button(self.yes_no_frame, text="No", command=self.on_no_click)
        self.button_no.grid(row=1, column=1, pady=2, padx=2)

        self.active_images = []
        self.selected_game_image = None
        self.selected_game_item = None
        self.animation_id = None

        try:
            # Use resource_path to get the correct logo path
            logo_path = resource_path("SteamRouletteLogo.png")
            print(f"Trying to load logo from: {logo_path}")
            
            if not os.path.exists(logo_path):
                raise FileNotFoundError(f"Logo file not found at: {logo_path}")
            
            # Load the logo image
            logo_image = Image.open(logo_path)
            logo_image_tk = ImageTk.PhotoImage(logo_image)

            # Display logo
            self.label_logoimage = tk.Label(frame, image=logo_image_tk, bg=self.light_mode_bg)
            self.label_logoimage.image = logo_image_tk  # Keep reference to avoid garbage collection
            self.label_logoimage.grid(row=0, pady=5)

        except FileNotFoundError as fnfe:
            print(fnfe)
            # In case logo or icon is missing, display a fallback message
            self.label_logoimage = tk.Label(frame, text="Logo Missing", font=("Arial", 16), bg=self.light_mode_bg)
            self.label_logoimage.grid(row=0, pady=5)

        except Exception as e:
            print(f"Error: {e}")

        try:
            # Get the path for the .ico file
            icon_path = resource_path("SteamRouletteIcon.ico")
            print(f"Trying to load icon from: {icon_path}")

            # Ensure the icon file exists
            if not os.path.exists(icon_path):
                raise FileNotFoundError(f"Icon file not found at: {icon_path}")

            # Set the window icon
            self.root.iconbitmap(icon_path)
            print("Window icon successfully set.")

        except FileNotFoundError as fnfe:
            print(fnfe)
        except Exception as e:
            print(f"Error setting window icon: {e}")

        # Set Light Mode
        self.set_light_mode()

        # Display a random header image on startup
        self.display_random_header_image()

    def preload_images(self):
        """Preload images for both installed and uninstalled games using threading."""
        def preload_image(game):
            app_id = game.get("app_id")
            if not app_id or app_id in self.preloaded_images:
                return
            img = fetch_header_image(app_id, self.cache_dir)
            if img:
                self.preloaded_images[app_id] = img

        # Preload images in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(preload_image, self.installed_games + getattr(self, 'uninstalled_games', []))

    def generate_games_found_text(self):
        """Generate a summary of games found on each drive."""
        drives_text = ["Installed\nGames Found:"]
        for drive in self.drives:
            games_count = len([game for game in self.installed_games if game.get('path', '').startswith(drive)])
            drives_text.append(f"{drive} {games_count} games")
        return "\n".join(drives_text)

    def load_api_key(self):
        """Load API key from the file in the same directory as the .exe."""
        api_key_path = "apikey.txt"
        if os.path.exists(api_key_path):
            with open(api_key_path, "r") as file:
                return file.read().strip()
        return ""

    def set_api_key(self):
        """Prompt user for an API key and save it to a file in the current directory."""
        bg_color = self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg
        fg_color = self.dark_mode_fg if self.is_dark_mode else self.light_mode_fg

        api_key_popup = tk.Toplevel(self.root)
        api_key_popup.title("Enter API Key")
        
        width = 350
        height = 150

        hs = api_key_popup.winfo_screenheight()
        ws = api_key_popup.winfo_screenwidth()

        x = (ws/6) - (width/10)
        y = (hs/5) - (height/5)

        api_key_popup.geometry('%dx%d+%d+%d' % (width, height, x, y))

        self.update_theme(api_key_popup, bg_color, fg_color)

        label = tk.Label(api_key_popup, text="Please enter your Steam API Key:", bg=bg_color, fg=fg_color)
        label.pack(pady=10)

        entry = tk.Entry(api_key_popup, bg=bg_color, fg=fg_color)
        entry.pack(pady=5)

        def submit():
            api_key = entry.get()
            if api_key:
                with open("apikey.txt", "w") as file:
                    file.write(api_key)
                self.api_key = api_key
                messagebox.showinfo("API Key", "API Key saved successfully.")
                api_key_popup.destroy()
            else:
                messagebox.showerror("Error", "API Key not entered.")

        submit_button = tk.Button(api_key_popup, text="Submit", command=submit, bg=bg_color, fg=fg_color)
        submit_button.pack(pady=10)

    def fetch_steam_user_id(self, api_key, steam_id):
        """Fetch Steam User ID automatically using the Steam API."""
        url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        params = {
            "key": api_key,
            "steamids": steam_id  # Placeholder Steam ID for testing; it will be replaced dynamically
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()  # Check if the response is successful
            data = response.json()

            if "response" in data and "players" in data["response"]:
                player_info = data["response"]["players"][0]
                steam_id = player_info.get("steamid")
                print(f"Successfully fetched Steam User ID: {steam_id}")
                return steam_id
            else:
                print("Could not fetch Steam User ID.")
                return None
            
        except Exception as e:
            print(f"Error fetching Steam User ID: {e}")
            return None

    def load_user_id_key(self):
        """Load Steam User ID from the file if available, else prompt for it."""
        user_id_path = "steamuserid.txt"
        if os.path.exists(user_id_path):
            with open(user_id_path, "r") as file:
                return file.read().strip()  # Return the Steam User ID if found
        else:
            return ""  # Return an empty string if no Steam User ID is found

    def set_user_id_key(self):
        """Prompt the user for a Steam User ID and save it to a file."""
        bg_color = self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg
        fg_color = self.dark_mode_fg if self.is_dark_mode else self.light_mode_fg

        user_id_popup = tk.Toplevel(self.root)
        user_id_popup.title("Enter Steam User ID")
        
        width = 350
        height = 150

        hs = user_id_popup.winfo_screenheight()
        ws = user_id_popup.winfo_screenwidth()

        x = (ws/6) - (width/10)
        y = (hs/5) - (height/5)

        user_id_popup.geometry('%dx%d+%d+%d' % (width, height, x, y))

        self.update_theme(user_id_popup, bg_color, fg_color)

        label = tk.Label(user_id_popup, text="Please enter your Steam User ID:", bg=bg_color, fg=fg_color)
        label.pack(pady=10)

        entry = tk.Entry(user_id_popup, bg=bg_color, fg=fg_color)
        entry.pack(pady=5)

        def submit():
            steam_user_id = entry.get()
            if steam_user_id:
                with open("steamuserid.txt", "w") as file:
                    file.write(steam_user_id)
                messagebox.showinfo("Success", "Steam User ID saved successfully.")
                user_id_popup.destroy()
            else:
                messagebox.showerror("Error", "Steam User ID not entered.")

        submit_button = tk.Button(user_id_popup, text="Submit", command=submit, bg=bg_color, fg=fg_color)
        submit_button.pack(pady=10)

    def load_header_images(self, folder_path):
        """Load all image files from the specified folder."""
        image_files = []
        for filename in os.listdir(folder_path):
            # Check if the file is a valid image (add more file extensions if needed)
            if filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                image_files.append(os.path.join(folder_path, filename))
        return image_files
    
    def load_uninstalled_games_images(self):
        """Load images for uninstalled games in a background thread."""
        # Simulate loading process for uninstalled game images (use your actual preloading logic here)
        self.preload_images()

        # Once images are loaded, safely update the UI
        self.root.after(0, self.update_ui_after_loading_images)

    def update_ui_after_loading_images(self):
        """Update UI elements after loading uninstalled game images."""
        # Now that images are preloaded, you can enable the button or update the canvas
        self.button_spin.config(state=tk.NORMAL, text="Spin the Wheel")
        print("Uninstalled games images have been loaded.")

    def on_yes_click(self):
        """Include uninstalled games in the cycle list and preload their images."""
        if not self.api_key:
            messagebox.showerror("Error", "Please set your Steam API key first.")
            return

        # Disable the Spin button while loading images
        self.button_spin.config(state=tk.DISABLED, text="Loading...")

        user_id = self.load_user_id_key()
        if not user_id:
            user_id = self.fetch_steam_user_id(self.api_key, "Your Placeholder SteamID")
            if user_id:
                self.save_user_id_key(user_id)
            else:
                messagebox.showerror("Error", "Could not fetch Steam User ID.")
                return

        all_games = get_all_games(self.api_key, user_id)
        if not all_games:
            messagebox.showerror("Error", "No games were fetched from the Steam API.")
            return

        # Map 'appid' to 'app_id' for uninstalled games
        uninstalled_games = [{**game, "app_id": str(game["appid"])} for game in all_games if "appid" in game]

        installed_ids = {game["app_id"] for game in self.installed_games}
        new_uninstalled_games = [game for game in uninstalled_games if game["app_id"] not in installed_ids]

        if new_uninstalled_games:
            # Add uninstalled games to the list
            self.uninstalled_games = new_uninstalled_games
            self.installed_games.extend(new_uninstalled_games)

            # Load images for uninstalled games asynchronously
            threading.Thread(target=self.load_images_in_parallel, daemon=True).start()

            messagebox.showinfo("Uninstalled Games Added", f"Included {len(new_uninstalled_games)} uninstalled games.")
        else:
            messagebox.showinfo("No Uninstalled Games", "No uninstalled games were found to include.")

    def on_no_click(self):
        """Remove uninstalled games from the cycle list."""
        if hasattr(self, 'uninstalled_games'):
            uninstalled_ids = {game["app_id"] for game in self.uninstalled_games}
            self.installed_games = [game for game in self.installed_games if game["app_id"] not in uninstalled_ids]
            del self.uninstalled_games  # Clear the uninstalled games list
            messagebox.showinfo("Uninstalled Games Removed", "Uninstalled games have been removed from the cycle.")

    def load_images_in_parallel(self, batch_size=10):
        """Preload images for uninstalled games in batches."""
        games_to_load = self.uninstalled_games
        for i in range(0, len(games_to_load), batch_size):
            batch = games_to_load[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=5) as executor:
                executor.map(lambda game: fetch_header_image(game["app_id"], self.cache_dir), batch)
        self.root.after(0, self.on_images_preloaded)

    def on_images_preloaded(self):
        """Called when all images are preloaded."""
        self.is_images_preloaded = True

        # Re-enable the Spin button after images are loaded
        self.button_spin.config(state=tk.NORMAL, text="Spin the Wheel")
        print("Images for uninstalled games have been loaded and cached.")

    def load_image_for_game(self, game, cache_dir):
        """Load and cache the image for a specific game."""
        app_id = game["app_id"]
        cache_file_path = os.path.join(cache_dir, f"{app_id}.jpg")

        # Check if the image already exists in the cache
        if os.path.exists(cache_file_path):
            print(f"Using cached image for app_id {app_id}")
            return  # Skip if the image is already cached

        # Fetch the image and save it to the cache
        print(f"Fetching image for app_id {app_id}...")
        img = fetch_header_image(app_id)  # Replace with actual image fetching logic

        if img:
            # Save the image to the cache
            img.save(cache_file_path, "JPEG")
            print(f"Image cached for app_id {app_id}")
        else:
            print(f"Failed to fetch image for app_id {app_id}")

    def start_animation(self):
        """Start the spinning animation after loading images."""
        # Ensure that images are properly preloaded
        if not self.preloaded_images:
            print("Error: No images were preloaded.")
            return

        # Now start the animation
        self.cycle_images(self.installed_games + getattr(self, 'uninstalled_games', []))

    def display_random_header_image(self):
        """Display a random header image on the canvas initially."""
        random_game = random.choice(self.installed_games)
        random_app_id = random_game["app_id"]  # Get the app_id of the selected game
        print(f"Fetching image for app_id {random_app_id}")

        random_image = fetch_header_image(random_app_id, self.cache_dir)
        
        if random_image:
            print(f"Image fetched successfully for app_id {random_app_id}")
        
        # Resize the image to match the canvas size
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        print(f"Canvas width: {canvas_width}, Canvas height: {canvas_height}")
        
        random_image_resized = random_image.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)

        random_image_tk = ImageTk.PhotoImage(random_image_resized)

        # Make sure to keep a reference to the image
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=random_image_tk, anchor=tk.CENTER)

        # Store the image reference to prevent it from being garbage collected
        self.active_images = [(random_image_tk, random_image)]

        print("Random header image displayed on canvas.")

        # Force Tkinter to process the events and refresh the canvas
        self.canvas.update_idletasks()
        self.root.update()

    def display_image_from_url(self, image_url):
        """Download and display the image from a URL on the canvas."""
        try:
            img_data = requests.get(image_url).content
            img = Image.open(io.BytesIO(img_data))
            img_resized = img.resize((600, 300), Image.Resampling.LANCZOS)  # Resize image to fit the canvas
            img_tk = ImageTk.PhotoImage(img_resized)

            # Display the image on the canvas
            self.canvas.create_image(0, 0, anchor='nw', image=img_tk)

            # Keep a reference to the image to avoid garbage collection
            self.canvas.image = img_tk  # Keep a reference so the image stays in memory

        except Exception as e:
            print(f"Error loading image from URL {image_url}: {e}")

    def set_light_mode(self):
        """Set the window to light mode."""
        self.update_theme(self.root, self.light_mode_bg, self.light_mode_fg)

    def set_dark_mode(self):
        """Set the window to dark mode."""
        self.update_theme(self.root, self.dark_mode_bg, self.dark_mode_fg)

    def update_theme(self, widget, bg_color, fg_color):
        """Recursively update the background and foreground color for all widgets."""
        # Update background color for the widget
        widget.config(bg=bg_color)

        # If the widget supports fg (foreground), update it
        if isinstance(widget, (tk.Button, tk.Label, tk.Entry, tk.Text)):  # Check if widget supports fg
            widget.config(fg=fg_color)

        # Recursively update child widgets
        for child in widget.winfo_children():
            if isinstance(child, tk.Widget):  # Only apply to Tkinter widgets
                self.update_theme(child, bg_color, fg_color)

    def toggle_theme(self):
        """Toggle between light mode and dark mode."""
        # Now, toggle the theme for the entire window
        if self.is_dark_mode:
            self.set_light_mode()
        else:
            self.set_dark_mode()

        # Toggle the mode flag after applying the theme
        self.is_dark_mode = not self.is_dark_mode

    def toggle_spin_button(self):
        """Toggle the spin button between Spin and Re-roll."""
        if self.button_spin.cget("text") == "Spin the Wheel":
            # When Spin Wheel is clicked, call spin_wheel method
            self.spin_wheel()
        else:
            # When Re-Roll is clicked, rerun the spin with the same number of games
            self.spin_wheel()

        if not self.is_images_preloaded:
            messagebox.showerror("Error", "Please wait until images are preloaded.")
            return  # Exit if images are not preloaded yet

        print("Spin Button clicked. Starting the animation...")
        self.start_animation()  # Start the animation

    def set_number_of_games(self):
        """Popup window to ask user for how many games to spin between."""
        bg_color = self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg
        fg_color = self.dark_mode_fg if self.is_dark_mode else self.light_mode_fg

        self.popup = tk.Toplevel(self.root)
        self.popup.title("Select Number of Games")

        width = 350
        height = 150

        hs = self.popup.winfo_screenheight()
        ws = self.popup.winfo_screenwidth()

        x = (ws/6) - (width/10)
        y = (hs/5) - (height/5)

        self.popup.geometry('%dx%d+%d+%d' % (width, height, x, y))

        self.update_theme(self.popup, bg_color, fg_color)

        # Label to guide the user
        label = tk.Label(self.popup, text="Enter number of games to spin:", bg=bg_color, fg=fg_color)
        label.pack(pady=10)

        # Entry widget to accept input
        self.num_games_entry = tk.Entry(self.popup, bg=bg_color, fg=fg_color)
        self.num_games_entry.pack(pady=5)

        # Submit button to get the value from the entry box
        submit_button = tk.Button(self.popup, text="Submit", command=self.submit_number_of_games, bg=bg_color, fg=fg_color)
        submit_button.pack(pady=10)

    def submit_number_of_games(self):
        """Retrieve the number of games inputted and update the animation."""
        try:
            # Get the value entered by the user
            num_games_to_spin = int(self.num_games_entry.get())
            
            # Check if the input is within a valid range
            if num_games_to_spin > len(self.installed_games) or num_games_to_spin < 1:
                raise ValueError("Number must be between 1 and the total number of games.")
            
            # Set the number of games to spin
            self.selected_num_games = num_games_to_spin  # Store the selected number of games
            
            # Update the label to show the selected number of games
            self.label_number_of_games.config(text=f"Number selected:\n {num_games_to_spin}")

            # Close the popup window after submitting
            self.popup.destroy()

            # Update the button text to "Spin Wheel" once the number is set
            self.button_spin.config(state=tk.NORMAL, text="Spin the Wheel")

        except ValueError as e:
            # If input is invalid, show an error message
            error_label = tk.Label(self.popup, text=f"Error: {e}", fg="red", bg=self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg)
            error_label.pack()

    def clear_exclusions(self):
        """Clear all exclusions and restore excluded games to the installed list."""
        print(f"Before clearing exclusions:\nExcluded: {self.excluded_games}\nInstalled: {[game['name'] for game in self.installed_games]}")

        # Restore the excluded games back into installed_games
        for game_id in self.excluded_games:
            # Find the game by app_id in installed games
            restored_game = next(
                (game for game in self.installed_games if game["app_id"] == game_id), 
                None
            )
            
            if restored_game:
                print(f"Restoring game: {restored_game['name']} to installed games.")
            else:
                print(f"Could not restore game with ID {game_id}, it might already be in installed games.")

        # Clear exclusions after restoring
        self.excluded_games = []

        # Update the UI
        self.excluded_label.config(text=f"Excluded Games:\n{len(self.excluded_games)}")

        # Print for verification
        print(f"After clearing exclusions:\nExcluded: {self.excluded_games}\nInstalled: {[game['name'] for game in self.installed_games]}")

        self.exclude_games()  # Rebuild the checklist
        self.save_exclusions()
        
        # Notify the user
        messagebox.showinfo("Clear Exclusions", "All exclusions have been cleared and games re-added to the checklist.")

    def exclude_games(self):
        """Open a new window to allow users to select games to exclude, with search functionality."""
        if hasattr(self, "exclude_popup") and self.exclude_popup.winfo_exists():
            self.exclude_popup.lift()  # Bring the existing popup to the front
            return

        self.exclude_popup = tk.Toplevel(self.root)
        self.exclude_popup.title("Exclude Games")

        width = 600
        height = 500

        hs = self.exclude_popup.winfo_screenheight()
        ws = self.exclude_popup.winfo_screenwidth()

        x = (ws/24) - (width/24)
        y = (hs/3) - (height/3)

        self.exclude_popup.geometry('%dx%d+%d+%d' % (width, height, x, y))
        self.exclude_popup.resizable(False, False)

        # Apply dark mode if enabled
        bg_color = self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg
        fg_color = self.dark_mode_fg if self.is_dark_mode else self.light_mode_fg
        self.update_theme(self.exclude_popup, bg_color, fg_color)

        # Adding mouse wheel scroll functionality
        def on_mouse_wheel(event):
            """Scroll the canvas when mouse wheel is used."""
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")  # Adjust scroll amount

        # Create a search input box at the top
        search_label = tk.Label(self.exclude_popup, text="Search:", bg=bg_color, fg=fg_color, font="12")
        search_label.pack(pady=2, padx=2)
        
        search_var = tk.StringVar()
        search_entry = tk.Entry(self.exclude_popup, textvariable=search_var, bg=bg_color, fg=fg_color, font="12")
        search_entry.pack(pady=6, padx=2)

        def update_search_results(*args):
            """Update the checklist dynamically based on the search input."""
            search_text = search_var.get().lower()
            
            # Clear the current game list
            for widget in scrollable_frame.winfo_children():
                widget.destroy()

            # Filter the games based on the search text
            filtered_games = [game for game in sorted_games if search_text in game["name"].lower()]
            
            # Create checkboxes for filtered games
            for game in filtered_games:
                var = tk.BooleanVar(value=game["app_id"] in self.excluded_games)  # Ensure checkbox reflects exclusion
                cb = tk.Checkbutton(scrollable_frame, text=game["name"], variable=var, bg=bg_color, fg=fg_color, selectcolor=bg_color, font="12")
                cb.pack(anchor="w")
                game_vars[game["app_id"]] = var
        
        # Bind the search input to the update function
        search_var.trace_add("write", update_search_results)

        # Scrollable frame for the list of games
        canvas = tk.Canvas(self.exclude_popup, bg=bg_color, bd=0, highlightthickness=0)
        scrollable_frame = tk.Frame(canvas, bg=bg_color)
        scrollbar = tk.Scrollbar(self.exclude_popup, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind_all("<MouseWheel>", on_mouse_wheel)  # Windows and Mac mouse wheel scroll

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True, padx= 4)
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Get installed games to populate the exclude list
        all_games = self.installed_games  # Use the installed_games as the base
        sorted_games = sorted(all_games, key=lambda game: game["name"].lower())

        # Log for debugging
        print(f"Populating exclude list with games: {[game['name'] for game in sorted_games]}")

        # Initialize the game vars dictionary for checkboxes
        game_vars = {}

        # Initially populate with all games
        for game in sorted_games:
            var = tk.BooleanVar(value=game["app_id"] in self.excluded_games)  # Ensure checkbox reflects exclusion
            cb = tk.Checkbutton(scrollable_frame, text=game["name"], variable=var, bg=bg_color, fg=fg_color, selectcolor=bg_color, font="12")
            cb.pack(anchor="w")
            game_vars[game["app_id"]] = var

        def apply_exclusions():
            """Apply the exclusions and update the list of excluded games."""
            self.excluded_games = [app_id for app_id, var in game_vars.items() if var.get()]
            self.excluded_label.config(text=f"Excluded Games:\n{len(self.excluded_games)}")
            self.save_exclusions()
            messagebox.showinfo("Exclusions Applied", f"Excluded {len(self.excluded_games)} games.")
            self.exclude_games()

        # Apply button
        apply_button = tk.Button(self.exclude_popup, text="Apply", command=apply_exclusions, bg=bg_color, fg=fg_color, font="12")
        apply_button.pack(pady=4, padx=4)

        # Clear exclusions button
        clear_button = tk.Button(self.exclude_popup, text="Clear", command=self.clear_exclusions, bg=bg_color, fg=fg_color, font="12")
        clear_button.pack(pady=4, padx=4)

    def load_exclusions(self):
        """Load exclusions from a file."""
        if os.path.exists("excluded_games.json"):
            try:
                with open("excluded_games.json", "r") as file:
                    excluded_game_ids = json.load(file)
                    self.excluded_games = excluded_game_ids
                    print(f"Loaded exclusions: {self.excluded_games}")
            except Exception as e:
                print(f"Error loading exclusions: {e}")

    def save_exclusions(self):
        """Save exclusions to a file."""
        try:
            with open("excluded_games.json", "w") as file:
                json.dump(self.excluded_games, file)
                print(f"Saved exclusions: {self.excluded_games}")
        except Exception as e:
            print(f"Error saving exclusions: {e}")

    def spin_wheel(self):
        """Start the spinning animation based on the selected number of games."""
        if not self.selected_num_games:
            num_games_to_spin = len(self.installed_games)  # Spin all installed games by default
        else:
            num_games_to_spin = self.selected_num_games  # Use user-specified count

        # Filter games with valid app_id and exclude the ones that are in excluded_games
        valid_games = [game for game in self.installed_games if "app_id" in game and game["app_id"] not in self.excluded_games]
        if not valid_games:
            print("Error: No valid games found to spin.")
            return

        selected_games = random.sample(valid_games, min(num_games_to_spin, len(valid_games)))
        print(f"Selected games: {', '.join([game['name'] for game in selected_games])}")

        # Assign one valid game as the selected game
        self.selected_game = random.choice(selected_games)
        print(f"Selected game: {self.selected_game.get('name', 'Unknown')} (app_id: {self.selected_game.get('app_id')})")

        # Disable the spin button while the animation is running
        self.button_spin.config(state=tk.DISABLED, text="Re-Roll")
        self.button_launch.config(state=tk.DISABLED)
        self.button_store.config(state=tk.DISABLED)

        # Pass only valid games to cycle_images
        self.cycle_images(selected_games)

    def reroll_game(self):
        """Handle the reroll button click."""
        # Reset the animation speed to the initial value for a fresh start
        self.animation_speed = self.initial_animation_speed

        # Disable the selected game image and buttons
        if self.selected_game_item:
            self.canvas.delete(self.selected_game_item)  # Remove the previous selected game image

        # Disable buttons while rerolling
        self.button_launch.config(state=tk.DISABLED)
        self.button_store.config(state=tk.DISABLED)

        # Select a new game
        self.selected_game = random.choice(self.installed_games)

        # Display the selected game image (it will be a new one)
        self.display_selected_game()

    def load_cache_images(self, images_to_display):
        """Preload all missing images from the cache directory in a separate thread."""
        def preload():
            # Update the label to show "ACTIVE"
            self.root(self.label_preloading.config(text="Preloading: ACTIVE"))

            cache_dir = os.path.join(os.path.dirname(sys.executable), "image_cache")
            # Check if the directory exists, create it if it doesn't
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
                print(f"Cache directory created at: {cache_dir}")
            else:
                print(f"Cache directory already exists at: {cache_dir}")

            for index, game in enumerate(images_to_display):
                app_id = game["app_id"]
                if app_id not in self.preloaded_images:
                    # Attempt to load the image from the cache
                    cache_file_path = os.path.join(cache_dir, f"{app_id}.jpg")
                    if os.path.exists(cache_file_path):
                        try:
                            print(f"Preloading image from cache for {game['name']} (app_id: {app_id})")
                            img = Image.open(cache_file_path)
                            img_resized = img.resize((600, 300), Image.Resampling.LANCZOS)  # Resize for consistency
                            self.preloaded_images[app_id] = img_resized  # Store in preloaded_images
                        except Exception as e:
                            print(f"Error loading image from cache for {game['name']} (app_id: {app_id}): {e}")
                    else:
                        print(f"Warning: No cache image found for {game['name']} (app_id: {app_id})")

            # Update the label back to "IDLE" after preloading is done
            self.root.after(0, lambda: self.label_preloading.config(text="Preloading: IDLE"))

            # Safely call cycle_images on the main thread
            self.root.after(0, lambda: self.cycle_images(images_to_display))

        # Start the preloading process in a separate thread
        threading.Thread(target=preload, daemon=True).start()

    def prepare_images(self, games):
        """Prepare images for the spinning effect, including installed and uninstalled games."""
        self.preloaded_images = {}
        for game in games:
            app_id = game.get("app_id")
            if not app_id:
                continue
            # Load image for each game and store it in preloaded_images
            self.preloaded_images[app_id] = fetch_header_image(app_id, self.cache_dir)

        # Ensure self.selected_game is properly initialized
        if self.selected_game is not None:
            self.selected_game_image = self.load_image(self.selected_game["app_id"])
        else:
            # Handle the case where selected_game is None (e.g., set a placeholder)
            print("Warning: selected_game is None, using placeholder.")
            self.selected_game_image = create_placeholder_image("No Game Selected")

        # Clear the canvas before displaying the selected game's image
        self.canvas.delete("all")  # Clear all existing images from the canvas

        # Display the selected game image (if selected_game is valid)
        if self.selected_game_image:
            img_tk = ImageTk.PhotoImage(self.selected_game_image)
            self.canvas.create_image(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2, image=img_tk, anchor=tk.CENTER)
            self.active_images = [(img_tk, self.selected_game_image)]  # Store the image for animation
        
        print("Image preparation complete.")

    def load_image(self, app_id):
        """Load and resize an image, checking the cache if not in preloaded_images."""
        img = self.preloaded_images.get(app_id)
        if not img:
            img = fetch_header_image(app_id, self.cache_dir)
            if img:
                self.preloaded_images[app_id] = img
        if img:
            return img.resize((600, 300), Image.Resampling.LANCZOS)
        return create_placeholder_image("Image Unavailable")
    
    def cycle_images(self, selected_games):
        """Cycle through the images as part of the spinning effect, with no padding and images resized to fit the canvas."""
        self.active_images = []
        self.label_welcome.config(text="Rolling...")

        # Get canvas dimensions
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # Preload and ensure images for the selected games
        for game in selected_games:
            app_id = game["app_id"]
            img = self.preloaded_images.get(app_id)
            if img is None:
                # Attempt to load from cache or fallback to placeholder
                img = fetch_header_image(app_id, self.cache_dir)
                if img:
                    self.preloaded_images[app_id] = img

        # Prepare images for animation
        x_position = 0  # Starting x-coordinate for images on the canvas
        for game in selected_games:
            app_id = game["app_id"]
            img = self.preloaded_images.get(app_id)
            if img is None:
                print(f"Error: No image found for game {game['name']} (app_id: {app_id})")
                continue  # Skip this game if no image is found

            # Resize the image to fit the canvas dimensions
            img_resized = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)

            # Convert the image to Tkinter-compatible format
            try:
                img_tk = ImageTk.PhotoImage(img_resized)
                image_item = self.canvas.create_image(x_position, canvas_height // 2, image=img_tk, anchor=tk.CENTER)
                self.active_images.append((image_item, img_tk))  # Keep reference to avoid garbage collection
                x_position += canvas_width  # No padding between images
            except Exception as e:
                print(f"Error processing image for {game['name']} (app_id: {app_id}): {e}")
                continue

        # Add the selected game's image at the end of the sequence
        try:
            selected_img = self.preloaded_images.get(self.selected_game["app_id"])
            if selected_img is None:
                # Attempt to load if not already preloaded
                selected_img = fetch_header_image(self.selected_game["app_id"], self.cache_dir)
                self.preloaded_images[self.selected_game["app_id"]] = selected_img

            selected_img_resized = selected_img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
            selected_img_tk = ImageTk.PhotoImage(selected_img_resized)
            image_item = self.canvas.create_image(x_position, canvas_height // 2, image=selected_img_tk, anchor=tk.CENTER)
            self.active_images.append((image_item, selected_img_tk))  # Add selected game to the list
        except Exception as e:
            print(f"Error processing selected game image: {e}")
            return  # Exit if the selected game's image processing fails

        # Start the animation
        self.animate_images()

    def animate_images(self):
        """Animate the images sliding across the canvas with conditional slowdown."""
        canvas_width = self.canvas.winfo_width()  # Get the width of the canvas
        include_uninstalled_games = hasattr(self, 'uninstalled_games') and self.uninstalled_games

        # Calculate total distance for animation
        total_distance = len(self.active_images) * canvas_width

        # Set the desired duration (in milliseconds)
        desired_duration = 7600  # 8 seconds for animation
        self.frame_delay = 16  # Default frame delay in ms (60 FPS)
        frames = desired_duration // self.frame_delay  # Total number of frames
        self.animation_speed = max(20, total_distance // frames)  # Pixels per frame

        def slide():
            # Move all images to the left
            for image_item, img_tk in self.active_images:
                self.canvas.move(image_item, -self.animation_speed, 0)  # Move images to the left

            # Start slowing down earlier if uninstalled games are included
            slowdown_start_index = -3

            # Check if the current image is in the last 10 images (based on whether uninstalled games are included)
            for i, (image_item, img_tk) in enumerate(self.active_images[slowdown_start_index:]):  
                image_x = self.canvas.coords(image_item)[0]  # x-coordinate of the image
                img_width = self.canvas.bbox(image_item)[2] - self.canvas.bbox(image_item)[0]  # Image width
                image_left_x = image_x - img_width / 2  # Left edge of the image

                # If the image is near or at the left edge, start slowing down
                if image_left_x <= 0:  # If the image is near or at the left edge
                    self.animation_speed = max(5, self.animation_speed * 0.95)  # Gradually slow down the speed

            # Get the x-coordinate of the top-left corner of the last image
            last_image_x = self.canvas.coords(self.active_images[-1][0])[0]  # x-coordinate of the last image
            img_width = self.canvas.bbox(self.active_images[-1][0])[2] - self.canvas.bbox(self.active_images[-1][0])[0]  # Image width
            last_image_left_x = last_image_x - img_width / 2  # Left edge of the last image

            # Stop the animation when the last image's left edge reaches the left edge of the canvas (x = 0)
            if last_image_left_x <= 0:  # Last image reaches the left side
                self.display_selected_game()  # Display selected game image
                print(f"Final spinning duration: {time.time() - self.start_time:.2f} seconds")
                return  # End the animation

            # Continue moving the images if they haven't reached the left edge
            self.animation_id = self.root.after(self.frame_delay, slide)

        self.start_time = time.time()  # Start the timer to calculate total spinning duration
        slide()

    def update_animation_preview(self, num_games_to_spin):
        """Update the animation preview with the selected number of games."""
        # Randomly select the number of games specified by the user
        selected_games = random.sample(self.installed_games, num_games_to_spin)
        
        # Display the selected games (can be adjusted to your animation logic)
        print(f"Selected games for preview: {', '.join([game['name'] for game in selected_games])}")

        # Set up the canvas with the selected games (you can update the visuals here)
        self.selected_games_preview = selected_games
        
        # Optionally, update the UI with a label displaying the number of games selected
        self.label_game_name.config(text=f"{len(selected_games)} Games Selected")
        
        # You could refresh your canvas or just display the images of the selected games
        self.display_selected_games_preview(selected_games)
        
    def display_selected_games_preview(self, selected_games):
        """Display a preview of the selected games on the canvas."""
        # Clear any previous preview images (if needed)
        self.canvas.delete("preview")  # Assuming you label preview images with 'preview'
        
        # Show the preview of the selected games on the canvas
        for index, game in enumerate(selected_games):
            img = self.preloaded_images.get(game["app_id"])
            img_tk = ImageTk.PhotoImage(img)
            x_position = 600 * (index + 1)  # Adjust based on how you want to space the images
            self.canvas.create_image(x_position, 150, image=img_tk, anchor=tk.CENTER, tags="preview")

        # Optionally, update the UI with a label displaying the number of games selected
        self.label_game_name.config(text=f"{len(selected_games)} Games Selected")

    def display_selected_game(self):
        """Display the selected game image after the spin."""
        if self.selected_game is not None:
            app_id = self.selected_game["app_id"]
            self.selected_game_image = self.load_image(app_id)
            self.label_welcome.config(text="Done!")
            self.label_game_name.config(text=f"{self.selected_game['name']}")
            self.label_welcome.config(text="Done!")
            
            # Resize the selected game image to match the canvas size
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            selected_image_resized = self.selected_game_image.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
            
            # Clear the canvas before displaying the selected game's image
            self.canvas.delete("all")
            
            # Display the selected game image
            img_tk = ImageTk.PhotoImage(selected_image_resized)
            self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=img_tk, anchor=tk.CENTER)
            self.active_images = [(img_tk, selected_image_resized)]  # Store for later reference
            print(f"Displaying selected game image: {self.selected_game['name']}")

        # Re-enable buttons
        self.button_spin.config(state=tk.NORMAL, text="Re-Roll")
        self.button_launch.config(state=tk.NORMAL)
        self.button_store.config(state=tk.NORMAL)

    def launch_game(self):
        """Launch the selected game using Steam."""
        webbrowser.open(f"steam://run/{self.selected_game['app_id']}")

    def open_store(self):
        """Open the Steam store page for the selected game."""
        webbrowser.open(f"https://store.steampowered.com/app/{self.selected_game['app_id']}")

# Main Function
def main():
    steam_path = STEAM_PATH if os.path.exists(STEAM_PATH) else None
    if not steam_path:
        print("Steam installation not found.")
        return

    # Ensure the cache directory exists
    cache_dir = create_cache_directory()

    games = get_installed_games(steam_path)
    drives = get_drives()
    if not games:
        print("No games found.")
        return

    root = tk.Tk()
    app = SteamRouletteGUI(root, games, drives)
    app.cache_dir = cache_dir  # Pass the cache directory to the GUI class
    root.mainloop()

if __name__ == "__main__":
    main()
