import os
import io
import random
import platform
import webbrowser
import requests
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from io import BytesIO
import json
import vdf
import sys
from concurrent.futures import ThreadPoolExecutor
import time
import winreg
import threading
from functools import lru_cache

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PLACEHOLDER_IMAGE_DIMENSIONS = (600, 300)
ANIMATION_DURATION_MS = 7600
FRAME_DELAY_MS = 16
SLOWDOWN_FACTOR = 0.95
MIN_SPEED = 5
PRELOAD_WORKERS = 10
IMAGE_CACHE_SUBDIR = "image_cache"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _exe_dir() -> str:
    """Directory that contains the running executable (or script in dev mode)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _data_path(filename: str) -> str:
    """Resolve a user-data file (api key, user id, exclusions) next to the exe."""
    return os.path.join(_exe_dir(), filename)


def resource_path(relative_path: str) -> str:
    """Resolve a bundled resource (icons, logos) – works in dev and PyInstaller."""
    try:
        base = sys._MEIPASS          # PyInstaller temp dir
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


# ---------------------------------------------------------------------------
# Steam installation discovery
# ---------------------------------------------------------------------------
def get_steam_install_path() -> str | None:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        return path
    except FileNotFoundError:
        return None


def find_steam_path_fallback() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        os.path.expanduser(r"~\AppData\Local\Steam"),
    ]
    for p in candidates:
        if os.path.exists(os.path.join(p, "steam.exe")):
            return p
    return None


STEAM_PATH = get_steam_install_path() or find_steam_path_fallback()
ICON_PATH = resource_path("SteamRouletteIcon.ico")


# ---------------------------------------------------------------------------
# Cache directory
# ---------------------------------------------------------------------------
def create_cache_directory() -> str:
    cache_dir = os.path.join(_exe_dir(), IMAGE_CACHE_SUBDIR)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


# ---------------------------------------------------------------------------
# VDF / ACF parsing
# ---------------------------------------------------------------------------
def parse_vdf(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            content = vdf.parse(fh)
        libraries = content.get("libraryfolders", {})
        return {
            key: value.get("path")
            for key, value in libraries.items()
            if isinstance(value, dict) and "path" in value
        }
    except Exception as e:
        print(f"Error parsing VDF file: {e}")
        return {}


@lru_cache(maxsize=None)
def fetch_game_data(acf_path: str, library_path: str) -> dict:
    try:
        with open(acf_path, "r", encoding="utf-8") as fh:
            content = vdf.parse(fh).get("AppState", {})
        return {
            "app_id": content.get("appid"),
            "name": content.get("name"),
            "path": library_path,
        }
    except Exception as e:
        print(f"Error reading ACF file {acf_path}: {e}")
        return {}


def get_installed_games(steam_path: str) -> list:
    library_folders = parse_vdf(os.path.join(steam_path, "steamapps", "libraryfolders.vdf"))
    installed_games = []
    for library_path in library_folders.values():
        if not (library_path and isinstance(library_path, str)):
            continue
        steamapps_path = os.path.join(library_path, "steamapps")
        if not os.path.exists(steamapps_path):
            continue
        for acf_file in filter(lambda f: f.endswith(".acf"), os.listdir(steamapps_path)):
            game = fetch_game_data(os.path.join(steamapps_path, acf_file), library_path)
            if game and game.get("app_id"):
                installed_games.append(game)
            else:
                print(f"Excluded invalid game entry: {game}")
    return installed_games


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
# Thread lock for preloaded_images dict mutations coming from background threads
_image_lock = threading.Lock()


def create_placeholder_image(text: str) -> Image.Image:
    img = Image.new("RGB", PLACEHOLDER_IMAGE_DIMENSIONS, color=(40, 40, 40))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((img.width - tw) / 2, (img.height - th) / 2),
        text, font=font, fill="white",
    )
    return img


def fetch_header_image(app_id: str, cache_dir: str, timeout: int = 10) -> Image.Image:
    """Fetch game header image from disk cache or Steam CDN."""
    cache_file = os.path.join(cache_dir, f"{app_id}.jpg")
    if os.path.exists(cache_file):
        try:
            return Image.open(cache_file)
        except Exception:
            pass  # corrupt cache file – re-fetch below

    urls = [
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/page_bg.jpg",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content))
                img.save(cache_file, "JPEG")
                return img
        except Exception as e:
            print(f"Error fetching image for app_id {app_id}: {e}")

    return create_placeholder_image("Image Unavailable")


# ---------------------------------------------------------------------------
# Steam Web API helpers
# ---------------------------------------------------------------------------
def get_all_games(api_key: str, steam_id: str) -> list:
    """Fetch all games owned by the user via the Steam API."""
    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        "key": api_key,
        "steamid": steam_id,
        "include_appinfo": True,
        "include_played_free_games": True,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "response" in data and "games" in data["response"]:
            games = data["response"]["games"]
            print(f"Fetched {len(games)} games from Steam API.")
            return games
        print("No games found in Steam API response.")
        return []
    except Exception as e:
        print(f"Error fetching games from Steam API: {e}")
        return []


def get_uninstalled_games_from_api(api_key: str, steam_id: str, installed_games: list) -> list:
    all_games = get_all_games(api_key, steam_id)
    if not all_games:
        return []
    installed_ids = {str(g["app_id"]) for g in installed_games}
    return [
        {"app_id": str(g["appid"]), "name": g["name"]}
        for g in all_games
        if str(g["appid"]) not in installed_ids
    ]


# ---------------------------------------------------------------------------
# Drive enumeration
# ---------------------------------------------------------------------------
def get_drives() -> list:
    if platform.system() == "Windows":
        return [f"{chr(i)}:\\" for i in range(65, 91) if os.path.exists(f"{chr(i)}:\\")]
    elif platform.system() == "Linux":
        import subprocess
        result = subprocess.run(["df", "-h", "--output=source"], capture_output=True, text=True)
        return result.stdout.splitlines()[1:]
    elif platform.system() == "Darwin":
        import subprocess
        result = subprocess.run(["mount"], capture_output=True, text=True)
        return [line.split()[2] for line in result.stdout.splitlines()]
    return []


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class SteamRouletteGUI:
    def __init__(self, root: tk.Tk, installed_games: list, drives: list):
        self.root = root
        self.installed_games = installed_games
        self.excluded_games: list = []
        self.uninstalled_games: list = []
        self.selected_game: dict | None = None
        self.drives = drives
        self.cache_dir = create_cache_directory()
        self.api_key: str = self._load_text_file("apikey.txt")
        self.is_dark_mode: bool = False
        self.selected_num_games: int | None = None
        self.is_images_preloaded: bool = False
        self.active_images: list = []
        self.selected_game_image: Image.Image | None = None
        self.selected_game_item = None
        self.animation_id = None
        self.preloaded_images: dict = {}

        # Color schemes
        self.light_mode_bg = "#ffffff"
        self.dark_mode_bg  = "#2e2e2e"
        self.light_mode_fg = "#000000"
        self.dark_mode_fg  = "#ffffff"

        # Animation state
        self.initial_animation_speed = 50
        self.animation_speed = 200
        self.frame_delay = FRAME_DELAY_MS

        self._build_ui()
        self.load_exclusions()
        # Pre-load installed-game images in the background; UI stays responsive
        threading.Thread(target=self._preload_installed_images, daemon=True).start()

    # ------------------------------------------------------------------
    # File I/O helpers
    # ------------------------------------------------------------------
    def _load_text_file(self, filename: str) -> str:
        path = _data_path(filename)
        if os.path.exists(path):
            with open(path, "r") as fh:
                return fh.read().strip()
        return ""

    def _save_text_file(self, filename: str, content: str) -> None:
        with open(_data_path(filename), "w") as fh:
            fh.write(content)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.root.title("Steam Roulette")
        width, height = 600, 750
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        self.root.geometry(f"{width}x{height}+{int(ws/2 - width/2)}+{int(hs/2 - height/2)}")
        self.root.resizable(False, False)

        # Window icon
        try:
            if os.path.exists(ICON_PATH):
                self.root.iconbitmap(ICON_PATH)
        except Exception as e:
            print(f"Error setting window icon: {e}")

        bg = self.light_mode_bg
        fg = self.light_mode_fg

        # ── Top info bar ─────────────────────────────────────────────
        self.copyright_notice = tk.Label(self.root, text="© Streetbackguy 2024",
                                         font=("Arial", 8), bg=bg, fg=fg)
        self.copyright_notice.place(relx=0.0, rely=0.0, anchor="nw", x=5, y=5)

        self.label_game_count = tk.Label(self.root, text=self._games_found_text(),
                                         font=("Arial", 10), bg=bg, fg=fg)
        self.root.update_idletasks()
        self.label_game_count.place(x=self.root.winfo_width() - 5, y=5, anchor="ne")

        # ── Top info bar ─────────────────────────────────────────────
        self.copyright_notice = tk.Label(
            self.root,
            text="© Streetbackguy 2024",
            font=("Arial", 8),
            bg=bg,
            fg=fg
        )

        self.copyright_notice.place(x=10, y=58)

        self.label_game_count = tk.Label(
            self.root,
            text=self._games_found_text(),
            font=("Arial", 10),
            bg=bg,
            fg=fg
        )

        self.root.update_idletasks()

        self.label_game_count.place(
            x=self.root.winfo_width() - 5,
            y=5,
            anchor="ne"
        )

        # ── Logo / title frame ───────────────────────────────────────
        top_frame = tk.Frame(self.root, bg=bg)

        # Push main content downward slightly
        top_frame.pack(side="top", pady=55)

        # Small logo positioned manually in top-left
        try:
            logo_path = resource_path("SteamRouletteLogo.png")

            if not os.path.exists(logo_path):
                raise FileNotFoundError(f"Logo not found: {logo_path}")

            logo_img = Image.open(logo_path)

            # Resize logo smaller
            logo_img = logo_img.resize((120, 50), Image.LANCZOS)

            logo_tk = ImageTk.PhotoImage(logo_img)

            self.label_logoimage = tk.Label(
                self.root,
                image=logo_tk,
                bg=bg
            )

            self.label_logoimage.image = logo_tk

        except Exception as e:
            print(e)

            self.label_logoimage = tk.Label(
                self.root,
                text="Steam Roulette",
                font=("Arial", 12),
                bg=bg,
                fg=fg
            )

        # Place logo in top-left
        self.label_logoimage.place(x=5, y=5)

        # Main title labels remain centered
        self.label_welcome = tk.Label(
            top_frame,
            text="Welcome to Steam Roulette!",
            font=("Arial", 16),
            bg=bg,
            fg=fg
        )

        self.label_welcome.grid(row=0, pady=5)

        self.label_game_name = tk.Label(
            top_frame,
            text="",
            wraplength=580,
            font=("Arial", 20),
            bg=bg,
            fg=fg
        )

        self.label_game_name.grid(row=1, pady=5)

        # ── Canvas (game art strip) ──────────────────────────────────
        self.canvas = tk.Canvas(self.root, width=600, height=300, bg="black")
        self.canvas.pack(pady=1)
        self.root.update_idletasks()
        self.display_random_header_image()

        # ── Spin / launch / store buttons ────────────────────────────
        utility_frame = tk.Frame(self.root, bg=bg)
        utility_frame.pack(pady=5)

        self.button_spin = tk.Button(utility_frame, text="Spin the Wheel",
                                     command=self.spin_wheel, font=("Arial", 14), bg=bg, fg=fg)
        self.button_spin.grid(row=0, column=0, pady=10, padx=10, columnspan=2)

        self.button_launch = tk.Button(utility_frame, text="Launch/Install Game",
                                       command=self.launch_game, state=tk.DISABLED,
                                       font=("Arial", 10), bg=bg, fg=fg)
        self.button_launch.grid(row=1, column=0, pady=5, padx=4)

        self.button_store = tk.Button(utility_frame, text="Steam Storepage",
                                      command=self.open_store, state=tk.DISABLED,
                                      font=("Arial", 10), bg=bg, fg=fg)
        self.button_store.grid(row=1, column=1, pady=5, padx=4)

        # ── Controls: number of games / exclusions ───────────────────
        self.frame_controls = tk.Frame(self.root, bg=bg)
        self.frame_controls.place(anchor="w", x=4, y=645)
        for col in range(3):
            self.frame_controls.grid_columnconfigure(col, weight=1)

        self.button_set_number_of_games = tk.Button(
            self.frame_controls, text="Set Number of Games",
            command=self.set_number_of_games, bg=bg, fg=fg)
        self.button_set_number_of_games.grid(row=0, column=1, pady=2)

        self.label_number_of_games = tk.Label(
            self.frame_controls, text="Number of games to spin:\nAll Games",
            font=("Arial", 8), bg=bg, fg=fg)
        self.label_number_of_games.grid(row=1, column=1, pady=2)

        self.button_exclude = tk.Button(
            self.frame_controls, text="Exclude Games",
            command=self.exclude_games, font=("Arial", 10), bg=bg, fg=fg)
        self.button_exclude.grid(row=2, column=1, pady=2)

        self.excluded_label = tk.Label(
            self.frame_controls, text=f"Excluded Games:\n{len(self.excluded_games)}",
            font=("Arial", 8), bg=bg, fg=fg)
        self.excluded_label.grid(row=3, column=1, pady=2)

        # ── Bottom-left: API key / user ID / theme ───────────────────
        self.button_frame = tk.Frame(self.root, bg=bg)
        self.button_frame.place(relx=0.0, rely=1.0, anchor="sw", x=2, y=-2)

        tk.Button(self.button_frame, text="Set API Key",
                  command=self.set_api_key, font=("Arial", 10), bg=bg, fg=fg
                  ).grid(row=0, column=0, pady=2, padx=2)

        tk.Button(self.button_frame, text="Set Steam User ID",
                  command=self.set_user_id_key, font=("Arial", 10), bg=bg, fg=fg
                  ).grid(row=0, column=1, pady=2, padx=2)

        tk.Button(self.button_frame, text="Toggle Dark Mode",
                  command=self.toggle_theme, font=("Arial", 10), bg=bg, fg=fg
                  ).grid(row=0, column=2, pady=2, padx=2)

        # ── Bottom-right: checkboxes + status ────────────────────────
        self.yes_no_frame = tk.Frame(self.root, bg=bg)
        self.yes_no_frame.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)

        self.please_wait_label = tk.Label(self.yes_no_frame, text="", font="6", bg=bg, fg=fg)
        self.please_wait_label.grid(row=0)

        self.include_uninstalled_var = tk.BooleanVar(value=False)
        self.include_uninstalled_checkbox = tk.Checkbutton(
            self.yes_no_frame, text="Include Uninstalled Games",
            variable=self.include_uninstalled_var, command=self.toggle_uninstalled_games,
            bg=bg, fg=fg, selectcolor=bg)
        self.include_uninstalled_checkbox.grid(sticky="w", row=1)

        self.filter_achievements_var = tk.BooleanVar(value=False)
        self.filter_achievements_checkbox = tk.Checkbutton(
            self.yes_no_frame, text="Exclude 100% Achieved Games",
            variable=self.filter_achievements_var, command=self.toggle_achievement_filter,
            bg=bg, fg=fg, selectcolor=bg)
        self.filter_achievements_checkbox.grid(sticky="w", row=2)

        self.set_light_mode()

    # ------------------------------------------------------------------
    # Image pre-loading
    # ------------------------------------------------------------------
    def _preload_installed_images(self):
        """Background worker: fetch header images for all installed games."""
        def _load(game):
            app_id = game.get("app_id")
            if not app_id:
                return
            with _image_lock:
                already = app_id in self.preloaded_images
            if already:
                return
            img = fetch_header_image(app_id, self.cache_dir)
            with _image_lock:
                self.preloaded_images[app_id] = img

        with ThreadPoolExecutor(max_workers=PRELOAD_WORKERS) as ex:
            ex.map(_load, self.installed_games)

        self.root.after(0, self._on_installed_images_ready)

    def _on_installed_images_ready(self):
        self.is_images_preloaded = True
        print("Installed-game images pre-loaded.")

    def load_images_in_parallel(self, batch_size: int = 10):
        """Load images for uninstalled games in batches (runs in a background thread)."""
        games = list(self.uninstalled_games)
        for i in range(0, len(games), batch_size):
            batch = games[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=5) as ex:
                ex.map(lambda g: fetch_header_image(g["app_id"], self.cache_dir), batch)
        self.root.after(0, self.on_images_preloaded)

    def on_images_preloaded(self):
        self.is_images_preloaded = True
        self.button_spin.config(state=tk.NORMAL, text="Spin the Wheel")
        self.include_uninstalled_checkbox.config(state=tk.NORMAL)
        self.filter_achievements_checkbox.config(state=tk.NORMAL)
        self.please_wait_label.config(text="")
        print("Uninstalled-game images loaded and cached.")

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------
    def _games_found_text(self) -> str:
        lines = ["Installed\nGames Found:"]
        for drive in self.drives:
            count = sum(1 for g in self.installed_games if g.get("path", "").startswith(drive))
            lines.append(f"{drive} {count} games")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # API key & Steam User ID
    # ------------------------------------------------------------------
    def load_api_key(self) -> str:
        return self._load_text_file("apikey.txt")

    def set_api_key(self):
        self._string_input_popup(
            title="Enter API Key",
            prompt="Please enter your Steam API Key:",
            on_submit=lambda v: (
                self._save_text_file("apikey.txt", v),
                setattr(self, "api_key", v),
                messagebox.showinfo("API Key", "API Key saved successfully."),
            ),
        )

    def load_user_id_key(self) -> str:
        return self._load_text_file("steamuserid.txt")

    def set_user_id_key(self):
        self._string_input_popup(
            title="Enter Steam User ID",
            prompt="Please enter your Steam User ID:",
            on_submit=lambda v: (
                self._save_text_file("steamuserid.txt", v),
                messagebox.showinfo("Success", "Steam User ID saved successfully."),
            ),
        )

    def save_user_id_key(self, user_id: str):
        self._save_text_file("steamuserid.txt", user_id)

    def fetch_steam_user_id(self, api_key: str, steam_id: str) -> str | None:
        """Verify a Steam ID via the Web API and return it (or None on failure)."""
        url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        try:
            resp = requests.get(url, params={"key": api_key, "steamids": steam_id}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            players = data.get("response", {}).get("players", [])
            if players:
                return players[0].get("steamid")
        except Exception as e:
            print(f"Error fetching Steam User ID: {e}")
        return None

    # ------------------------------------------------------------------
    # Generic popup helper (replaces three nearly-identical popups)
    # ------------------------------------------------------------------
    def _string_input_popup(self, title: str, prompt: str, on_submit):
        bg = self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg
        fg = self.dark_mode_fg if self.is_dark_mode else self.light_mode_fg

        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.resizable(False, False)
        ws, hs = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry(f"350x150+{int(ws/6 - 35)}+{int(hs/5 - 30)}")
        self.update_theme(popup, bg, fg)

        tk.Label(popup, text=prompt, bg=bg, fg=fg).pack(pady=10)
        entry = tk.Entry(popup, bg=bg, fg=fg)
        entry.pack(pady=5)

        def _submit():
            val = entry.get().strip()
            if val:
                on_submit(val)
                popup.destroy()
            else:
                messagebox.showerror("Error", "Field cannot be empty.")

        tk.Button(popup, text="Submit", command=_submit, bg=bg, fg=fg).pack(pady=10)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def update_theme(self, widget, bg: str, fg: str):
        try:
            widget.config(bg=bg)
        except tk.TclError:
            pass
        if isinstance(widget, tk.Checkbutton):
            widget.config(fg=fg, selectcolor=bg)
        elif isinstance(widget, (tk.Button, tk.Label, tk.Entry, tk.Text)):
            widget.config(fg=fg)
        for child in widget.winfo_children():
            self.update_theme(child, bg, fg)

    def set_light_mode(self):
        self.update_theme(self.root, self.light_mode_bg, self.light_mode_fg)

    def set_dark_mode(self):
        self.update_theme(self.root, self.dark_mode_bg, self.dark_mode_fg)

    def toggle_theme(self):
        if self.is_dark_mode:
            self.set_light_mode()
        else:
            self.set_dark_mode()
        self.is_dark_mode = not self.is_dark_mode

    # ------------------------------------------------------------------
    # Uninstalled games toggle
    # ------------------------------------------------------------------
    def toggle_uninstalled_games(self):
        if self.include_uninstalled_var.get():
            if not self.api_key:
                messagebox.showerror("Error", "Please set your Steam API key first.")
                self.include_uninstalled_var.set(False)
                return

            self.button_spin.config(state=tk.DISABLED, text="Loading...")
            self.include_uninstalled_checkbox.config(state=tk.DISABLED)
            self.filter_achievements_checkbox.config(state=tk.DISABLED)
            self.please_wait_label.config(text="Please Wait…")

            # Run network call in a background thread to keep the UI responsive
            threading.Thread(target=self._fetch_uninstalled_in_background, daemon=True).start()
        else:
            if self.uninstalled_games:
                uninstalled_ids = {g["app_id"] for g in self.uninstalled_games}
                self.installed_games = [g for g in self.installed_games
                                        if g["app_id"] not in uninstalled_ids]
                self.uninstalled_games = []
                messagebox.showinfo("Uninstalled Games Removed",
                                    "Uninstalled games removed from the spin pool.")

    def _fetch_uninstalled_in_background(self):
        user_id = self.load_user_id_key()
        if not user_id:
            self.root.after(0, lambda: messagebox.showerror(
                "Error", "Please set your Steam User ID first."))
            self.root.after(0, lambda: self.include_uninstalled_var.set(False))
            self.root.after(0, self.enable_checkbox)
            return

        all_games = get_all_games(self.api_key, user_id)
        if not all_games:
            self.root.after(0, lambda: messagebox.showerror(
                "Error", "No games were fetched from the Steam API."))
            self.root.after(0, lambda: self.include_uninstalled_var.set(False))
            self.root.after(0, self.enable_checkbox)
            return

        installed_ids = {g["app_id"] for g in self.installed_games}
        new_uninstalled = [
            {**g, "app_id": str(g["appid"])}
            for g in all_games
            if "appid" in g and str(g["appid"]) not in installed_ids
        ]

        def _apply():
            if new_uninstalled:
                self.uninstalled_games = new_uninstalled
                self.installed_games.extend(new_uninstalled)
                if self.filter_achievements_var.get():
                    self.exclude_achievement_games()
                threading.Thread(target=self.load_images_in_parallel, daemon=True).start()
                messagebox.showinfo("Uninstalled Games Added",
                                    f"Added {len(new_uninstalled)} uninstalled games.")
            else:
                messagebox.showinfo("No Uninstalled Games",
                                    "No uninstalled games found to include.")
                self.enable_checkbox()

        self.root.after(0, _apply)

    # ------------------------------------------------------------------
    # Achievement filter
    # ------------------------------------------------------------------
    def toggle_achievement_filter(self):
        self.include_uninstalled_checkbox.config(state=tk.DISABLED)
        self.filter_achievements_checkbox.config(state=tk.DISABLED)
        self.button_spin.config(state=tk.DISABLED)
        self.please_wait_label.config(text="Please Wait…")

        if self.filter_achievements_var.get():
            threading.Thread(target=self._exclude_achievements_bg, daemon=True).start()
        else:
            threading.Thread(target=self._include_achievements_bg, daemon=True).start()

    def _exclude_achievements_bg(self):
        self.exclude_achievement_games()
        self.root.after(0, lambda: self.excluded_label.config(
            text=f"Excluded Games:\n{len(self.excluded_games)}"))
        self.root.after(0, self.save_exclusions)
        self.root.after(0, self.enable_checkbox)

    def _include_achievements_bg(self):
        self.include_achievement_games()
        self.root.after(0, lambda: self.excluded_label.config(
            text=f"Excluded Games:\n{len(self.excluded_games)}"))
        self.root.after(0, self.save_exclusions)
        self.root.after(0, self.enable_checkbox)

    def exclude_achievement_games(self):
        all_lists = self.installed_games + self.uninstalled_games
        for game in all_lists:
            app_id = game["app_id"]
            if not self.supports_achievements(app_id):
                continue
            progress = self.get_achievement_progress(app_id)
            total = progress["total"]
            if total > 0 and progress["unlocked"] == total:
                if app_id not in self.excluded_games:
                    self.excluded_games.append(app_id)

    def include_achievement_games(self):
        """Remove 100%-complete achievement games from the excluded list."""
        to_remove = []
        for app_id in list(self.excluded_games):
            progress = self.get_achievement_progress(app_id)
            total = progress["total"]
            if total > 0 and progress["unlocked"] == total:
                to_remove.append(app_id)
        for app_id in to_remove:
            self.excluded_games.remove(app_id)

    def supports_achievements(self, app_id: str) -> bool:
        url = "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
        try:
            resp = requests.get(url, params={"key": self.api_key, "appid": app_id}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return (
                "game" in data
                and "availableGameStats" in data["game"]
                and "achievements" in data["game"]["availableGameStats"]
            )
        except Exception as e:
            print(f"Error checking achievements schema for {app_id}: {e}")
            return False

    def get_achievement_progress(self, app_id: str) -> dict:
        if not self.supports_achievements(app_id):
            return {"total": 0, "unlocked": 0}
        url = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
        params = {
            "key": self.api_key,
            "steamid": self.load_user_id_key(),
            "appid": app_id,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "playerstats" in data and "achievements" in data["playerstats"]:
                achievements = data["playerstats"]["achievements"]
                return {
                    "total": len(achievements),
                    "unlocked": sum(a["achieved"] for a in achievements),
                }
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error fetching achievements for {app_id}: {e}")
        except Exception as e:
            print(f"Error fetching achievements for {app_id}: {e}")
        return {"total": 0, "unlocked": 0}

    def enable_checkbox(self):
        self.include_uninstalled_checkbox.config(state=tk.NORMAL)
        self.filter_achievements_checkbox.config(state=tk.NORMAL)
        self.button_spin.config(state=tk.NORMAL)
        self.please_wait_label.config(text="")

    # ------------------------------------------------------------------
    # Exclusion management
    # ------------------------------------------------------------------
    def load_exclusions(self):
        path = _data_path("excluded_games.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as fh:
                    self.excluded_games = json.load(fh)
                print(f"Loaded {len(self.excluded_games)} exclusions.")
            except Exception as e:
                print(f"Error loading exclusions: {e}")

    def save_exclusions(self):
        try:
            with open(_data_path("excluded_games.json"), "w") as fh:
                json.dump(self.excluded_games, fh)
        except Exception as e:
            print(f"Error saving exclusions: {e}")

    def clear_exclusions(self):
        self.excluded_games = []
        self.excluded_label.config(text=f"Excluded Games:\n0")
        self.save_exclusions()
        messagebox.showinfo("Cleared", "All exclusions have been cleared.")
        # Rebuild the checklist in the open popup if it exists
        if hasattr(self, "exclude_popup") and self.exclude_popup.winfo_exists():
            self.exclude_popup.destroy()
        self.exclude_games()

    def exclude_games(self):
        """Open (or raise) the game-exclusion popup."""
        if hasattr(self, "exclude_popup") and self.exclude_popup.winfo_exists():
            self.exclude_popup.lift()
            return

        bg = self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg
        fg = self.dark_mode_fg if self.is_dark_mode else self.light_mode_fg

        self.exclude_popup = tk.Toplevel(self.root)
        self.exclude_popup.title("Exclude Games")
        ws, hs = self.exclude_popup.winfo_screenwidth(), self.exclude_popup.winfo_screenheight()
        self.exclude_popup.geometry(f"600x500+{int(ws/24 - 25)}+{int(hs/3 - 167)}")
        self.exclude_popup.resizable(False, False)
        self.update_theme(self.exclude_popup, bg, fg)

        # Search bar
        tk.Label(self.exclude_popup, text="Search:", bg=bg, fg=fg, font=12).pack(pady=2)
        search_var = tk.StringVar()
        search_entry = tk.Entry(self.exclude_popup, textvariable=search_var, bg=bg, fg=fg, font=12)
        search_entry.pack(pady=6, padx=2)

        # Scrollable canvas
        list_canvas = tk.Canvas(self.exclude_popup, bg=bg, bd=0, highlightthickness=0)
        scrollable_frame = tk.Frame(list_canvas, bg=bg)
        scrollbar = tk.Scrollbar(self.exclude_popup, orient="vertical", command=list_canvas.yview)
        list_canvas.configure(yscrollcommand=scrollbar.set)

        # Bind scroll only to this canvas (not globally)
        list_canvas.bind("<Enter>",
                         lambda _: list_canvas.bind_all("<MouseWheel>", self._on_mousewheel(list_canvas)))
        list_canvas.bind("<Leave>",
                         lambda _: list_canvas.unbind_all("<MouseWheel>"))

        scrollbar.pack(side="right", fill="y")
        list_canvas.pack(side="left", fill="both", expand=True, padx=4)
        list_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        scrollable_frame.bind("<Configure>",
                              lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))

        sorted_games = sorted(self.installed_games, key=lambda g: g["name"].lower())
        self.game_vars: dict = {}

        def _populate(filter_text: str = ""):
            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            for game in sorted_games:
                if filter_text and filter_text not in game["name"].lower():
                    continue
                app_id = game["app_id"]
                var = tk.BooleanVar(value=(app_id in self.excluded_games))
                self.game_vars[app_id] = var
                tk.Checkbutton(
                    scrollable_frame, text=game["name"], variable=var,
                    bg=bg, fg=fg, selectcolor=bg, font=12,
                ).pack(anchor="w")

        _populate()
        search_var.trace_add("write", lambda *_: _populate(search_var.get().lower()))

        def _apply():
            self.excluded_games = [aid for aid, v in self.game_vars.items() if v.get()]
            self.excluded_label.config(text=f"Excluded Games:\n{len(self.excluded_games)}")
            self.save_exclusions()
            messagebox.showinfo("Exclusions Applied", f"Excluded {len(self.excluded_games)} games.")

        btn_row = tk.Frame(self.exclude_popup, bg=bg)
        btn_row.pack(pady=4)
        tk.Button(btn_row, text="Apply", command=_apply,
                  bg=bg, fg=fg, font=12).pack(side="left", padx=4)
        tk.Button(btn_row, text="Clear All", command=self.clear_exclusions,
                  bg=bg, fg=fg, font=12).pack(side="left", padx=4)

    @staticmethod
    def _on_mousewheel(canvas: tk.Canvas):
        def handler(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return handler

    # ------------------------------------------------------------------
    # Number-of-games selector
    # ------------------------------------------------------------------
    def set_number_of_games(self):
        bg = self.dark_mode_bg if self.is_dark_mode else self.light_mode_bg
        fg = self.dark_mode_fg if self.is_dark_mode else self.light_mode_fg

        popup = tk.Toplevel(self.root)
        popup.title("Select Number of Games")
        popup.resizable(False, False)
        ws, hs = popup.winfo_screenwidth(), popup.winfo_screenheight()
        popup.geometry(f"350x150+{int(ws/6 - 35)}+{int(hs/5 - 30)}")
        self.update_theme(popup, bg, fg)

        tk.Label(popup, text="Enter number of games to spin:", bg=bg, fg=fg).pack(pady=10)
        entry = tk.Entry(popup, bg=bg, fg=fg)
        entry.pack(pady=5)

        def _submit():
            try:
                n = int(entry.get())
                if n < 1 or n > len(self.installed_games):
                    raise ValueError
                self.selected_num_games = n
                self.label_number_of_games.config(text=f"Number selected:\n{n}")
                self.button_spin.config(state=tk.NORMAL, text="Spin the Wheel")
                popup.destroy()
            except ValueError:
                tk.Label(popup, text=f"Enter a number 1–{len(self.installed_games)}",
                         fg="red", bg=bg).pack()

        tk.Button(popup, text="Submit", command=_submit, bg=bg, fg=fg).pack(pady=10)

    # ------------------------------------------------------------------
    # Canvas image display
    # ------------------------------------------------------------------
    def display_random_header_image(self):
        if not self.installed_games:
            return
        game = random.choice(self.installed_games)
        img = fetch_header_image(game["app_id"], self.cache_dir)
        self._display_image_on_canvas(img)
        self.canvas.update_idletasks()

    def _display_image_on_canvas(self, img: Image.Image):
        self.canvas.update_idletasks()
        cw = self.canvas.winfo_width() or 600
        ch = self.canvas.winfo_height() or 300
        img_resized = img.resize((cw, ch), Image.Resampling.LANCZOS)
        img_tk = ImageTk.PhotoImage(img_resized)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=img_tk, anchor=tk.CENTER)
        self.active_images = [(img_tk, img_resized)]

    def load_image(self, app_id: str) -> Image.Image:
        with _image_lock:
            img = self.preloaded_images.get(app_id)
        if not img:
            img = fetch_header_image(app_id, self.cache_dir)
            with _image_lock:
                self.preloaded_images[app_id] = img
        cw = self.canvas.winfo_width() or 600
        ch = self.canvas.winfo_height() or 300
        return img.resize((cw, ch), Image.Resampling.LANCZOS)

    # ------------------------------------------------------------------
    # Spin logic
    # ------------------------------------------------------------------
    def spin_wheel(self):
        valid_games = [
            g for g in self.installed_games
            if "app_id" in g and g["app_id"] not in self.excluded_games
        ]
        if not valid_games:
            messagebox.showerror("Error", "No valid games available to spin.")
            return

        n = self.selected_num_games or len(valid_games)
        sample = random.sample(valid_games, min(n, len(valid_games)))

        # Pick the winner from the full valid pool (not just the sample)
        self.selected_game = random.choice(valid_games)
        print(f"Winner: {self.selected_game['name']} (app_id: {self.selected_game['app_id']})")

        self.button_spin.config(state=tk.DISABLED, text="Spinning…")
        self.button_launch.config(state=tk.DISABLED)
        self.button_store.config(state=tk.DISABLED)

        self.cycle_images(sample)

    def cycle_images(self, selected_games: list):
        self.active_images = []
        self.label_welcome.config(text="Rolling…")

        self.canvas.update_idletasks()
        cw = self.canvas.winfo_width() or 600
        ch = self.canvas.winfo_height() or 300

        # Ensure images exist in preloaded dict
        for game in selected_games:
            app_id = game["app_id"]
            with _image_lock:
                cached = self.preloaded_images.get(app_id)
            if cached is None:
                img = fetch_header_image(app_id, self.cache_dir)
                with _image_lock:
                    self.preloaded_images[app_id] = img

        # Place images on canvas side-by-side
        x_pos = 0
        games_to_draw = list(selected_games)
        # Append the winning game at the end
        if self.selected_game not in games_to_draw:
            games_to_draw.append(self.selected_game)

        for game in games_to_draw:
            app_id = game["app_id"]
            with _image_lock:
                img = self.preloaded_images.get(app_id)
            if img is None:
                continue
            try:
                img_r = img.resize((cw, ch), Image.Resampling.LANCZOS)
                img_tk = ImageTk.PhotoImage(img_r)
                item = self.canvas.create_image(x_pos, ch // 2, image=img_tk, anchor=tk.CENTER)
                self.active_images.append((item, img_tk))
                x_pos += cw
            except Exception as e:
                print(f"Error placing image for {game['name']}: {e}")

        self.animate_images()

    def animate_images(self):
        cw = self.canvas.winfo_width() or 600
        total_distance = len(self.active_images) * cw
        frames = ANIMATION_DURATION_MS // FRAME_DELAY_MS
        self.animation_speed = max(20, total_distance // frames)

        def slide():
            for item, _ in self.active_images:
                self.canvas.move(item, -self.animation_speed, 0)

            # Decelerate when the last few images are approaching
            for item, _ in self.active_images[-3:]:
                coords = self.canvas.coords(item)
                if not coords:
                    continue
                bbox = self.canvas.bbox(item)
                if bbox and (coords[0] - (bbox[2] - bbox[0]) / 2) <= 0:
                    self.animation_speed = max(MIN_SPEED,
                                               self.animation_speed * SLOWDOWN_FACTOR)

            # Check if last image has scrolled to left edge
            last_item = self.active_images[-1][0]
            coords = self.canvas.coords(last_item)
            if not coords:
                self.display_selected_game()
                return
            bbox = self.canvas.bbox(last_item)
            if bbox:
                last_left = coords[0] - (bbox[2] - bbox[0]) / 2
                if last_left <= 0:
                    self.display_selected_game()
                    return

            self.animation_id = self.root.after(FRAME_DELAY_MS, slide)

        slide()

    def display_selected_game(self):
        if self.selected_game is None:
            return
        app_id = self.selected_game["app_id"]
        img = self.load_image(app_id)
        self.label_welcome.config(text="Done!")
        self.label_game_name.config(text=self.selected_game["name"])
        self._display_image_on_canvas(img)
        self.button_spin.config(state=tk.NORMAL, text="Re-Roll")
        self.button_launch.config(state=tk.NORMAL)
        self.button_store.config(state=tk.NORMAL)

    # ------------------------------------------------------------------
    # Game actions
    # ------------------------------------------------------------------
    def launch_game(self):
        if self.selected_game:
            webbrowser.open(f"steam://run/{self.selected_game['app_id']}")

    def open_store(self):
        if self.selected_game:
            webbrowser.open(f"https://store.steampowered.com/app/{self.selected_game['app_id']}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    steam_path = STEAM_PATH
    if not steam_path or not os.path.exists(steam_path):
        print("Steam installation not found.")
        messagebox.showerror("Steam Roulette", "Could not locate your Steam installation.")
        return

    cache_dir = create_cache_directory()
    games = get_installed_games(steam_path)
    drives = get_drives()

    if not games:
        messagebox.showerror("Steam Roulette", "No installed Steam games found.")
        return

    root = tk.Tk()
    app = SteamRouletteGUI(root, games, drives)
    app.cache_dir = cache_dir
    root.mainloop()


if __name__ == "__main__":
    main()
