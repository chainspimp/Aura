# ============================================
# FILE: spotify_gui.py
# Fixed: SpotifyOAuth now uses cache_path so tokens persist between sessions
# ============================================

import tkinter as tk
from tkinter import messagebox
import logging
import os

logger = logging.getLogger(__name__)

_TOKEN_CACHE = os.path.join(os.path.expanduser("~"), ".aura_spotify_token_cache")


class SpotifyPlaylistSelector:
    def __init__(self, song_data: dict):
        self.song_data = song_data
        self.sp = self._init_spotify()

        self.root = tk.Tk()
        self.root.title("AURA - Music Identified")
        self.root.geometry("350x520")
        self.root.configure(bg='#121212')
        self.playlist_ids: dict[str, str] = {}
        self.photo = None  # keep reference so GC doesn't collect it
        self._setup_ui()

    # ── Spotify auth ──────────────────────────────────────────────────────────

    def _init_spotify(self):
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            return spotipy.Spotify(
                auth_manager=SpotifyOAuth(
                    scope="playlist-modify-public playlist-read-private",
                    redirect_uri="http://localhost:8888/callback",
                    cache_path=_TOKEN_CACHE,  # persists token between runs
                )
            )
        except ImportError:
            logger.error("spotipy not installed. Run: pip install spotipy")
            return None

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        # Album cover
        cover_url = self.song_data.get('cover_url')
        if cover_url:
            try:
                import requests
                import io
                from PIL import Image, ImageTk

                resp = requests.get(cover_url, timeout=10)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content)).resize((200, 200))
                self.photo = ImageTk.PhotoImage(img)
                tk.Label(self.root, image=self.photo, bg='#121212').pack(pady=10)
            except Exception as e:
                logger.warning(f"Could not load cover art: {e}")

        # Song info
        tk.Label(
            self.root,
            text=self.song_data.get('title', 'Unknown'),
            fg="white", bg="#121212",
            font=("Arial", 14, "bold")
        ).pack()
        tk.Label(
            self.root,
            text=self.song_data.get('artist', 'Unknown'),
            fg="#b3b3b3", bg="#121212"
        ).pack()

        # Playlist list
        tk.Label(self.root, text="Add to Playlist:", fg="white", bg="#121212", pady=10).pack()
        self.listbox = tk.Listbox(
            self.root, bg="#282828", fg="white",
            borderwidth=0, highlightthickness=0
        )
        self.listbox.pack(fill="both", expand=True, padx=20)
        self._load_playlists()

        # Add button
        tk.Button(
            self.root,
            text="ADD TO SPOTIFY",
            bg="#1DB954", fg="white",
            command=self._add_song,
            font=("Arial", 10, "bold")
        ).pack(pady=20)

    def _load_playlists(self):
        if self.sp is None:
            self.listbox.insert(tk.END, "Spotify unavailable")
            return
        try:
            playlists = self.sp.current_user_playlists()
            self.playlist_ids = {p['name']: p['id'] for p in playlists['items']}
            for name in self.playlist_ids:
                self.listbox.insert(tk.END, name)
        except Exception as e:
            logger.error(f"Failed to load playlists: {e}")
            self.listbox.insert(tk.END, "Could not load playlists")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _add_song(self):
        if self.sp is None:
            messagebox.showerror("Error", "Spotify is not connected.")
            return

        spotify_id = self.song_data.get('spotify_id')
        if not spotify_id:
            messagebox.showerror("Error", "No Spotify track ID available for this song.")
            return

        selection = self.listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "Please select a playlist first.")
            return

        playlist_name = self.listbox.get(selection[0])
        playlist_id = self.playlist_ids.get(playlist_name)
        if not playlist_id:
            messagebox.showerror("Error", "Could not find playlist ID.")
            return

        try:
            self.sp.playlist_add_tracks(playlist_id, [spotify_id])
            messagebox.showinfo("Success", f"Added to '{playlist_name}'")
            self.root.destroy()
        except Exception as e:
            logger.error(f"Failed to add track: {e}")
            messagebox.showerror("Error", f"Failed to add track: {e}")

    def show(self):
        self.root.mainloop()