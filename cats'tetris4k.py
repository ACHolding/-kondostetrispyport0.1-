#!/usr/bin/env python3
"""cats'tetris4k.py - ULTRA! TETRIS by AC Kondo (FILES_OFF).

Python 3.10+
Install: python -m pip install pygame-ce
Run:     python program.py

FILES_OFF: No bundled ROMs, assets, images, audio, or font files.
Korobeiniki (Russian Theme A) loads from YouTube at runtime via yt-dlp
into a temp cache; if that fails, a chiptune fallback is synthesized in RAM.

Controls:
    Left / Right (or A / D) : Move tetromino (with NES-style DAS autorepeat)
    Up / X (or W)           : Rotate clockwise
    Z                       : Rotate counter-clockwise
    Down (or S)             : Soft drop
    Space                   : Hard drop
    Enter                   : Start / Pause
    M                       : Toggle Audio
    F11                     : Fullscreen
"""

import math
import os
import random
import shutil
import subprocess
import tempfile
import threading
from array import array
from collections import deque
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame as pg
except ImportError:
    raise SystemExit("Install pygame-ce first: python -m pip install pygame-ce")

FILES_OFF = True

# Runtime YouTube source for Korobeiniki (no shipped audio files).
# Folk melody is public-domain; yt-dlp pulls a recording into temp cache only.
YOUTUBE_KOROBEINIKI = "ytsearch1:Korobeiniki traditional russian folk song"
YOUTUBE_CACHE_NAME = "deltatetris_korobeiniki"

# Main menu
MENU_ITEMS = ("PLAY", "HELP", "SETTINGS", "ABOUT", "EXIT")
TETRIS_OG_DATE = "JUN 6 1984"
NES_TETRIS_DATE = "NOV 1989"

# NES standard resolution & internal render target
WIDTH, HEIGHT = 256, 224
FPS = 60
STEP = 1.0 / 60.0

# 10x20 Playfield
BOARD_W, BOARD_H = 10, 20
TILE = 8
BOARD_X = 96
BOARD_Y = 32

# Authentic NES Tetris Palette
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (170, 170, 170)
DARK_GRAY = (80, 80, 80)
RED = (230, 40, 40)

# NES Level Color Schemes (Primary & Secondary)
LEVEL_PALETTES = [
    ((74, 117, 255), (107, 205, 253)),   # 0: Blue
    ((62, 186, 62),  (181, 235, 78)),    # 1: Green
    ((180, 49, 219), (242, 114, 255)),   # 2: Magenta
    ((74, 117, 255), (114, 246, 120)),   # 3: Cyan/Green
    ((230, 40, 120), (90, 230, 140)),    # 4: Rose/Cyan
    ((120, 230, 180),(160, 180, 255)),   # 5: Mint
    ((210, 70, 30),  (160, 160, 160)),   # 6: Rust
    ((120, 40, 200), (190, 50, 60)),     # 7: Purple
    ((40, 90, 240),  (220, 60, 60)),     # 8: Dark Blue
    ((220, 90, 40),  (240, 180, 60)),    # 9: Orange
]

# Tetromino definitions (4x4 grids)
TETROMINOES = {
    "T": [
        [(0, 1), (1, 1), (2, 1), (1, 2)],
        [(1, 0), (1, 1), (1, 2), (0, 1)],
        [(0, 1), (1, 1), (2, 1), (1, 0)],
        [(1, 0), (1, 1), (1, 2), (2, 1)],
    ],
    "J": [
        [(0, 1), (1, 1), (2, 1), (0, 2)],
        [(1, 0), (1, 1), (1, 2), (0, 0)],
        [(0, 1), (1, 1), (2, 1), (2, 0)],
        [(1, 0), (1, 1), (1, 2), (2, 2)],
    ],
    "Z": [
        [(0, 1), (1, 1), (1, 2), (2, 2)],
        [(1, 0), (1, 1), (0, 1), (0, 2)],
        [(0, 1), (1, 1), (1, 2), (2, 2)],
        [(1, 0), (1, 1), (0, 1), (0, 2)],
    ],
    "O": [
        [(1, 1), (2, 1), (1, 2), (2, 2)],
        [(1, 1), (2, 1), (1, 2), (2, 2)],
        [(1, 1), (2, 1), (1, 2), (2, 2)],
        [(1, 1), (2, 1), (1, 2), (2, 2)],
    ],
    "S": [
        [(1, 1), (2, 1), (0, 2), (1, 2)],
        [(0, 0), (0, 1), (1, 1), (1, 2)],
        [(1, 1), (2, 1), (0, 2), (1, 2)],
        [(0, 0), (0, 1), (1, 1), (1, 2)],
    ],
    "L": [
        [(0, 1), (1, 1), (2, 1), (2, 2)],
        [(1, 0), (1, 1), (1, 2), (0, 2)],
        [(0, 1), (1, 1), (2, 1), (0, 0)],
        [(1, 0), (1, 1), (1, 2), (2, 0)],
    ],
    "I": [
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        [(2, 0), (2, 1), (2, 2), (2, 3)],
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        [(2, 0), (2, 1), (2, 2), (2, 3)],
    ],
}

