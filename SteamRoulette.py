import os
import sys;
import random
import time
import shutil
import string
import unicodedata
import platform
import webbrowser
import subprocess
import vdf
import re
import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk
import requests
from io import BytesIO
from steam.client import SteamClient

# Steam API and user information
STEAM_PATH = os.path.expanduser(r"C:\Program Files (x86)\Steam")
LIBRARY_FOLDERS_FILE = os.path.join(STEAM_PATH, "steamapps", "libraryfolders.vdf")
client = SteamClient()
EXCLUDED_APP_IDS = {228980, 250820, 365670}
EXCLUDED_KEYWORDS = ["redistributable", "steamvr", "blender", "tool", "wallpaper engine", "3dmark"]

# Function Definitions (Ensure these are defined above usage in your code)

# Function to get all drives (works for Windows, Linux, macOS)
def get_drives():
    system = platform.system()
    drives = []

    if system == "Windows":
        # Windows - use 'wmic' to get drives
        for drive in subprocess.check_output("wmic logicaldisk get name", shell=True).splitlines()[1:]:
            drive = drive.strip().decode()
            if drive:  # Ensure it's a valid drive
                drives.append(drive)

    elif system == "Linux":
        # Linux - look at mounted filesystems
        with os.popen("df -h --output=source") as f:
            for line in f.readlines()[1:]:
                drive = line.split()[0]
                if os.path.isdir(drive):  # Ensure it's a valid mount point
                    drives.append(drive)

    elif system == "Darwin":  # macOS
        # macOS - look at mounted volumes
        for drive in subprocess.check_output("mount").splitlines():
            drive = drive.split()[2]
            if os.path.isdir(drive):  # Ensure it's a valid directory
                drives.append(drive)

    return drives

# Function to parse libraryfolders.vdf and find all Steam library paths
def parse_vdf(file_path):
    """Parse VDF content and extract library paths."""
    libraries = {}
    try:
        # Parse the file by passing the file path directly
        with open(file_path, 'r', encoding='utf-8') as file:
            data = vdf.parse(file)
            for index, library in data.get("libraryfolders", {}).items():
                library_path = library.get("path")
                if library_path:
                    libraries[index] = library_path
    except Exception as e:
        print(f"Error parsing libraryfolders.vdf: {e}")
    return libraries

# Function to parse ACF file and extract game data
def parse_acf(acf_file_path):
    """Parse an ACF file and extract game data."""
    game_data = {}
    try:
        # Check if ACF file exists
        if not os.path.exists(acf_file_path):
            print(f"ACF file not found: {acf_file_path}")
            return None

        # Open the ACF file as a file object
        with open(acf_file_path, "r", encoding="utf-8") as file:
            # Use VDF parser to parse the file object, not the raw content
            parsed_content = vdf.parse(file)
            # Extract the app ID and game name from the parsed content
            app_id = parsed_content.get("AppState", {}).get("appid")
            name = parsed_content.get("AppState", {}).get("name")

            if app_id and name:
                print(f"Extracted Game: {name} (App ID: {app_id})")  # Debug: print game info
                game_data['app_id'] = app_id
                game_data['name'] = name
            else:
                print(f"Failed to extract valid data from {acf_file_path}")  # Debug: Print error if data is missing

    except Exception as e:
        print(f"Error parsing ACF file {acf_file_path}: {e}")
        return None

    return game_data

# Function to check if the game should be excluded
def is_excluded(game_data):
    """Check if a game should be excluded based on app id or keywords."""
    app_id = game_data.get("app_id", None)
    print(f"Checking exclusion for game {game_data.get('name', 'Unknown')} (App ID: {app_id})")
    
    if app_id is None:
        print(f"Game data is missing app_id: {game_data}")
        return True  # Exclude if no app_id

    if app_id and app_id in EXCLUDED_APP_IDS:
        print(f"Excluding game {game_data.get('name', 'Unknown')} due to App ID exclusion.")
        return True
    name = game_data.get("name", "").lower()
    for keyword in EXCLUDED_KEYWORDS:
        if keyword in name:
            print(f"Excluding game {game_data.get('name', 'Unknown')} due to keyword '{keyword}' in name.")
            return True
    return False

