import os
import io
import random
import platform
import webbrowser
import requests
import tkinter as tk
from tkinter import simpledialog, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk
from io import BytesIO
import vdf
import sys
import concurrent.futures
import threading
import time
import json

# Constants
STEAM_PATH = os.path.expanduser(r"C:\Program Files (x86)\Steam")
EXCLUDED_APP_IDS = {228980, 250820, 365670, 223850}
EXCLUDED_KEYWORDS = ["redistributable", "steamvr", "blender", "tool", "wallpaper engine", "3dmark"]
ICON_PATH = r"SteamRouletteIcon.ico"
PLACEHOLDER_IMAGE_DIMENSIONS = (200, 300)

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

def is_excluded(game):
    """Determine if a game should be excluded."""
    if not game or not game.get("app_id"):
        return True
    if game["app_id"] in EXCLUDED_APP_IDS or any(keyword in game["name"].lower() for keyword in EXCLUDED_KEYWORDS):
        return True
    return False

def fetch_header_image(app_id, timeout=10):
    """Fetch game header image from Steam or return a placeholder."""
    urls = [
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/page_bg.jpg",
    ]
    for url in urls:
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return Image.open(BytesIO(response.content))
        except Exception as e:
            print(f"Error fetching image for app_id {app_id}: {e}")
    return create_placeholder_image("Image Unavailable")