# 1 = primary color, 2 = secondary color, 3 = pure white
PIECE_COLOR_STYLE = {
    "T": 1,
    "J": 2,
    "Z": 1,
    "O": 3,
    "S": 2,
    "L": 1,
    "I": 2,
}

# Drop speeds (frames per grid step) matching authentic NES Tetris
NES_SPEED_TABLE = [
    48, 43, 38, 33, 28, 23, 18, 13, 8, 6,
    5, 5, 5, 4, 4, 4, 3, 3, 3, 2,
    2, 2, 2, 2, 2, 2, 2, 2, 2, 1
]

# Embedded 5x7 Font
GLYPHS = {
    "A": "01110/10001/10001/11111/10001/10001/10001",
    "B": "11110/10001/10001/11110/10001/10001/11110",
    "C": "01111/10000/10000/10000/10000/10000/01111",
    "D": "11110/10001/10001/10001/10001/10001/11110",
    "E": "11111/10000/10000/11110/10000/10000/11111",
    "F": "11111/10000/10000/11110/10000/10000/10000",
    "G": "01111/10000/10000/10111/10001/10001/01111",
    "H": "10001/10001/10001/11111/10001/10001/10001",
    "I": "11111/00100/00100/00100/00100/00100/11111",
    "J": "00111/00010/00010/00010/10010/10010/01100",
    "K": "10001/10010/10100/11000/10100/10010/10001",
    "L": "10000/10000/10000/10000/10000/10000/11111",
    "M": "10001/11011/10101/10101/10001/10001/10001",
    "N": "10001/11001/10101/10011/10001/10001/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110",
    "P": "11110/10001/10001/11110/10000/10000/10000",
    "Q": "01110/10001/10001/10001/10101/10010/01101",
    "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110",
    "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "10001/10001/10001/10001/10001/10001/01110",
    "V": "10001/10001/10001/10001/10001/01010/00100",
    "W": "10001/10001/10001/10101/10101/11011/10001",
    "X": "10001/10001/01010/00100/01010/10001/10001",
    "Y": "10001/10001/01010/00100/00100/00100/00100",
    "Z": "11111/00001/00010/00100/01000/10000/11111",
    "0": "01110/10001/10011/10101/11001/10001/01110",
    "1": "00100/01100/00100/00100/00100/00100/01110",
    "2": "01110/10001/00001/00010/00100/01000/11111",
    "3": "11110/00001/00001/01110/00001/00001/11110",
    "4": "00010/00110/01010/10010/11111/00010/00010",
    "5": "11111/10000/10000/11110/00001/00001/11110",
    "6": "01110/10000/10000/11110/10001/10001/01110",
    "7": "11111/00001/00010/00100/01000/01000/01000",
    "8": "01110/10001/10001/01110/10001/10001/01110",
    "9": "01110/10001/10001/01111/00001/00001/01110",
    "-": "00000/00000/00000/11111/00000/00000/00000",
    ".": "00000/00000/00000/00000/00000/00110/00110",
    ":": "00000/00110/00110/00000/00110/00110/00000",
    "!": "00100/00100/00100/00100/00100/00000/00100",
    "?": "01110/10001/00001/00010/00100/00000/00100",
    "/": "00001/00010/00010/00100/01000/01000/10000",
    ">": "10000/01000/00100/00010/00100/01000/10000",
    "=": "00000/00000/11111/00000/11111/00000/00000",
    "(": "00010/00100/01000/01000/01000/00100/00010",
    ")": "01000/00100/00010/00010/00010/00100/01000",
    "[": "01110/01000/01000/01000/01000/01000/01110",
    "]": "01110/00010/00010/00010/00010/00010/01110",
    "+": "00000/00100/00100/11111/00100/00100/00000",
    ",": "00000/00000/00000/00000/00110/00010/00100",
    "'": "00100/00100/00000/00000/00000/00000/00000",
    "*": "00000/10101/01110/11111/01110/10101/00000",
}


@lru_cache(maxsize=512)
def text_surf(val, color=WHITE, scale=1):
    surf = pg.Surface((max(1, len(val) * 6 - 1) * scale, 7 * scale), pg.SRCALPHA)
    for i, ch in enumerate(val.upper()):
        for y, row in enumerate(GLYPHS.get(ch, "").split("/")):
            for x, bit in enumerate(row):
                if bit == "1":
                    pg.draw.rect(surf, color, ((i * 6 + x) * scale, y * scale, scale, scale))
    return surf


def draw_text(surf, val, x, y, color=WHITE, scale=1, center=False):
    lbl = text_surf(str(val), color, scale)
    dx = round(x - lbl.get_width() / 2) if center else round(x)
    surf.blit(lbl, (dx, round(y)))