# Function to detect Steam library locations and installed games
def detect_steam_path():
    """Detect Steam installation path and library folders."""
    system = platform.system()
    default_paths = []

    if system == "Windows":
        default_paths = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Steam"),
            os.path.expandvars(r"%ProgramFiles%\Steam"),
            os.path.expandvars(r"%LocalAppData%\Steam"),
            os.path.expandvars(r"%steamapps%"),
        ]
    elif system == "Darwin":  # macOS
        default_paths = [
            os.path.expanduser("~/Library/Application Support/Steam"),
        ]
    elif system == "Linux":
        default_paths = [
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.local/share/Steam"),
        ]
    else:
        raise OSError("Unsupported operating system.")

    # Check default paths first
    for path in default_paths:
        if os.path.exists(path):
            return path

    # If not found, check the steamapps libraryfolders.vdf for custom installations
    if os.path.exists(LIBRARY_FOLDERS_FILE):
        with open(LIBRARY_FOLDERS_FILE, "r") as file:
            content = file.read()

        libraries = parse_vdf(content)
        for library in libraries.values():
            if os.path.exists(library):
                return library

    raise FileNotFoundError("Steam installation or library not found.")

# Get list of drives (Windows, Linux, macOS)
drives = get_drives()
print(f"Detected drives: {drives}")

def scan_steam_libraries(steamapps_path):
    """Scan a Steam library folder for installed games."""
    installed_games = []
    try:
        acf_files = [f for f in os.listdir(steamapps_path) if f.endswith(".acf")]
        for acf in acf_files:
            acf_path = os.path.join(steamapps_path, acf)
            game_data = parse_acf(acf_path)

            # Check if the game is valid and not excluded
            if game_data and not is_excluded(game_data):
                game_data["path"] = steamapps_path  # Include the path for drive grouping
                installed_games.append(game_data)

    except Exception as e:
        print(f"Error while scanning {steamapps_path}: {e}")
    
    return installed_games

def get_steam_user_id(steam_path):
    """Extract the Steam User ID from loginusers.vdf."""
    # Correct path construction
    loginusers_file = os.path.join(steam_path, "config", "loginusers.vdf")
    
    # Debug: Print the file path to ensure it's correct
    print(f"Looking for loginusers.vdf at: {loginusers_file}")

    # Check if the file exists
    if not os.path.exists(loginusers_file):
        print(f"Error: {loginusers_file} not found.")
        return None

    try:
        # Open and parse the file
        with open(loginusers_file, 'r', encoding='utf-8') as file:
            data = vdf.parse(file)
        
        print(f"Parsed loginusers.vdf data: {data}")  # Debug: Print parsed data

        # Ensure 'users' key exists and is structured as expected
        users = data.get('users', {})
        if not users:
            print("No users found in loginusers.vdf.")
            return None

        # Look for the active user (usually the last user in the list or the one with 'MostRecent' flag)
        for user_id, user_info in users.items():
            if user_info.get("MostRecent", False):  # Check for the most recent user
                print(f"Active user found: User ID {user_id}")
                return user_id  # Return the user ID of the most recent user

        print("No active user found in loginusers.vdf.")
        return None

    except Exception as e:
        print(f"Error parsing loginusers.vdf: {e}")
        return None

# Specify your Steam installation path explicitly
steam_path = r"C:\Program Files (x86)\Steam"  # Modify if your Steam installation is elsewhere
get_steam_user_id(steam_path)


# Function to get installed games from a specific Steam library path
def get_installed_games(steam_path):
    """Scan the Steam installation path for installed games."""
    library_folders_file = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(library_folders_file):
        print(f"Library folders file not found at {steam_path}.")
        return []

    installed_games = []
    try:
        libraries = parse_vdf(library_folders_file)
        print(f"Libraries parsed: {libraries}")  # Debug: Print parsed library paths

        # Scan each Steam library folder
        for library_index, library_path in libraries.items():
            if isinstance(library_path, str):  # Ensure it's a valid string path
                steamapps_path = os.path.join(library_path, "steamapps")
                if os.path.exists(steamapps_path):
                    print(f"Scanning Steamapps folder: {steamapps_path}")
                    installed_games.extend(scan_steam_libraries(steamapps_path))
                else:
                    print(f"Steamapps folder not found: {steamapps_path}")
            else:
                print(f"Invalid library path detected: {library_path}")

    except Exception as e:
        print(f"Error while processing Steam libraries at {steam_path}: {e}")
        return []

    print(f"Installed games found in {steam_path}: {len(installed_games)}")
    return installed_games