def create_placeholder_image(text):
    """Generate a placeholder image."""
    img = Image.new("RGB", PLACEHOLDER_IMAGE_DIMENSIONS, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    text_size = draw.textsize(text, font=font)
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
        if library_path and isinstance(library_path, str):  # Ensure valid paths
            steamapps_path = os.path.join(library_path, "steamapps")
            if os.path.exists(steamapps_path):
                for acf_file in filter(lambda f: f.endswith(".acf"), os.listdir(steamapps_path)):
                    game = fetch_game_data(os.path.join(steamapps_path, acf_file), library_path)
                    if game and not is_excluded(game):
                        installed_games.append(game)
    return installed_games

def get_drives():
    """Detect all available drives on the system."""
    if platform.system() == "Windows":
        return [f"{chr(i)}:\\" for i in range(65, 91) if os.path.exists(f"{chr(i)}:\\")]
    elif platform.system() == "Linux":
        return [line.split()[0] for line in os.popen("df -h --output=source").readlines()[1:]]
    elif platform.system() == "Darwin":  # macOS
        return [line.split()[2] for line in os.popen("mount").readlines()]
    return []

def resource_path(relative_path):
    """ Get the absolute path to the resource, works for both development and PyInstaller. """
    try:
        # PyInstaller creates a temp folder and stores the path to the bundled app
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")  # Use the current directory in development
    
    return os.path.join(base_path, relative_path)

# GUI Class
class SteamRouletteGUI:
    def __init__(self, root, installed_games, drives):
        self.root = root
        self.installed_games = installed_games
        self.selected_game = None
        self.drives = drives
        self.api_key = self.load_api_key()

        # Define color schemes
        self.light_mode_bg = "#ffffff"
        self.dark_mode_bg = "#2e2e2e"
        self.light_mode_fg = "#000000"
        self.dark_mode_fg = "#ffffff"

        # Initialize animation speed (starting value)
        self.initial_animation_speed = 50  # Adjust this as needed
        self.animation_speed = self.initial_animation_speed

        # Create a frame to contain the game name label and other elements
        frame = tk.Frame(self.root, bg=self.light_mode_bg)
        frame.pack(pady=5)

        # Apply light mode to the frame
        self.update_theme(frame, self.light_mode_bg, self.light_mode_fg)

        # Set initial animation speed
        self.animation_speed = 200  # Controls the distance moved per frame
        self.frame_delay = 16  # Controls the speed of the animation (time between frames)

        self.root.title("Steam Roulette")
        self.root.geometry("600x700")
        self.root.resizable(False, False)

        try:
            # Use resource_path for bundled paths
            if hasattr(sys, '_MEIPASS'):  # PyInstaller temp folder
                icon_path = os.path.join(sys._MEIPASS, 'SteamRouletteIcon.ico')
            else:
                # Fallback to the local path if not using PyInstaller
                icon_path = f"{ICON_PATH}"  # Update this path

            # Set the window and taskbar icon
            self.root.iconbitmap(ICON_PATH)  # Set .ico for the window
            self.root.iconphoto(True, tk.PhotoImage(file=ICON_PATH))  # Set taskbar icon

        except Exception as e:
            print(f"Error setting window icon: {e}")

        # Path to the folder containing the header images
        if getattr(sys, 'frozen', False):  # If running as an executable
            base_path = sys._MEIPASS
        else:  # If running as a script
            base_path = os.path.dirname(os.path.abspath(__file__))

        # Define the relative path to the 'header_images' folder
        self.header_images_folder = os.path.join(base_path, "image_cache")

        # Try to load images locally, if they don't exist, fallback to Steam API
        if os.path.exists(self.header_images_folder) and os.listdir(self.header_images_folder):
            self.header_images = self.load_header_images(self.header_images_folder)
        else:
            self.header_images = self.fetch_random_game_header_from_steam()

        # Label displaying "Games Found on Drives" (bottom right corner)
        self.label_game_count = tk.Label(root, text=self.generate_games_found_text(), font=("Arial", 10))
        self.label_game_count.place(relx=0.0, rely=0.0, anchor='nw', x=5, y=60)

        # Label displaying copyright notice in the top-left corner
        self.copyright_notice = tk.Label(root, text="© Streetbackguy 2024", font=("Arial", 8))
        self.copyright_notice.place(relx=0.0, rely=0.0, anchor='nw', x=5, y=5)

        # Initial theme mode (light mode by default)
        self.is_dark_mode = False

        # Create a frame for the lower-left corner buttons
        self.button_frame = tk.Frame(root, bg=self.light_mode_bg)  # Define button_frame here first
        self.button_frame.pack(pady=5)
        self.button_frame.place(relx=0.0, rely=1.0, anchor='sw', x=2, y=-2)  # Padding for the frame

        # Button to set the API Key
        self.button_set_api_key = tk.Button(self.button_frame, text="Set API Key", command=self.set_api_key, state=tk.NORMAL, font=("Arial", 12))
        self.button_set_api_key.grid(row=0, column=0, pady=2, padx=2)

        # Button to toggle dark mode
        self.button_toggle_theme = tk.Button(self.button_frame, text="Toggle Dark Mode", command=self.toggle_theme, font=("Arial", 12))
        self.button_toggle_theme.grid(row=0, column=1, pady=2, padx=2)

        # Canvas
        self.canvas = tk.Canvas(root, width=600, height=300, bg="black")
        self.canvas.pack(pady=1)

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
        self.button_launch = tk.Button(utility_frame, text="Launch Game", command=self.launch_game, state=tk.DISABLED, font=("Arial", 12))
        self.button_launch.grid(row=1, column=0, pady=5, padx=4)

        # Button to go to the Steam store for the selected game
        self.button_store = tk.Button(utility_frame, text="Steam Storepage", command=self.open_store, state=tk.DISABLED, font=("Arial", 12))
        self.button_store.grid(row=1, column=1, pady=5, padx=4)

        # Create a container frame to hold the button and label
        self.frame_controls = tk.Frame(self.root)
        self.frame_controls.place(relx=0.0, rely=0.85, anchor='w', x=4, y=24)

        # Add a button that triggers the popup to input the number of games
        self.button_set_number_of_games = tk.Button(self.frame_controls, text="Set Number of Games", command=self.set_number_of_games)
        self.button_set_number_of_games.grid(row=0, column=0, sticky='w')  # Positioned within the frame

        # Label to show the number of games selected (initially empty)
        self.label_number_of_games = tk.Label(self.frame_controls, text="Number of games:\nAll Games", font=("Arial", 8))
        self.label_number_of_games.grid(row=1, column=0, sticky='w', padx=18)

        # Create a frame to contain the game name label and other elements
        self.yes_no_frame = tk.Frame(self.root, bg=self.light_mode_bg)
        self.yes_no_frame.place(relx=1.0, rely=1.0, anchor='se', x=-2, y=-2)  # Padding for the frame

        # Label for Selecting whether to include uninstalled games or not
        self.label_number_of_games = tk.Label(self.yes_no_frame, text="Include Uninstalled Games?", font=("Arial", 8))
        self.label_number_of_games.grid(row=0, column=0, columnspan=2)

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

        # Preload the images
        self.preloaded_images = {}
        self.preload_images()
        # Display a random header image on startup
        self.display_random_header_image()

        # Use resource_path to get the correct logo path
        logo_path = resource_path("SteamRouletteLogo.png")
        try:
            logo_image = Image.open(logo_path)
            logo_image = ImageTk.PhotoImage(logo_image)

            self.label_logoimage = tk.Label(frame, image=logo_image, bg=self.light_mode_bg)
            self.label_logoimage.image = logo_image  # Keep a reference to the image
            self.label_logoimage.grid(row=0, pady=5)

            # Welcome label
            self.label_welcome = tk.Label(frame, text="Welcome to Steam Roulette!", font=("Arial", 16), bg=self.light_mode_bg)
            self.label_welcome.grid(row=1, pady=5)

            # Remove text from label_game_name after logo is displayed
            self.label_game_name = tk.Label(frame, text="", wraplength=600, font=("Arial", 20), bg=self.light_mode_bg)
            self.label_game_name.grid(row=2, pady=5)

            # Ensure the window updates after packing elements
            self.root.update_idletasks()

        except Exception as e:
            print(f"Error loading logo image: {e}")

        # Set initial theme (light mode)
        self.set_light_mode()
        # Display a random header image on startup
        self.display_random_header_image()

    def preload_images(self):
        """Preload images into memory for smoother animation with parallel processing."""
        
        def load_and_resize_image(game):
            """Helper function to fetch and resize an image."""
            img = fetch_header_image(game["app_id"])
            img = img.resize((600, 300), Image.Resampling.LANCZOS)  # Resize to canvas size
            self.preloaded_images[game["app_id"]] = img  # Store the PIL Image, not PhotoImage

        # Use ThreadPoolExecutor to preload images in parallel
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Submit image loading tasks in parallel for each game
            executor.map(load_and_resize_image, self.installed_games)

    def generate_games_found_text(self):
        """Generate a summary of games found on each drive."""
        drives_text = ["Games Found:"]
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
        api_key = simpledialog.askstring("Enter API Key", "Please enter your Steam API Key:")
        if api_key:
            with open("apikey.txt", "w") as file:
                file.write(api_key)
            self.api_key = api_key
            messagebox.showinfo("API Key", "API Key saved successfully.")

    def load_header_images(self, folder_path):
        """Load all image files from the specified folder."""
        image_files = []
        for filename in os.listdir(folder_path):
            # Check if the file is a valid image (add more file extensions if needed)
            if filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                image_files.append(os.path.join(folder_path, filename))
        return image_files

    def fetch_random_game_header_from_steam(self):
        """Fetch a random game's header image from the Steam API."""
        random_game_id = random.randint(1, 100000)  # Example: random game ID between 1 and 100000
        url = f"https://store.steampowered.com/api/appdetails?appids={random_game_id}"
        try:
            response = requests.get(url)
            data = response.json()

            if data.get(str(random_game_id)) and data[str(random_game_id)].get("data"):
                game_data = data[str(random_game_id)]["data"]
                if game_data.get("header_image"):
                    header_image_url = game_data["header_image"]
                    return [header_image_url]  # Return the header image URL as a list for consistency
                else:
                    print("No header image found for the game.")
            else:
                print("Failed to retrieve data for the game.")
        except Exception as e:
            print(f"Error fetching header from Steam API: {e}")
        return []
    
    def on_yes_click(self):
        print("Yes clicked")
        # Add your logic for when 'Yes' is clicked

    def on_no_click(self):
        print("No clicked")
        # Add your logic for when 'No' is clicked

    def display_random_header_image(self):
        """Display a random header image on the canvas."""
        if self.header_images:
            # Select a random image from the list of header images
            random_image_path = random.choice(self.header_images)

            # If the image is a URL (Steam API), download and display it
            if random_image_path.startswith("http"):  # Check if the path is a URL
                self.display_image_from_url(random_image_path)
            else:
                self.display_image_from_file(random_image_path)

    def display_image_from_file(self, image_path):
        """Display the image from a local file on the canvas."""
        try:
            img = Image.open(image_path)
            img_resized = img.resize((600, 300), Image.Resampling.LANCZOS)  # Resize image to fit the canvas
            img_tk = ImageTk.PhotoImage(img_resized)

            # Display the image on the canvas
            self.canvas.create_image(0, 0, anchor='nw', image=img_tk)

            # Keep a reference to the image to avoid garbage collection
            self.canvas.image = img_tk  # Keep a reference so the image stays in memory

        except Exception as e:
            print(f"Error loading image from file {image_path}: {e}")

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

    def set_number_of_games(self):
        """Popup window to ask user for how many games to spin between."""
        # Create a new Toplevel window for input
        self.popup = tk.Toplevel(self.root)
        self.popup.title("Select Number of Games")
        self.popup.geometry("300x150")

        # Label to guide the user
        label = tk.Label(self.popup, text="Enter number of games to spin:")
        label.pack(pady=10)

        # Entry widget to accept input
        self.num_games_entry = tk.Entry(self.popup)
        self.num_games_entry.pack(pady=5)

        # Submit button to get the value from the entry box
        submit_button = tk.Button(self.popup, text="Submit", command=self.submit_number_of_games)
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
            self.label_number_of_games.config(text=f"Number of games selected: {num_games_to_spin}")

            # Close the popup window after submitting
            self.popup.destroy()

            # Update the button text to "Spin Wheel" once the number is set
            self.button_spin.config(state=tk.NORMAL, text="Spin the Wheel")

        except ValueError as e:
            # If input is invalid, show an error message
            error_label = tk.Label(self.popup, text=f"Error: {e}", fg="red")
            error_label.pack()

    def spin_wheel(self):
        """Start the spinning animation based on the selected number of games."""
        if not self.selected_num_games:
            num_games_to_spin = len(self.installed_games)  # Spin all games by default
        else:
            num_games_to_spin = self.selected_num_games  # Spin selected number of games

        # Randomly select the number of games specified by the user
        selected_games = random.sample(self.installed_games, num_games_to_spin)
        
        # Display the selected games (can be adjusted to your animation logic)
        print(f"Spinning the following games: {', '.join([game['name'] for game in selected_games])}")

        # Reset the animation speed to the initial value for a fresh start
        self.animation_speed = self.initial_animation_speed

        # Disable the spin button while the animation is running
        self.button_spin.config(state=tk.DISABLED, text="Re-Roll")

        # Clear previous game name and other UI elements
        self.label_game_name.config(text="")
        self.label_welcome.config(text="")

        # If there was a previously displayed selected game image, remove it
        if hasattr(self, 'selected_game_item'):
            self.canvas.delete(self.selected_game_item)  # Remove the previous selected game image

        # Set the selected game to be randomly chosen
        self.selected_game = random.choice(selected_games)

        # Start the spinning effect with the selected games
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
        self.label_game_name.config(text=f"Selected Game: {self.selected_game['name']}")

        # Display the selected game image (it will be a new one)
        self.display_selected_game()

    def cycle_images(self, selected_games):
        """Cycle through the images as part of the spinning effect, adding the selected game's image at the end."""
        self.selected_game_image = self.preloaded_images.get(self.selected_game["app_id"])
        self.active_images = []
        images_to_display = self.installed_games
        self.label_welcome.config(text="Rolling...")

        # Shuffle the images_to_display list to show images in a random order each time
        random.shuffle(images_to_display)  # Shuffle the list of installed games

        # Create image items on the canvas
        x_position = 600  # Starting position off the right of the canvas
        for game in images_to_display:
            img = self.preloaded_images.get(game["app_id"])
            img_tk = ImageTk.PhotoImage(img)
            image_item = self.canvas.create_image(x_position, 150, image=img_tk, anchor=tk.CENTER)
            self.active_images.append((image_item, img_tk))  # Add both image and reference to active_images
            x_position += 600  # Fill the canvas width with no padding

        # Add the selected game's image at the end of the sequence
        selected_img = self.selected_game_image
        selected_img_tk = ImageTk.PhotoImage(selected_img)
        image_item = self.canvas.create_image(x_position, 150, image=selected_img_tk, anchor=tk.CENTER)
        self.active_images.append((image_item, selected_img_tk))  # Add selected game to the list

        self.animate_images()

    def animate_images(self):
        """Animate the images sliding across the canvas."""
        canvas_width = self.canvas.winfo_width()  # Get the width of the canvas

        # Calculate total distance for animation
        total_distance = len(self.active_images) * canvas_width

        # Set the desired duration (in milliseconds)
        desired_duration = 7600  # 7.6 seconds, with slowdown it's 8 seconds

        # Calculate the frame delay or speed dynamically
        self.frame_delay = 16  # Default frame delay in ms (60 FPS)
        frames = desired_duration // self.frame_delay  # Total number of frames
        self.animation_speed = max(1, total_distance // frames)  # Pixels per frame

        def slide():
            # Move all images to the left
            for image_item, img_tk in self.active_images:
                self.canvas.move(image_item, -self.animation_speed, 0)  # Move images to the left

            # Check if the current image is in the last 10 images
            for i, (image_item, img_tk) in enumerate(self.active_images[-5:]):  # Last 5 images
                image_x = self.canvas.coords(image_item)[0]  # x-coordinate of the image
                img_width = self.canvas.bbox(image_item)[2] - self.canvas.bbox(image_item)[0]  # Image width
                image_left_x = image_x - img_width / 2  # Left edge of the image

                # If the image is within the last 10 images, start slowing down
                if image_left_x <= 0:  # If the image is near or at the left edge
                    self.animation_speed = max(5, self.animation_speed * 0.98)  # Gradually slow down the speed

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

    # Dynamically adjust both speed and frame delay
    def setup_animation(self):
        canvas_width = self.canvas.winfo_width()
        total_distance = len(self.active_images) * canvas_width
        desired_duration = 8000  # 8 seconds in milliseconds

        # Adjust frame delay or animation speed dynamically
        self.frame_delay = max(1, 16)  # Default to 60 FPS if possible
        frames = desired_duration // self.frame_delay
        self.animation_speed = max(1, total_distance // frames)

    def display_selected_game(self):
        """Display the selected game image after the animation stops."""
        self.label_game_name.config(text=f"{self.selected_game['name']}")
        self.label_welcome.config(text="Done!")
        # Make sure the selected game image is resized and placed centered on the canvas
        img = self.selected_game_image.resize((600, 300), Image.Resampling.LANCZOS)
        img_tk = ImageTk.PhotoImage(img)
        self.selected_game_item = self.canvas.create_image(300, 150, image=img_tk, anchor=tk.CENTER)
        self.canvas.image = img_tk  # Keep reference to prevent garbage collection

        # Re-enable the buttons and re-enable the "Re-roll" button with correct text
        self.button_spin.config(state=tk.NORMAL, text="Re-Roll")
        self.button_launch.config(state=tk.NORMAL)
        self.button_store.config(state=tk.NORMAL)

    def launch_game(self):
        """Launch the selected game."""
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

    games = get_installed_games(steam_path)
    drives = get_drives()
    if not games:
        print("No games found.")
        return

    root = tk.Tk()
    app = SteamRouletteGUI(root, games, drives)
    root.mainloop()

if __name__ == "__main__":
    main()