class SoundEngine:
    """SFX synth + Korobeiniki from YouTube (FILES_OFF: no bundled audio).

    Startup must stay instant: synth loads immediately; YouTube fetches in a
    background thread and swaps in when ready.
    """

    def __init__(self):
        self.rate = 44100
        self.available = False
        self.muted = False
        self.sounds = {}
        self.music = None
        self.music_path = None
        self.using_youtube = False
        self.music_channel = None
        self.sfx_channels = []
        self._yt_lock = threading.Lock()
        self._yt_thread = None
        self._init_mixer()
        if self.available:
            self.build_sfx()
            # Instant path — never block the window on network.
            self.music = self._synth_korobeiniki()
            self.using_youtube = False
            print("Music source: synthesized Korobeiniki (instant)")
            self._start_youtube_bg()

    def _init_mixer(self):
        configs = [
            (22050, -16, 1, 512),
            (44100, -16, 1, 1024),
            (22050, -16, 2, 512),
            (44100, -16, 2, 1024),
        ]
        last_err = None
        for freq, size, chans, buf in configs:
            try:
                if pg.mixer.get_init():
                    pg.mixer.quit()
                pg.mixer.init(freq, size, chans, buf)
                info = pg.mixer.get_init()
                if not info:
                    continue
                self.rate = info[0]
                pg.mixer.set_num_channels(8)
                self.music_channel = pg.mixer.Channel(0)
                self.sfx_channels = [pg.mixer.Channel(i) for i in range(1, 8)]
                self.available = True
                return
            except Exception as exc:
                last_err = exc
        self.available = False
        print("Audio unavailable, continuing silently:", last_err)

    def synth_square(self, duration, freq, vol=0.15, duty=0.5):
        """Fast square-wave PCM (period tiling — no per-sample Python math)."""
        count = max(1, int(self.rate * duration))
        amp = int(32767 * vol)
        if not freq or freq <= 0:
            return array("h", [0] * count)
        period = max(2, int(round(self.rate / float(freq))))
        high = max(1, min(period - 1, int(period * duty)))
        cycle = array("h", [amp] * high + [-amp] * (period - high))
        reps, rem = divmod(count, period)
        out = array("h")
        if reps:
            out.extend(cycle * reps)
        if rem:
            out.extend(cycle[:rem])
        # Tiny fade edges to avoid clicks
        fade = min(32, count // 4)
        for i in range(fade):
            out[i] = int(out[i] * (i / fade))
            out[-1 - i] = int(out[-1 - i] * (i / fade))
        return out

    def build_sfx(self):
        self.sounds["move"] = pg.mixer.Sound(buffer=self.synth_square(0.04, 300, 0.14))
        self.sounds["rotate"] = pg.mixer.Sound(buffer=self.synth_square(0.05, 520, 0.16))
        self.sounds["drop"] = pg.mixer.Sound(buffer=self.synth_square(0.06, 180, 0.22))

        clear_samples = array("h")
        for f in (440, 554, 659, 880):
            clear_samples.extend(self.synth_square(0.05, f, 0.16))
        self.sounds["clear"] = pg.mixer.Sound(buffer=clear_samples)

        tetris_samples = array("h")
        for f in (523, 659, 783, 1046, 1318):
            tetris_samples.extend(self.synth_square(0.08, f, 0.22))
        self.sounds["tetris"] = pg.mixer.Sound(buffer=tetris_samples)

        gameover_samples = array("h")
        for f in (400, 350, 300, 250, 200, 150):
            gameover_samples.extend(self.synth_square(0.12, f, 0.2))
        self.sounds["gameover"] = pg.mixer.Sound(buffer=gameover_samples)

    def _synth_korobeiniki(self):
        # Theme A (Korobeiniki) — compact loop so startup stays snappy.
        korobeiniki = [
            (76, 4), (71, 2), (72, 2), (74, 4), (72, 2), (71, 2),
            (69, 4), (69, 2), (72, 2), (76, 4), (74, 2), (72, 2),
            (71, 6), (72, 2), (74, 4), (76, 4),
            (72, 4), (69, 4), (69, 8),
            (0, 2), (74, 4), (77, 2), (81, 4), (79, 2), (77, 2),
            (76, 6), (72, 2), (76, 4), (74, 2), (72, 2),
            (71, 4), (71, 2), (72, 2), (74, 4), (76, 4),
            (72, 4), (69, 4), (69, 8),
        ]
        music_samples = array("h")
        beat = 0.09
        for midi, length in korobeiniki:
            freq = 440.0 * (2.0 ** ((midi - 69) / 12.0)) if midi > 0 else 0.0
            music_samples.extend(self.synth_square(beat * length, freq, 0.12, duty=0.25))
        return pg.mixer.Sound(buffer=music_samples)

    def _youtube_cache_path(self) -> Path:
        return Path(tempfile.gettempdir()) / YOUTUBE_CACHE_NAME

    def _cached_youtube(self) -> str | None:
        base = self._youtube_cache_path()
        for ext in (".wav", ".ogg", ".mp3", ".m4a", ".webm", ".opus"):
            hit = Path(str(base) + ext)
            if hit.is_file() and hit.stat().st_size > 8000:
                return str(hit)
        matches = sorted(Path(tempfile.gettempdir()).glob(YOUTUBE_CACHE_NAME + ".*"))
        for hit in matches:
            if hit.is_file() and hit.stat().st_size > 8000 and hit.suffix.lower() not in {".part", ".ytdl", ".temp"}:
                return str(hit)
        return None

    def _fetch_youtube(self) -> str | None:
        """Download Korobeiniki from YouTube into temp cache (FILES_OFF)."""
        if FILES_OFF is not True:
            return None
        hit = self._cached_youtube()
        if hit:
            return hit

        ytdlp = shutil.which("yt-dlp") or shutil.which("youtube-dl")
        if not ytdlp:
            return None

        base = self._youtube_cache_path()
        outtmpl = str(base) + ".%(ext)s"
        env = os.environ.copy()
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                    "ALL_PROXY", "all_proxy"):
            env.pop(key, None)

        attempts = [
            [ytdlp, "-f", "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
             "--no-playlist", "--no-warnings", "--socket-timeout", "10",
             "-o", outtmpl, YOUTUBE_KOROBEINIKI],
            [ytdlp, "-f", "bestaudio/best", "-x", "--audio-format", "wav",
             "--audio-quality", "5", "--no-playlist", "--no-warnings",
             "--socket-timeout", "10", "-o", outtmpl, YOUTUBE_KOROBEINIKI],
        ]
        for cmd in attempts:
            try:
                proc = subprocess.run(
                    cmd, check=False, timeout=25, capture_output=True, text=True, env=env
                )
                if proc.returncode == 0:
                    hit = self._cached_youtube()
                    if hit:
                        return hit
            except Exception:
                continue
        return None

    def _start_youtube_bg(self):
        if self._yt_thread and self._yt_thread.is_alive():
            return

        def worker():
            print("Fetching Korobeiniki from YouTube in background…")
            path = self._fetch_youtube()
            if not path:
                print("YouTube fetch skipped/failed — keeping synth")
                return
            with self._yt_lock:
                self.music_path = path
                self.using_youtube = True
            print("Music source: YouTube cache ->", path)
            # If music is already looping on synth, hot-swap to YouTube.
            if self.available and not self.muted:
                try:
                    playing = (
                        self.music_channel is not None and self.music_channel.get_busy()
                    )
                    if playing or pg.mixer.music.get_busy():
                        if self.music_channel is not None:
                            self.music_channel.stop()
                        pg.mixer.music.load(path)
                        pg.mixer.music.set_volume(0.55)
                        pg.mixer.music.play(-1)
                except Exception as exc:
                    print("YouTube hot-swap failed:", exc)

        self._yt_thread = threading.Thread(target=worker, name="yt-korobeiniki", daemon=True)
        self._yt_thread.start()

    def play_sfx(self, name):
        if self.available and not self.muted and name in self.sounds:
            for ch in self.sfx_channels:
                if not ch.get_busy():
                    ch.play(self.sounds[name])
                    break

    def start_music(self):
        if not self.available or self.muted:
            return
        try:
            with self._yt_lock:
                use_yt = self.using_youtube and self.music_path
                path = self.music_path
            if use_yt and path:
                if self.music_channel is not None:
                    self.music_channel.stop()
                pg.mixer.music.load(path)
                pg.mixer.music.set_volume(0.55)
                pg.mixer.music.play(-1)
            elif self.music is not None and self.music_channel is not None:
                try:
                    pg.mixer.music.stop()
                except Exception:
                    pass
                self.music_channel.set_volume(0.45)
                self.music_channel.play(self.music, loops=-1)
        except Exception as exc:
            print("start_music failed:", exc)

    def stop_all(self):
        if not self.available:
            return
        try:
            pg.mixer.music.stop()
        except Exception:
            pass
        if self.music_channel is not None:
            self.music_channel.stop()
        for ch in self.sfx_channels:
            ch.stop()

    def pause_music(self, paused: bool):
        if not self.available or self.muted:
            return
        try:
            with self._yt_lock:
                use_yt = self.using_youtube
            if use_yt:
                if paused:
                    pg.mixer.music.pause()
                else:
                    pg.mixer.music.unpause()
            elif self.music_channel is not None:
                if paused:
                    self.music_channel.pause()
                else:
                    self.music_channel.unpause()
        except Exception:
            pass

    def toggle(self):
        self.muted = not self.muted
        if self.muted:
            self.stop_all()
        else:
            self.start_music()