# Example Usage
steam_path = STEAM_PATH  # Adjust for your Steam installation path
user_id = get_steam_user_id(steam_path)
if user_id:
    print(f"Steam User ID: {user_id}")
else:
    print("Could not retrieve Steam User ID.")

installed_games = get_installed_games(steam_path)
print(f"Installed games found: {len(installed_games)}")

# Example Usage
steam_path = STEAM_PATH  # Adjust for your Steam installation path
user_id = get_steam_user_id(steam_path)
if user_id:
    print(f"Steam User ID: {user_id}")
else:
    print("Could not retrieve Steam User ID.")

installed_games = get_installed_games(steam_path)
print(f"Installed games found: {len(installed_games)}")

# Main flow
all_installed_games = []
installed_games = get_installed_games(steam_path)
print(f"Installed games after gathering: {installed_games}")  # Check final list here
if installed_games:
    all_installed_games.extend(installed_games)
else:
    print("No games found in installed directories.")

# Example usage
steam_path = STEAM_PATH  # Adjust based on your Steam installation path
installed_games = get_installed_games(steam_path)
print(f"Installed games: {installed_games}")

def extract_app_id_from_manifest(manifest_path):
    """Extract the app_id from the appmanifest file."""
    app_id = None
    try:
        with open(manifest_path, 'r', encoding='utf-8') as file:
            content = file.read()
            print(f"Manifest content for {manifest_path}: {content[:200]}")  # Debug: print first 200 characters
            match = re.search(r'"appid"\s*"\d+"', content)
            if match:
                app_id = match.group(0).split('"')[1]  # app_id will be at index 1
    except Exception as e:
        print(f"Error reading manifest {manifest_path}: {e}")
    return app_id

def process_game(game):
    app_id = game.get('app_id')
    if app_id is None:
        print(f"Excluding game {game['name']} because it has no app_id.")
        return  # Exclude the game

    # Continue with processing the game...
    print(f"Processing game {game['name']} with App ID: {app_id}")

# Example: Get installed games

installed_games = get_installed_games(steam_path)

if installed_games:
    for game in installed_games:
        print(f"Installed game: {game['name']} (App ID: {game['app_id']})")
else:
    print("No games found.")

def is_game(app_id):
    """Check if a given app_id corresponds to a game using the Steam API."""
    try:
        steam_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
        response = requests.get(steam_url)
        data = response.json()

        # Check if the app is a game
        if response.status_code == 200 and data.get(str(app_id), {}).get("success"):
            app_data = data[str(app_id)]["data"]
            return app_data.get("type") == "game"

    except Exception as e:
        print(f"Error checking if app_id {app_id} is a game: {e}")

    return False

def fetch_game_info_from_api(app_id):
    """Use the Steam API to check if the app is a game."""
    try:
        steam_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
        response = requests.get(steam_url)
        data = response.json()

        if response.status_code == 200 and data.get(str(app_id), {}).get("success"):
            app_data = data[str(app_id)]["data"]
            return app_data.get("type") == "game"

    except Exception as e:
        print(f"Error checking app ID {app_id} on Steam API: {e}")
    return False

def get_steam_user_id(steam_path):
    """Retrieve the most recent Steam User ID from loginusers.vdf."""
    try:
        config_path = os.path.join(steam_path, "config", "loginusers.vdf")
        if not os.path.exists(config_path):
            raise FileNotFoundError("loginusers.vdf not found. Please ensure Steam is installed correctly.")

        with open(config_path, "r") as file:
            content = file.read()

        # Parse the VDF structure
        users = parse_vdf(content).get("users", {})
        for user_id, user_data in users.items():
            if user_data.get("MostRecent") == "1":
                print(f"Most recent Steam User ID: {user_id}")
                return user_id

    except Exception as e:
        print(f"Error retrieving Steam User ID: {e}")

    return None

# Example: Get installed games
installed_games = get_installed_games(steam_path)

if installed_games:
    for game in installed_games:
        print(f"Installed game: {game['name']} (App ID: {game['app_id']})")
else:
    print("No games found.")


