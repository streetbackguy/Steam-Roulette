import os
import sys;
import random
import shutil
import string
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
EXCLUDED_APP_IDS = {228980, 250820, 365670, 223850}
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

def calculate_folder_size(folder_path):
    """Calculate the total size of a folder and its subfolders."""
    try:
        total_size = shutil.disk_usage(folder_path).used  # Size in bytes
        return total_size / (1024 * 1024 * 1024)  # Convert bytes to GB
    except Exception as e:
        print(f"Error calculating folder size for {folder_path}: {e}")
        return None

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


def get_installed_games(steam_path):
    """Scan the Steam installation path for installed games and sizes."""
    library_folders_file = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(library_folders_file):
        print(f"Library folders file not found at {steam_path}.")
        return []

    installed_games = []
    try:
        libraries = parse_vdf(library_folders_file)
        print(f"Libraries parsed: {libraries}")

        # Scan each Steam library folder
        for library_path in libraries.values():
            steamapps_path = os.path.join(library_path, "steamapps")
            if os.path.exists(steamapps_path):
                acf_files = [f for f in os.listdir(steamapps_path) if f.endswith(".acf")]
                for acf_file in acf_files:
                    acf_path = os.path.join(steamapps_path, acf_file)
                    game_data = parse_acf(acf_path)

                    if game_data:
                        # Resolve the installation folder
                        game_folder = os.path.join(library_path, "steamapps", "common", game_data["name"])
                        game_data["path"] = game_folder
                        
                        # Calculate folder size if the folder exists
                        if os.path.exists(game_folder):
                            game_data["size"] = calculate_folder_size(game_folder)
                        else:
                            game_data["size"] = None

                        installed_games.append(game_data)

    except Exception as e:
        print(f"Error processing Steam libraries: {e}")
        return []

    return installed_games

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
        self.filtered_games = []

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

        self.canvas = tk.Canvas(root, width=600, height=280, bg="black")
        self.canvas.pack(pady=10)

        # Add an image item to the canvas (placeholder, updated dynamically)
        self.image_item = None
        self.active_images = []  # Stores tuples of (canvas_item, x_position)

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

        # Call this method once at the start to preload the images
        self.preload_images()

        # Initialize the class
        self.animation_id = None  # To store the scheduled animation ID

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

    def spin_wheel(self):
        """Start the spinning animation and pick a random game."""
        
        # Clear the label when the button is clicked
        self.label_game_name.config(text="")  # Set the label text to an empty string

        if not self.installed_games:
            messagebox.showinfo("Error", "No games found.")
            return

        # Randomly select the final game
        self.selected_game = random.choice(self.installed_games)
        self.final_game_name = self.selected_game["name"]
        self.final_app_id = self.selected_game["app_id"]

        # Disable buttons during the spin
        self.button_spin.config(state=tk.DISABLED)
        self.button_launch.config(state=tk.DISABLED)
        self.button_store.config(state=tk.DISABLED)

        # Start spinning animation
        self.spin_effect_active = True
        self.cycle_game_names_and_images(speed=50)  # Start cycling images

        # Stop spinning after the animation is done (example time 10 seconds)
        self.root.after(10000, self.show_selected_game)  # Adjust time as needed (e.g., 10 seconds)

    def slide_images(self, speed=10, slowdown_start_index=5):
        """Slide all active images across the canvas."""
        canvas_width = self.canvas.winfo_width()  # Get the actual canvas width
        images_to_remove = []

        # Track if the selected game image has reached the center
        selected_image_reached_center = False

        # Track if all images have moved off-screen
        non_selected_images_offscreen = True

        # Calculate the position of the selected game (center of canvas)
        selected_game_position = canvas_width // 2

        # Loop over each image in the active images list
        for index, (image_item, img_tk) in enumerate(self.active_images):  # Unpack active images
            app_id = img_tk  # Assuming `img_tk` contains the app_id (can change depending on your data structure)
            
            # Get the current position of the image
            coords = self.canvas.coords(image_item)

            # Calculate the distance of the current image from the selected game position
            distance_from_selected_game = abs(coords[0] - selected_game_position)

            # Slow down the animation only for images after the designated index
            if index >= slowdown_start_index:  # Start slowing down from this image onwards
                if distance_from_selected_game < 300:  # You can adjust the threshold for slowing down
                    # Gradually decrease the speed when closer to the selected game (but not below 0.5)
                    speed = max(0.5, speed * 0.98)  # Slowly reduce speed as the image gets closer

            # Move the image to the left (adjust by smaller increments, controlled by speed)
            self.canvas.move(image_item, -speed, 0)  # Move left by a smaller, more consistent speed

            # If the image is non-selected and still on screen, we need to continue sliding
            if coords[0] > -canvas_width:
                non_selected_images_offscreen = False

            # If the selected game image reaches the center, make it fully visible and stop the animation
            if not selected_image_reached_center and distance_from_selected_game <= 20 and image_item == self.all_images[-1]:
                selected_image_reached_center = True
                # Ensure the selected image is fully displayed in the center
                self.canvas.itemconfig(image_item, anchor=tk.CENTER)
                self.canvas.coords(image_item, selected_game_position, coords[1])  # Keep it centered

            # Remove images that move off the canvas
            if coords[0] < -canvas_width:  # Image is fully off-screen to the left
                images_to_remove.append((image_item, img_tk))

        # Remove out-of-view images
        for image_item, img_tk in images_to_remove:
            self.canvas.delete(image_item)
            self.active_images.remove((image_item, img_tk))

        # Continue sliding if the selected image hasn't reached the center yet
        if self.spin_effect_active and not non_selected_images_offscreen:
            # Continue sliding and update the canvas with the current speed
            self.animation_id = self.root.after(20, self.slide_images, speed)  # Schedule the next frame
        else:
            # Stop animation and show the selected game in the center
            self.show_selected_game()

    def stop_animation(self):
        """Stop the sliding animation."""
        self.spin_effect_active = False
        # Optionally, you can update the label or perform any other tasks when the animation stops
        print("Animation stopped - Selected game header reached the left side of the canvas.")


    def preload_images(self):
        """Preload all game header images into memory."""
        self.preloaded_images = {}
        
        # Load all images for the games
        for game in self.installed_games:
            random_game_name = game["name"]
            random_app_id = game["app_id"]

            # Get the game image (try local header image first, then fallback to Steam API)
            game_image = get_local_header_image(random_app_id, random_game_name, self.steam_path)
            if not game_image:
                game_image = get_steam_header_image(random_app_id)

            # Check if the image was loaded successfully
            if game_image:
                # Get the canvas width (this will be available after the canvas is initialized)
                canvas_width = 600  # Set a default width if canvas width is not yet available
                canvas_height = 280  # Set a default height if canvas height is not yet available

                # Calculate the aspect ratio and resize the image
                image_width = canvas_width  # Resize the image to fill the canvas width
                image_height = int(game_image.size[1] * (canvas_width / game_image.size[0]))  # Maintain aspect ratio
                
                if image_width > 0 and image_height > 0:
                    # Resize the image to fit the canvas width while maintaining aspect ratio
                    game_image = game_image.resize((image_width, image_height), Image.Resampling.LANCZOS)
                    
                    # Store the preloaded image in memory (as a PhotoImage object)
                    self.preloaded_images[random_app_id] = ImageTk.PhotoImage(game_image)
                else:
                    print(f"Invalid image dimensions for game {random_game_name} (ID: {random_app_id})")
            else:
                print(f"Failed to load image for game {random_game_name} (ID: {random_app_id})")
        
    def cycle_game_names_and_images(self, speed=10):
        """Cycle through multiple game headers by sliding them across the canvas."""
        if not self.spin_effect_active:
            return

        # Clear previous images
        for image_item, _ in self.active_images:
            self.canvas.delete(image_item)
        self.active_images.clear()

        # Filter out the excluded apps (by app_id and keywords)
        filtered_games = [
            game for game in self.installed_games
            if game["app_id"] not in EXCLUDED_APP_IDS and not any(keyword.lower() in game["name"].lower() for keyword in EXCLUDED_KEYWORDS)
        ]

        # Get a list of random games (excluding the selected one)
        random_games = [game for game in filtered_games if game["app_id"] != self.final_app_id]
        
        # Shuffle the random games to get a varied set of images each time
        random.shuffle(random_games)

        # Add non-selected images first and selected image last
        images = random_games + [self.selected_game]  # Automatically add all non-selected games and selected game at the end
        images.append(self.selected_game)  # Add the selected game image last

        # Start the X position off-screen to the right
        x_position = self.canvas.winfo_width()

        # List to track all images and their associated game names
        self.all_images = []
        self.game_names = []

        for game in images:
            random_game_name = game["name"]
            random_app_id = game["app_id"]

            # Use preloaded image from memory
            game_image = self.preloaded_images.get(random_app_id)

            if game_image:
                # Get the preloaded image from memory
                img_tk = game_image

                # Set initial X position (off-screen to the right)
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                image_width = canvas_width
                image_height = img_tk.height()

                image_y = canvas_height - image_height // 2  # Stick to bottom of the canvas
                image_item = self.canvas.create_image(x_position, image_y, image=img_tk, anchor=tk.CENTER)

                # Store reference and move the X position to the next image
                self.active_images.append((image_item, img_tk))  # Store both canvas item and image reference

                # Track all images and associated game names
                self.all_images.append(image_item)
                self.game_names.append(random_game_name)

                x_position += image_width  # Move the X position for the next image

        # Start sliding the images
        self.slide_images(speed)

    def show_selected_game(self):
        """Display the selected game when the sliding stops."""
        # Clear all images from the canvas
        for image_item, _ in self.active_images:
            self.canvas.delete(image_item)
        self.active_images.clear()

        # Update the game name and size labels
        self.label_game_name.config(text=self.final_game_name)

        # Update the game size text dynamically
        if self.game_size is not None:
            self.label_game_size.config(text=f"Size on disk: {self.game_size:.2f} GB")
        else:
            self.label_game_size.config(text="Size on disk: Unavailable")

        # Get the selected game's image
        game_image = get_local_header_image(self.final_app_id, self.final_game_name, self.steam_path)
        if not game_image:
            game_image = get_steam_header_image(self.final_app_id)

        if game_image:
            # Resize the image to fit the canvas width
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # Resize the image to fit the width of the canvas
            image_width = canvas_width  # Fill the whole canvas width
            image_height = int(game_image.size[1] * (canvas_width / game_image.size[0]))  # Maintain aspect ratio
            game_image = game_image.resize((image_width, image_height), Image.Resampling.LANCZOS)
            img_tk = ImageTk.PhotoImage(game_image)

            # Dynamically calculate canvas center
            image_x = canvas_width // 2  # Center horizontally
            image_y = canvas_height // 2  # Center vertically

            # Clear the canvas and display the image
            self.canvas.delete("all")  # Clear previous canvas content
            self.image_item = self.canvas.create_image(image_x, image_y, image=img_tk, anchor=tk.CENTER)
            self.canvas.image = img_tk  # Keep a reference

            # Re-enable buttons
            self.button_spin.config(state=tk.NORMAL, text="Re-Roll")
            self.button_launch.config(state=tk.NORMAL)
            self.button_store.config(state=tk.NORMAL)

    def show_game_image(self, image):
        """Display the game image or fallback text in the GUI."""
        # Clear the current image and text before displaying a new one
        self.label_image.config(image=None, text="")

        if isinstance(image, Image.Image):  # Check if it's a PIL Image object
            # Set a fixed width for the image (e.g., 600px)
            target_width = 600
            target_height = 280

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