class Tetris:
    def __init__(self, audio):
        self.audio = audio
        self.high_score = 10000
        self.menu_index = 0
        self.start_level = 0
        self.menu_tick = 0
        self.reset_game(to_menu=True)

    def reset_game(self, to_menu=False):
        self.board = [[0] * BOARD_W for _ in range(BOARD_H)]
        self.score = 0
        self.lines = 0
        self.level = self.start_level
        self.state = "MENU" if to_menu else "PLAY"

        self.stats = {k: 0 for k in TETROMINOES}
        self.bag = list(TETROMINOES.keys())
        random.shuffle(self.bag)

        self.current_piece = None
        self.current_pos = [0, 0]
        self.current_rot = 0

        self.next_piece = self.pop_piece()
        self.spawn_piece()
        # spawn_piece may set GAMEOVER on a full board; force menu when requested
        if to_menu:
            self.state = "MENU"

        self.drop_timer = 0
        self.clearing_rows = []
        self.clear_timer = 0

        # Authentic NES DAS (Delayed Auto Shift)
        self.das_dir = 0
        self.das_timer = 0

    def go_menu(self):
        self.audio.stop_all()
        self.reset_game(to_menu=True)
        self.menu_index = 0

    def start_play(self):
        self.reset_game(to_menu=False)
        self.state = "PLAY"
        self.level = self.start_level
        self.audio.start_music()

    def menu_move(self, delta):
        self.menu_index = (self.menu_index + delta) % len(MENU_ITEMS)
        self.audio.play_sfx("move")

    def menu_activate(self):
        item = MENU_ITEMS[self.menu_index]
        self.audio.play_sfx("rotate")
        if item == "PLAY":
            self.start_play()
            return None
        if item == "HELP":
            self.state = "HELP"
        elif item == "SETTINGS":
            self.state = "SETTINGS"
        elif item == "ABOUT":
            self.state = "ABOUT"
        elif item == "EXIT":
            return "QUIT"
        return None

    def pop_piece(self):
        if not self.bag:
            self.bag = list(TETROMINOES.keys())
            random.shuffle(self.bag)
        return self.bag.pop()

    def spawn_piece(self):
        self.current_piece = self.next_piece
        self.next_piece = self.pop_piece()
        self.current_rot = 0
        self.stats[self.current_piece] += 1

        # Spawn top center
        self.current_pos = [3, 0]

        if self.check_collision(self.current_piece, self.current_pos, self.current_rot):
            self.state = "GAMEOVER"
            self.audio.stop_all()
            self.audio.play_sfx("gameover")

    def get_blocks(self, piece, rot):
        return TETROMINOES[piece][rot % len(TETROMINOES[piece])]

    def check_collision(self, piece, pos, rot):
        blocks = self.get_blocks(piece, rot)
        for bx, by in blocks:
            gx = pos[0] + bx
            gy = pos[1] + by
            if gx < 0 or gx >= BOARD_W or gy >= BOARD_H:
                return True
            if gy >= 0 and self.board[gy][gx] != 0:
                return True
        return False

    def lock_piece(self):
        blocks = self.get_blocks(self.current_piece, self.current_rot)
        color_id = PIECE_COLOR_STYLE[self.current_piece]
        for bx, by in blocks:
            gx = self.current_pos[0] + bx
            gy = self.current_pos[1] + by
            if 0 <= gy < BOARD_H and 0 <= gx < BOARD_W:
                self.board[gy][gx] = color_id

        self.audio.play_sfx("drop")
        self.check_lines()

    def check_lines(self):
        self.clearing_rows = [y for y, row in enumerate(self.board) if all(cell != 0 for cell in row)]
        if self.clearing_rows:
            self.state = "CLEARING"
            self.clear_timer = 20
            if len(self.clearing_rows) == 4:
                self.audio.play_sfx("tetris")
            else:
                self.audio.play_sfx("clear")
        else:
            self.spawn_piece()

    def finalize_clear(self):
        for y in self.clearing_rows:
            del self.board[y]
            self.board.insert(0, [0] * BOARD_W)

        count = len(self.clearing_rows)
        self.lines += count

        # Classic NES Scoring
        multiplier = [0, 40, 100, 300, 1200][count]
        self.score += multiplier * (self.level + 1)
        self.high_score = max(self.high_score, self.score)

        # Check level advancement (every 10 lines)
        self.level = self.lines // 10

        self.clearing_rows.clear()
        self.state = "PLAY"
        self.spawn_piece()

    def rotate(self, dir_rot):
        new_rot = (self.current_rot + dir_rot) % len(TETROMINOES[self.current_piece])
        if not self.check_collision(self.current_piece, self.current_pos, new_rot):
            self.current_rot = new_rot
            self.audio.play_sfx("rotate")

    def move(self, dx):
        new_pos = [self.current_pos[0] + dx, self.current_pos[1]]
        if not self.check_collision(self.current_piece, new_pos, self.current_rot):
            self.current_pos = new_pos
            self.audio.play_sfx("move")
            return True
        return False

    def hard_drop(self):
        while not self.check_collision(self.current_piece, [self.current_pos[0], self.current_pos[1] + 1], self.current_rot):
            self.current_pos[1] += 1
            self.score += 1
        self.lock_piece()

    def update(self):
        if self.state != "PLAY":
            if self.state == "CLEARING":
                self.clear_timer -= 1
                if self.clear_timer <= 0:
                    self.finalize_clear()
            return

        # DAS key movement updates
        keys = pg.key.get_pressed()
        curr_dir = 0
        if keys[pg.K_LEFT] or keys[pg.K_a]:
            curr_dir = -1
        elif keys[pg.K_RIGHT] or keys[pg.K_d]:
            curr_dir = 1

        if curr_dir != 0:
            if self.das_dir == curr_dir:
                self.das_timer += 1
                if self.das_timer >= 16 and (self.das_timer - 16) % 6 == 0:
                    self.move(curr_dir)
            else:
                self.das_dir = curr_dir
                self.das_timer = 0
                self.move(curr_dir)
        else:
            self.das_dir = 0
            self.das_timer = 0

        # Gravity / Fall Speed
        lvl_idx = min(self.level, len(NES_SPEED_TABLE) - 1)
        speed = NES_SPEED_TABLE[lvl_idx]

        soft_drop = keys[pg.K_DOWN] or keys[pg.K_s]
        if soft_drop:
            speed = min(speed, 2)

        self.drop_timer += 1
        if self.drop_timer >= speed:
            self.drop_timer = 0
            if not self.check_collision(self.current_piece, [self.current_pos[0], self.current_pos[1] + 1], self.current_rot):
                self.current_pos[1] += 1
                if soft_drop:
                    self.score += 1
            else:
                self.lock_piece()