def get_steam_header_image(app_id):
    """Fetch the Steam header or background image for a game using its app_id."""
    header_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
    background_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/page_bg.jpg"

    try:
        # Try fetching the header image
        response = requests.get(header_url)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            print(f"Fetched header image for app_id {app_id}.")
            return img

        # If header image is not found, attempt fetching the background image
        response = requests.get(background_url)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            print(f"Fetched background image for app_id {app_id}.")
            return img

    except Exception as e:
        print(f"Error fetching images for app_id {app_id}: {e}")
    
    return None  # Return None if neither image is found


def get_local_header_image(app_id, game_name, steam_path):
    """Fetch the local header image from the game's installation folder."""
    try:
        # Check in the default folder where the game's images might be stored
        game_path = os.path.join(steam_path, "steamapps", "common", game_name)
        
        # Try to find common image files that may be used by Steam
        possible_image_files = [
            os.path.join(game_path, "header.jpg"),
            os.path.join(game_path, "banner.jpg"),
            os.path.join(game_path, "artwork.jpg")
        ]
        
        # Check if any of these files exist
        for image_file in possible_image_files:
            if os.path.exists(image_file):
                print(f"Found local image for {game_name}: {image_file}")
                return Image.open(image_file)  # Open and return the image

    except Exception as e:
        print(f"Error loading local image for {game_name}: {e}")
    
    return None  # Return None if no local image is found

def create_placeholder_image(game_title):
    """Create a simple placeholder image with the game title."""
    img = Image.new('RGB', (200, 300), color=(255, 255, 255))  # White background
    draw = ImageDraw.Draw(img)

    # Draw the game title in the center
    text = "Image\nUnavailable"
    font = ImageFont.load_default()

    # Calculate text size using textbbox (bounding box)
    bbox = draw.textbbox((0, 0), text, font=font)
    textwidth = bbox[2] - bbox[0]
    textheight = bbox[3] - bbox[1]

    draw.text(((200 - textwidth) / 2, (300 - textheight) / 2), text, font=font, fill="black")

    return img

def get_fallback_image(game_title, app_id, steam_path):
    """Fetch the Steam header image or display a fallback text if needed."""
    try:
        # First, check the Steam API for the header image
        steam_image = get_steam_header_image(app_id)
        if steam_image:
            print(f"Using Steam header image for {game_title}.")
            return steam_image  # Return the Image object from Steam API

        # If no header image is found via the Steam API, check for local images
        local_image = get_local_header_image(app_id, game_title, steam_path)
        if local_image:
            print(f"Using local image for {game_title}.")
            return local_image  # Return the local image if found

        # If no image is found, return None and show text fallback
        print(f"Using fallback for {game_title}.")
        return None  # Return None if no image is found

    except Exception as e:
        print(f"Error fetching fallback image: {e}")
        return None  # Return None if error occurs
    
def resource_path(relative_path):
    """ Get the absolute path to the resource, works for both development and PyInstaller. """
    try:
        # PyInstaller creates a temp folder and stores the path to the bundled app
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")  # Use the current directory in development
    
    return os.path.join(base_path, relative_path)

class SteamRouletteGUI:
    def __init__(self, root, installed_games, steam_path, icon_path):
        self.root = root
        self.installed_games = installed_games
        self.steam_path = steam_path
        self.api_key = self.load_api_key()  # Load the API key if available
        self.selected_game = None
        self.game_size = 0

        # Use resource_path for bundled paths
        if hasattr(sys, '_MEIPASS'):  # PyInstaller temp folder
            icon_path = os.path.join(sys._MEIPASS, 'SteamRouletteIcon.ico')

        print(f"Using icon at: {icon_path}")  # Debug print

        try:
            # Set the window and taskbar icon
            self.root.iconbitmap(icon_path)  # Set .ico for the window
            self.root.iconphoto(True, tk.PhotoImage(file=icon_path))  # Set taskbar icon
        except Exception as e:
            print(f"Error setting window icon: {e}")

        # Use resource_path to get the correct image path
        logo_path = resource_path("SteamRouletteLogo.png")
        try:
            logo_image = Image.open(logo_path)
            logo_image = ImageTk.PhotoImage(logo_image)

            self.label_logoimage = tk.Label(root, image=logo_image)
            self.label_logoimage.image = logo_image  # Keep a reference to the image
            self.label_logoimage.pack(pady=10)

            # Remove text from label_game_name after logo is displayed
            self.label_game_name = tk.Label(root, text="", font=("Arial", 16))
            self.label_game_name.pack(pady=10)

            # Ensure the window updates after packing elements
            self.root.update_idletasks()

        except Exception as e:
            print(f"Error loading logo image: {e}")

        # Create the mapping of drives to game counts
        self.games_per_drive = self.group_games_by_drive(installed_games)

        self.label_game_name = tk.Label(root, text="Welcome to Steam Roulette!\n Click the button below to start spinning!", font=("Arial", 16))
        self.label_game_name.pack(pady=0)

        # Add a label for displaying the game size
        self.label_game_size = tk.Label(root, text="", font=("Arial", 10))
        self.label_game_size.pack(pady=5)

        self.label_image = tk.Label(root)
        self.label_image.pack(pady=10)

        self.button_spin = tk.Button(root, text="Spin the Wheel", command=self.spin_wheel, font=("Arial", 14))
        self.button_spin.pack(pady=10)

        self.button_launch = tk.Button(root, text="Launch Game", command=self.launch_game, state=tk.DISABLED, font=("Arial", 12))
        self.button_launch.pack(pady=5)

        self.button_store = tk.Button(root, text="Go to Steam Store", command=self.go_to_store, state=tk.DISABLED, font=("Arial", 12))
        self.button_store.pack(pady=5)

        # Bottom frame for alignment
        frame_bottom = tk.Frame(root)
        frame_bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # Update the "Games Found" label
        games_found_text = self.generate_games_found_text()
        self.label_game_count = tk.Label(frame_bottom, text=games_found_text, font=("Arial", 10))
        self.label_game_count.pack(side=tk.RIGHT, padx=10)

        # Add "Set API Key" button to bottom left
        self.button_set_api_key = tk.Button(frame_bottom, text="Set API Key", command=self.set_api_key, font=("Arial", 12))
        self.button_set_api_key.pack(side=tk.LEFT, padx=10)

        # Control flags
        self.spin_effect_active = False
        self.final_game_name = None
        self.final_app_id = None

    def get_drives(self):
        """Return a list of available drives."""
        drives = []
        for drive in string.ascii_uppercase:
            drive_path = f"{drive}:\\"
            if os.path.exists(drive_path):
                drives.append(drive_path)
        return drives

    def group_games_by_drive(self, games):
        """Group installed games by their drive."""
        games_per_drive = {}
        for game in games:
            game_path = game.get("path", "")
            print(f"Processing game path: {game_path}")  # Debugging line
            drive = os.path.splitdrive(game_path)[0]  # Extract the drive letter
            if drive:
                if drive not in games_per_drive:
                    games_per_drive[drive] = 0
                games_per_drive[drive] += 1
        return games_per_drive

    def generate_games_found_text(self):
        """Generate a summary of games found on each drive."""
        if not self.games_per_drive:
            return "Games Found:\nNo games detected."
        lines = ["Games Found:"]
        for drive, count in self.games_per_drive.items():
            lines.append(f"{drive} {count} games")
        return "\n".join(lines)

    def load_logo_image(self, image_path):
        """Load the logo image without resizing."""
        try:
            # Load the image using PIL
            img = Image.open(image_path)

            # Convert the image to a format compatible with Tkinter
            return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Error loading logo image from {image_path}: {e}")
            return None

    def load_api_key(self):
        """Load API key from the file in the same directory as the .exe."""
        # Get the path of the current working directory (where the .exe is located)
        current_directory = os.path.dirname(os.path.abspath(__file__))
        api_key_file_path = os.path.join(current_directory, 'apikey.txt')

        api_key_path = "apikey.txt"
        if os.path.exists(api_key_path):
            with open(api_key_path, "r") as file:
                return file.read().strip()
        return ""

    def set_api_key(self):
        """Prompt user for an API key and save it to a file in the current directory."""
        def save_api_key(api_key):
            try:
                # Get the current working directory
                current_directory = os.path.dirname(os.path.abspath(__file__))
                api_key_file_path = os.path.join(current_directory, 'apikey.txt')

                with open(api_key_file_path, 'w') as file:
                    file.write(api_key)
                    print(f"API Key saved to {api_key_file_path}")  # Debug: print save location
                self.api_key = api_key  # Store the API key in the object
                messagebox.showinfo("API Key", "API Key saved successfully.")
            except Exception as e:
                print(f"Error saving API key: {e}")

        # Show dialog box to get API key from the user
        api_key = simpledialog.askstring("Enter API Key", "Please enter your Steam API Key:")
        if api_key:
            save_api_key(api_key)  # Save the API key if provided

    def get_steam_library_paths(self, steam_config_path="C:\\Program Files (x86)\\Steam\\config\\libraryfolders.vdf"):
        """Get all the Steam library paths from the libraryfolders.vdf file."""
        library_paths = []
        
        if os.path.exists(steam_config_path):
            try:
                with open(steam_config_path, "rb") as f:
                    vdf_data = f.read()
                
                # Attempt to decode the file with UTF-8, if it fails, try ISO-8859-1
                try:
                    vdf_data = vdf_data.decode("utf-8")
                except UnicodeDecodeError:
                    vdf_data = vdf_data.decode("ISO-8859-1")
                
                lines = vdf_data.splitlines()
                for line in lines:
                    if '"path"' in line:
                        path = line.split('"')[3]
                        if os.path.exists(path):
                            library_paths.append(path)
            except Exception as e:
                print(f"Error reading libraryfolders.vdf: {e}")
        
        return library_paths

    def find_game_folder_using_app_id(self, app_id, steam_path="C:\\Program Files (x86)\\Steam"):
        """Automatically find the game folder using app_id and Steam's library structure."""
        library_paths = self.get_steam_library_paths(os.path.join(steam_path, "config", "libraryfolders.vdf"))
        
        for library in library_paths:
            game_folder = os.path.join(library, "steamapps", "common", str(app_id))
            if os.path.exists(game_folder):
                print(f"Game folder for app_id {app_id} found at: {game_folder}")
                return game_folder
        
        print(f"Game folder for app_id {app_id} not found.")
        return None

    def normalize_name(self, name, keep_apostrophes=False):
        """
        Normalize a game name by handling spaces, hyphens, colons, special characters, and accented characters.
        
        Parameters:
        - name (str): The game name to normalize.
        - keep_apostrophes (bool): Whether to retain apostrophes in the normalized name.
        """
        # Normalize Unicode characters and convert to ASCII
        normalized_name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
        
        # Make everything lowercase
        normalized_name = normalized_name.lower()
        
        # Remove common redundant words often appended to game titles
        redundant_words = ["ultimate", "edition", "definitive", "remastered", "deluxe", "sith"]
        for word in redundant_words:
            normalized_name = normalized_name.replace(word, "")

        # Replace spaces, hyphens, and other common special characters
        normalized_name = normalized_name.replace(" ", "_") \
            .replace("-", "_") \
            .replace(":", "") \
            .replace("™", "") \
            .replace("®", "") \
            .replace(",", "_") \
            .replace("(", "") \
            .replace(")", "")

        # Handle apostrophes based on the `keep_apostrophes` parameter
        if not keep_apostrophes:
            normalized_name = normalized_name.replace("'", "")

        # Fix specific cases for common words
        normalized_name = normalized_name.replace("vs", "vs")
        normalized_name = normalized_name.replace("_the_", "_")  # Collapse "the"
        normalized_name = normalized_name.replace("_of_", "_")  # Collapse "of"
        
        return normalized_name


    def generate_acronym(self, game_title):
        """
        Generate possible acronyms from the game title.
        """
        words = game_title.split()
        acronym_variants = []

        # Acronym based on the first letter of each significant word
        acronym_variants.append("".join([word[0].upper() for word in words if word.isalpha()]))

        # Include the first 3 letters of the first word + first letter of the second word
        if len(words) > 1:
            acronym_variants.append(words[0][:3].upper() + words[1][0].upper())  # Example: "Shin Megami" -> "ShiM"

        # Include numbers if present
        version_match = re.search(r"\bV\d*\b", game_title, re.IGNORECASE)  # Match versions like "V5" or "V"
        if version_match:
            version = version_match.group().upper()
            acronym_variants.append("".join([word[0].upper() for word in words[:3]]) + version)  # Example: "SMT5"

        # Special case: titles with "Vengeance" or similar keywords
        if "vengeance" in game_title.lower():
            acronym_variants.append("".join([word[0].upper() for word in words[:3]]) + "V")

        return acronym_variants

    def search_folder_by_title(self, game_title, base_path):
        """
        Search for folder names that match the significant parts of the game title or acronyms.
        """
        game_folders = os.listdir(os.path.join(base_path, "common"))
        matching_folders = []

        print(f"Searching for matching folders for '{game_title}'...")  # Debug log for folder matching

        # Normalize the game title
        normalized_title = self.normalize_name(game_title)

        # Extract primary keywords (e.g., "Shin", "Megami", "Tensei")
        primary_keywords = game_title.split(":")[0].strip().split()[:3]  # First 3 significant words

        # First, look for an exact match based on the normalized game title
        for folder in game_folders:
            if normalized_title == self.normalize_name(folder):
                matching_folders.append(folder)

        # If no exact match, try matching significant keywords
        if not matching_folders:
            for folder in game_folders:
                if all(keyword.lower() in folder.lower() for keyword in primary_keywords):
                    matching_folders.append(folder)

        # If still no matches, try acronym matches
        if not matching_folders:
            acronym_variants = self.generate_acronym(game_title)
            print(f"Trying acronyms for matching folder...")
            for folder in game_folders:
                for acronym in acronym_variants:
                    if acronym.lower() in folder.lower():
                        matching_folders.append(folder)

        print(f"Matching folders for '{game_title}': {matching_folders}")  # Debug log for folder matching
        return matching_folders

    def calculate_game_size(self, game_path):
        """Calculate the total size of all files in the game folder using disk usage."""
        if not os.path.exists(game_path):
            print(f"Game path does not exist: {game_path}")
            return 0  # Return 0 if the path is invalid

        # Option 1: Use shutil.disk_usage to get the folder size directly
        try:
            total_size = 0
            # Walk through the folder recursively and add the size of all files
            for dirpath, dirnames, filenames in os.walk(game_path):
                for filename in filenames:
                    total_size += os.path.getsize(os.path.join(dirpath, filename))
            
            total_size_gb = total_size / (1024 * 1024 * 1024)  # Convert bytes to GB
            print(f"Total size of '{game_path}': {total_size_gb:.2f} GB")
            return total_size_gb

        except Exception as e:
            print(f"Error calculating game size for {game_path}: {e}")
            return 0

    def spin_wheel(self):
        """Start the spinning animation and pick a random game."""
        if not self.installed_games:
            messagebox.showinfo("Error", "No games found.")
            return

        self.selected_game = random.choice(self.installed_games)
        game_title = self.selected_game["name"]
        app_id = self.selected_game["app_id"]
        game_path = os.path.join(self.selected_game["path"], "common", game_title)
        base_path = self.selected_game.get("path", steam_path)

        # Search for the folder that matches the game title
        matching_folders = self.search_folder_by_title(game_title, base_path)

        if not matching_folders:
            print(f"Unable to resolve game path for {game_title}")
            return

        # For simplicity, we take the first match
        game_path = os.path.join(base_path, "common", matching_folders[0])
        print(f"Found game folder: {game_path}")

        # Recalculate the total game size (including all files in subfolders)
        self.game_size = self.calculate_game_size(game_path)
        print(f"Total game size for '{game_title}': {self.game_size:.2f} GB")

        # Disable buttons during the spin
        self.button_spin.config(state=tk.DISABLED)
        self.button_launch.config(state=tk.DISABLED)
        self.button_store.config(state=tk.DISABLED)

        # Initialize spinning
        self.final_game_name = game_title
        self.final_app_id = app_id
        self.spin_effect_active = True

        # Start animation
        self.cycle_game_names_and_images(speed=50)

        # Stop spinning after 2 seconds and show the result
        self.root.after(2000, self.show_selected_game)

        # Start animation
        self.cycle_game_names_and_images(speed=50)

        # Stop spinning after 2 seconds and show the result
        self.root.after(2000, self.show_selected_game)

    def spin_game_names_and_images(self, final_game_name, final_app_id):
        """Cycle through random game names and images to simulate spinning."""
        # Run a random cycling effect for 2 seconds
        self.cycle_game_names_and_images()

        # Update the label every 100 milliseconds
        self.spin_effect_active = True
        self.cycle_game_names_and_images()
        
    def cycle_game_names_and_images(self, speed):
        """Cycle through game names and images rapidly."""
        if not self.spin_effect_active:
            return

        random_game = random.choice(self.installed_games)
        random_game_name = random_game["name"]
        random_app_id = random_game["app_id"]

        # Update displayed name and image
        self.label_game_name.config(text=random_game_name)
        game_image = get_fallback_image(random_game_name, random_app_id, self.steam_path)
        self.show_game_image(game_image)

        # Gradually slow down cycling
        if speed < 200:  # Increase delay incrementally
            self.root.after(speed, self.cycle_game_names_and_images, speed + 10)

    def show_selected_game(self):
        """Display the selected game and its size."""
        self.label_game_name.config(text=self.final_game_name)

        # Update the game size text dynamically
        if self.game_size is not None:
            self.label_game_size.config(text=f"Size: {self.game_size:.2f} GB")
        else:
            self.label_game_size.config(text="Size: Unavailable")

        # Display the game's image
        game_image = get_fallback_image(self.final_game_name, self.final_app_id, self.steam_path)
        self.show_game_image(game_image)

        # Enable action buttons
        self.button_launch.config(state=tk.NORMAL)
        self.button_store.config(state=tk.NORMAL)
        self.button_spin.config(state=tk.NORMAL, text="Re-Roll")

        # Stop the spinning effect
        self.spin_effect_active = False

    def show_game_image(self, image):
        """Display the game image or fallback text in the GUI."""
        # Clear the current image and text before displaying a new one
        self.label_image.config(image=None, text="")

        if isinstance(image, Image.Image):  # Check if it's a PIL Image object
            # Set a fixed width for the image (e.g., 600px)
            target_width = 600

            # Get the original width and height of the image
            original_width, original_height = image.size
            aspect_ratio = original_width / original_height

            # Calculate the new height to maintain the aspect ratio
            target_height = int(target_width / aspect_ratio)

            # Resize the image to the target width and calculated height
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

            # Convert the image to a Tkinter-compatible format
            img_tk = ImageTk.PhotoImage(image)

            # Set the image to the label and keep a reference
            self.label_image.config(image=img_tk, text="")  # Clear any previous text
            self.label_image.image = img_tk  # Keep a reference to avoid garbage collection
        else:
            # If no image is provided, show fallback text instead
            self.label_image.config(image=None, text="Image Unavailable")  # Show fallback text instead of an image)

    def launch_game(self):
        """Launch the selected game."""
        app_id = self.selected_game["app_id"]
        webbrowser.open(f"steam://run/{app_id}")

    def go_to_store(self):
        """Open the Steam store page for the selected game."""
        app_id = self.selected_game["app_id"]
        webbrowser.open(f"https://store.steampowered.com/app/{app_id}")