# Drawing Procedures
def draw_block(surf, x, y, color_style, palette_idx):
    pal = LEVEL_PALETTES[palette_idx % len(LEVEL_PALETTES)]
    if color_style == 1:
        base, hi = pal[0], WHITE
    elif color_style == 2:
        base, hi = pal[1], WHITE
    else:
        base, hi = WHITE, pal[0]

    # NES Authentic Beveled Block Shader
    pg.draw.rect(surf, base, (x, y, TILE, TILE))
    pg.draw.line(surf, hi, (x, y), (x + TILE - 1, y))
    pg.draw.line(surf, hi, (x, y), (x, y + TILE - 1))
    pg.draw.line(surf, BLACK, (x + TILE - 1, y), (x + TILE - 1, y + TILE - 1))
    pg.draw.line(surf, BLACK, (x, y + TILE - 1), (x + TILE - 1, y + TILE - 1))
    surf.set_at((x + 1, y + 1), hi)


def draw_frame(surf, x, y, w, h):
    pg.draw.rect(surf, BLACK, (x, y, w, h))
    pg.draw.rect(surf, WHITE, (x, y, w, h), 2)
    pg.draw.rect(surf, DARK_GRAY, (x + 2, y + 2, w - 4, h - 4), 1)


def render(surf, game):
    surf.fill(BLACK)
    pal_idx = game.level % len(LEVEL_PALETTES)

    # 1. Left Panel: Piece Statistics
    draw_frame(surf, 16, 32, 64, 160)
    draw_text(surf, "STATS", 32, 38, RED)

    preview_pieces = ["T", "J", "Z", "O", "S", "L", "I"]
    for i, p_name in enumerate(preview_pieces):
        py = 52 + i * 20
        # Draw miniature tetromino
        blocks = TETROMINOES[p_name][0]
        c_style = PIECE_COLOR_STYLE[p_name]
        for bx, by in blocks:
            draw_block(surf, 24 + bx * 5, py + by * 5, c_style, pal_idx)
        draw_text(surf, str(game.stats[p_name]).zfill(3), 54, py + 3, WHITE)

    # 2. Center Panel: Matrix Board
    draw_frame(surf, BOARD_X - 4, BOARD_Y - 4, BOARD_W * TILE + 8, BOARD_H * TILE + 8)

    # Draw settled blocks
    for y in range(BOARD_H):
        if game.state == "CLEARING" and y in game.clearing_rows:
            # Flashing clear line effect
            if (game.clear_timer // 2) % 2 == 0:
                pg.draw.rect(surf, WHITE, (BOARD_X, BOARD_Y + y * TILE, BOARD_W * TILE, TILE))
                continue
        for x in range(BOARD_W):
            cell = game.board[y][x]
            if cell != 0:
                draw_block(surf, BOARD_X + x * TILE, BOARD_Y + y * TILE, cell, pal_idx)

    # Draw active tetromino
    if game.state in ("PLAY", "PAUSE"):
        blocks = game.get_blocks(game.current_piece, game.current_rot)
        c_style = PIECE_COLOR_STYLE[game.current_piece]
        for bx, by in blocks:
            gx = game.current_pos[0] + bx
            gy = game.current_pos[1] + by
            if 0 <= gy < BOARD_H and 0 <= gx < BOARD_W:
                draw_block(surf, BOARD_X + gx * TILE, BOARD_Y + gy * TILE, c_style, pal_idx)

    # 3. Right Panel: Score, Lines, Level, Next
    draw_frame(surf, 184, 32, 60, 48)
    draw_text(surf, "TOP", 192, 36, RED)
    draw_text(surf, str(game.high_score).zfill(6), 192, 46, WHITE)
    draw_text(surf, "SCORE", 192, 56, RED)
    draw_text(surf, str(game.score).zfill(6), 192, 66, WHITE)

    draw_frame(surf, 184, 88, 60, 30)
    draw_text(surf, "LINES", 192, 92, RED)
    draw_text(surf, str(game.lines).zfill(3), 200, 104, WHITE)

    draw_frame(surf, 184, 126, 60, 40)
    draw_text(surf, "NEXT", 196, 130, RED)
    next_blocks = TETROMINOES[game.next_piece][0]
    next_style = PIECE_COLOR_STYLE[game.next_piece]
    for bx, by in next_blocks:
        draw_block(surf, 198 + bx * TILE, 142 + by * TILE, next_style, pal_idx)

    draw_frame(surf, 184, 174, 60, 24)
    draw_text(surf, "LEVEL", 192, 178, RED)
    draw_text(surf, str(game.level).zfill(2), 204, 188, WHITE)

    # UI Overlays
    if game.state == "MENU":
        render_main_menu(surf, game)
    elif game.state == "HELP":
        render_panel(surf, "HELP", [
            "LEFT RIGHT  MOVE",
            "UP / X / W  ROTATE",
            "Z  ROTATE CCW",
            "DOWN  SOFT DROP",
            "SPACE  HARD DROP",
            "ENTER  PAUSE",
            "ESC  MAIN MENU",
            "M  TOGGLE AUDIO",
            "F11  FULLSCREEN",
        ], "ENTER / ESC BACK")
    elif game.state == "SETTINGS":
        audio_lbl = "OFF" if game.audio.muted else "ON"
        render_panel(surf, "SETTINGS", [
            f"AUDIO  {audio_lbl}",
            f"START LV  {game.start_level:02d}",
            "",
            "LEFT RIGHT  LEVEL",
            "M / ENTER  AUDIO",
            "ESC  BACK",
        ], "ULTRA! TETRIS OPTIONS")
    elif game.state == "ABOUT":
        render_panel(surf, "ABOUT", [
            "ULTRA! TETRIS",
            "[C] AC KONDO",
            "1999-2026",
            "",
            "TETRIS CO.",
            f"OG {TETRIS_OG_DATE}",
            f"NES {NES_TETRIS_DATE}",
            "",
            "FILES_OFF BUILD",
            "KOROBEINIKI THEME",
        ], "ENTER / ESC BACK")
    elif game.state == "PAUSE":
        draw_text(surf, "PAUSE", BOARD_X + 18, BOARD_Y + 70, WHITE, scale=2)
        draw_text(surf, "ESC MENU", BOARD_X + 12, BOARD_Y + 100, GRAY)

    elif game.state == "GAMEOVER":
        draw_text(surf, "GAME OVER", BOARD_X + 6, BOARD_Y + 70, RED, scale=2)
        draw_text(surf, "ENTER MENU", BOARD_X + 8, BOARD_Y + 95, WHITE)
        draw_text(surf, "SPACE RETRY", BOARD_X + 8, BOARD_Y + 110, GRAY)


def render_main_menu(surf, game):
    shade = pg.Surface((WIDTH, HEIGHT), pg.SRCALPHA)
    shade.fill((0, 0, 0, 220))
    surf.blit(shade, (0, 0))

    # Soft animated accent blocks
    pal = LEVEL_PALETTES[(game.menu_tick // 90) % len(LEVEL_PALETTES)]
    for i, name in enumerate(("T", "J", "Z", "O", "S", "L", "I")):
        bx = 18 + (i % 4) * 58
        by = 12 + (i // 4) * 18 + ((game.menu_tick // 8 + i * 3) % 6)
        for ox, oy in TETROMINOES[name][0]:
            draw_block(surf, bx + ox * 5, by + oy * 5, PIECE_COLOR_STYLE[name], game.menu_tick // 90)

    draw_text(surf, "ULTRA! TETRIS", WIDTH // 2, 48, RED, scale=2, center=True)
    draw_text(surf, "[C] AC KONDO 1999-2026", WIDTH // 2, 72, WHITE, center=True)
    draw_text(surf, f"TETRIS CO. OG {TETRIS_OG_DATE}", WIDTH // 2, 84, GRAY, center=True)

    base_y = 108
    for i, label in enumerate(MENU_ITEMS):
        selected = i == game.menu_index
        color = RED if selected else WHITE
        prefix = ">" if selected else " "
        # Blink cursor
        if selected and (game.menu_tick // 16) % 2 == 0:
            prefix = " "
        draw_text(surf, f"{prefix} {label}", WIDTH // 2, base_y + i * 14, color, center=True)

    draw_text(surf, "UP DOWN SELECT  ENTER", WIDTH // 2, 200, DARK_GRAY, center=True)
    draw_text(surf, "EXIT GAME = EXIT", WIDTH // 2, 212, DARK_GRAY, center=True)


def render_panel(surf, title, lines, footer):
    shade = pg.Surface((WIDTH, HEIGHT), pg.SRCALPHA)
    shade.fill((0, 0, 0, 230))
    surf.blit(shade, (0, 0))
    draw_frame(surf, 28, 24, WIDTH - 56, HEIGHT - 48)
    draw_text(surf, title, WIDTH // 2, 36, RED, scale=2, center=True)
    y = 64
    for line in lines:
        if line:
            draw_text(surf, line, WIDTH // 2, y, WHITE, center=True)
        y += 12
    draw_text(surf, footer, WIDTH // 2, HEIGHT - 40, GRAY, center=True)


def main():
    # Pre-init mixer BEFORE pg.init so audio actually comes up on macOS.
    pg.mixer.pre_init(22050, -16, 1, 512)
    pg.init()
    pg.display.init()
    info = pg.display.Info()

    scale = max(1, min(4, (info.current_h - 100) // HEIGHT, (info.current_w - 100) // WIDTH))
    windowed_size = (WIDTH * scale, HEIGHT * scale)
    screen = pg.display.set_mode(windowed_size, pg.RESIZABLE)
    pg.display.set_caption("ULTRA! TETRIS [C] AC KONDO 1999-2026")

    audio = SoundEngine()
    game = Tetris(audio)
    canvas = pg.Surface((WIDTH, HEIGHT))
    clock = pg.time.Clock()

    running = True
    fullscreen = False

    try:
        while running:
            clock.tick(FPS)

            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False

                elif event.type == pg.KEYDOWN:
                    if event.key == pg.K_F11:
                        fullscreen = not fullscreen
                        screen = pg.display.set_mode((0, 0), pg.FULLSCREEN) if fullscreen else pg.display.set_mode(windowed_size, pg.RESIZABLE)

                    elif event.key == pg.K_m and game.state in ("MENU", "SETTINGS", "PLAY", "PAUSE"):
                        audio.toggle()
                        if game.state == "SETTINGS":
                            audio.play_sfx("rotate")

                    elif game.state == "MENU":
                        if event.key in (pg.K_UP, pg.K_w):
                            game.menu_move(-1)
                        elif event.key in (pg.K_DOWN, pg.K_s):
                            game.menu_move(1)
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            if game.menu_activate() == "QUIT":
                                running = False
                        elif event.key == pg.K_ESCAPE:
                            running = False

                    elif game.state in ("HELP", "ABOUT"):
                        if event.key in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE):
                            game.state = "MENU"
                            audio.play_sfx("move")

                    elif game.state == "SETTINGS":
                        if event.key in (pg.K_ESCAPE,):
                            game.state = "MENU"
                            audio.play_sfx("move")
                        elif event.key in (pg.K_LEFT, pg.K_a):
                            game.start_level = max(0, game.start_level - 1)
                            audio.play_sfx("move")
                        elif event.key in (pg.K_RIGHT, pg.K_d):
                            game.start_level = min(29, game.start_level + 1)
                            audio.play_sfx("move")
                        elif event.key in (pg.K_RETURN, pg.K_SPACE):
                            audio.toggle()
                            audio.play_sfx("rotate")

                    elif game.state == "GAMEOVER":
                        if event.key in (pg.K_RETURN, pg.K_ESCAPE):
                            game.go_menu()
                        elif event.key == pg.K_SPACE:
                            game.start_play()

                    elif game.state in ("PLAY", "PAUSE"):
                        if event.key == pg.K_ESCAPE:
                            game.go_menu()
                        elif event.key == pg.K_RETURN:
                            game.state = "PAUSE" if game.state == "PLAY" else "PLAY"
                            audio.pause_music(game.state == "PAUSE")
                        elif game.state == "PLAY":
                            if event.key in (pg.K_UP, pg.K_x, pg.K_w):
                                game.rotate(1)
                            elif event.key == pg.K_z:
                                game.rotate(-1)
                            elif event.key == pg.K_SPACE:
                                game.hard_drop()

            if game.state == "MENU":
                game.menu_tick = (game.menu_tick + 1) % 3600
            game.update()
            render(canvas, game)

            # Aspect-ratio preserving integer/float scaling blit
            sw, sh = screen.get_size()
            factor = min(sw / WIDTH, sh / HEIGHT)
            if factor >= 1:
                factor = max(1, int(factor))

            out_w, out_h = int(WIDTH * factor), int(HEIGHT * factor)
            viewport = pg.Rect((sw - out_w) // 2, (sh - out_h) // 2, out_w, out_h)

            screen.fill(BLACK)
            screen.blit(pg.transform.scale(canvas, (out_w, out_h)), viewport)
            pg.display.flip()

    finally:
        audio.stop_all()
        pg.quit()


if __name__ == "__main__":
    main() 