# Main function to scan for installed games across all drives
def main():
    """Main function to scan for installed games across all drives."""
    drives = get_drives()  # Get all available drives
    all_installed_games = []

    # Path to the icon (same path as your script or the packaged file)
    icon_path = r'SteamRouletteIcon.ico'  # Path to the .ico file

    # Check default Steam paths on each drive
    for drive in drives:
        possible_steam_paths = [
            os.path.join(drive, "Program Files (x86)", "Steam"),
            os.path.join(drive, "Steam"),
        ]

        for steam_path in possible_steam_paths:
            if os.path.exists(steam_path):
                print(f"Steam installation detected at: {steam_path}")
                installed_games = get_installed_games(steam_path)
                all_installed_games.extend(installed_games)

    # Include the global STEAM_PATH if not already scanned
    if os.path.exists(STEAM_PATH):
        print(f"Checking additional Steam path: {STEAM_PATH}")
        installed_games = get_installed_games(STEAM_PATH)
        all_installed_games.extend(installed_games)

    # Remove duplicates based on app_id
    unique_games = []
    seen_app_ids = set()
    for game in all_installed_games:
        app_id = game.get("app_id")
        if app_id and app_id not in seen_app_ids:
            unique_games.append(game)
            seen_app_ids.add(app_id)

    all_installed_games = unique_games

    print(f"Total installed games found: {len(all_installed_games)}")
    for game in all_installed_games:
        print(f"Game: {game.get('name')} (App ID: {game.get('app_id')})")

    if all_installed_games:
        # Initialize GUI with the list of installed games
        root = tk.Tk()
        app = SteamRouletteGUI(root, all_installed_games, STEAM_PATH, icon_path)
        root.title("Steam Roulette")
        root.geometry("600x800")
        root.resizable(False, False)
        root.mainloop()
    else:
        print("No installed games found.")

if __name__ == "__main__":
    main()
