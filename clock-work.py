#!/usr/bin/env python3
"""
Advanced Quiz - a themed, animated Tkinter trivia game (stdlib only).

Files created next to this script on first run:
    questions.json   local question bank (edit it freely!)
    highscores.json  top-5 leaderboard
    settings.json    remembers name / difficulty / theme

Optional icon files (silently ignored if missing): favicon.png, favicon.ico

made with curiosity at HUNRUTECH
"""
from __future__ import annotations

import html
import json
import math
import queue
import random
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = BASE_DIR / "questions.json"
SCORES_FILE = BASE_DIR / "highscores.json"
SETTINGS_FILE = BASE_DIR / "settings.json"

FONT_FAMILY = "Helvetica"
DIFFICULTIES = {"Easy": 20, "Medium": 15, "Hard": 8}  # seconds per question
QUESTION_COUNTS = [5, 10, 15]
LETTERS = "ABCD"
MAX_NAME_LEN = 16
ENABLE_FADE = True  # fade between screens (needs window-alpha support)

OPENTDB_URL = "https://opentdb.com/api.php"
OPENTDB_CATEGORY_IDS = {"History": 23, "Science": 17, "Pop Culture": 11}

THEMES = {
    "dark": {
        "bg": "#0f172a", "card": "#1e293b", "input": "#0f172a",
        "fg": "#f1f5f9", "muted": "#94a3b8", "border": "#334155",
        "accent": "#6366f1", "accent_hover": "#818cf8",
        "btn": "#334155", "btn_hover": "#475569", "btn_disabled": "#172033",
        "good": "#16a34a", "bad": "#dc2626", "warn": "#f59e0b",
        "good_text": "#4ade80", "bad_text": "#f87171",
    },
    "light": {
        "bg": "#f1f5f9", "card": "#ffffff", "input": "#f8fafc",
        "fg": "#0f172a", "muted": "#64748b", "border": "#cbd5e1",
        "accent": "#4f46e5", "accent_hover": "#6366f1",
        "btn": "#e2e8f0", "btn_hover": "#cbd5e1", "btn_disabled": "#e6ebf1",
        "good": "#16a34a", "bad": "#dc2626", "warn": "#d97706",
        "good_text": "#15803d", "bad_text": "#b91c1c",
    },
}


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
def lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly blend two #rrggbb colours."""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> bool:
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp.replace(path)
        return True
    except OSError:
        return False


def load_icon(root: tk.Tk) -> None:
    """Try a .png (iconphoto) first, then a .ico (iconbitmap); never crash."""
    png, ico = BASE_DIR / "favicon.png", BASE_DIR / "favicon.ico"
    if png.exists():
        try:
            img = tk.PhotoImage(file=str(png))
            root.iconphoto(True, img)
            root._icon_img = img  # keep a reference
            return
        except tk.TclError:
            pass
    if ico.exists():
        try:
            root.iconbitmap(str(ico))
        except tk.TclError:
            pass


# ----------------------------------------------------------------------------
# Data layer: questions, API, high scores
# ----------------------------------------------------------------------------
def _q(category, question, options, answer):
    return {"category": category, "question": question, "options": options, "answer": answer}


DEFAULT_QUESTIONS = [
    _q("History", "Who was the first democratically elected leader of the Russian Federation?",
       ["Boris Johnson", "Boris Yeltsin", "Mikhail Gorbachev"], 1),
    _q("Pop Culture", "What was the first Carry On film ever made?",
       ["Carry On Sergeant", "Carry On Cleo", "Carry On Doctor"], 0),
    _q("General", "Why did Tibetans grow long finger nails?",
       ["They're attention seekers.", "To pick noses efficiently.", "To scratch their back."], 2),
    _q("History", "Who signed the Magna Carta?", ["Henry III", "King John I", "Richard I"], 1),
    _q("General", "What sport was Fanny Chmelar recognized for competing in?",
       ["Long Jump", "Show Jumping", "Ski-ing"], 2),
    _q("History", "Which of these North Korean dictators ruled first?",
       ["Kim Il-Sung", "Kim Jong-Un", "Kim Jong-Il"], 0),
    _q("Pop Culture", "What was Shaun Ryder's autobiography called?",
       ["Twisting My Plums", "Twisting My Melon", "Twisting My Ankle"], 1),
    _q("General", "Bartolomeo Cristofori invented what?", ["The Car", "The Piano", "The Trumpet"], 1),
    _q("Science", "Which planet is known as the Red Planet?", ["Venus", "Mars", "Jupiter"], 1),
    _q("General", "What is the capital of Australia?", ["Sydney", "Canberra", "Melbourne"], 1),
    _q("Science", "What is the chemical symbol for gold?", ["Ag", "Au", "Ar"], 1),
    _q("Science", "How many bones does an adult human body have?", ["206", "186", "256"], 0),
    _q("Science", "Which planet in our solar system is the hottest?", ["Mercury", "Venus", "Mars"], 1),
    _q("Science", "Which gas do plants absorb for photosynthesis?",
       ["Oxygen", "Nitrogen", "Carbon dioxide"], 2),
    _q("Pop Culture", "Which actor played Tony Stark in the Marvel Cinematic Universe?",
       ["Chris Evans", "Robert Downey Jr.", "Mark Ruffalo"], 1),
    _q("Pop Culture", "Ringo Starr was the drummer of which band?",
       ["The Rolling Stones", "The Who", "The Beatles"], 2),
    _q("History", "Who was the first President of the United States?",
       ["Thomas Jefferson", "George Washington", "John Adams"], 1),
    _q("History", "In which year did the Berlin Wall fall?", ["1987", "1991", "1989"], 2),
    _q("History", "In which year was the Great Fire of London?", ["1666", "1566", "1766"], 0),
    _q("General", "Who painted the Mona Lisa?", ["Michelangelo", "Leonardo da Vinci", "Raphael"], 1),
    _q("General", "Which is the largest ocean on Earth?", ["Atlantic", "Indian", "Pacific"], 2),
]


class QuestionBank:
    @staticmethod
    def _valid(item) -> bool:
        return (
            isinstance(item, dict)
            and isinstance(item.get("question"), str)
            and isinstance(item.get("options"), list)
            and 2 <= len(item["options"]) <= 4
            and all(isinstance(o, str) for o in item["options"])
            and isinstance(item.get("answer"), int)
            and 0 <= item["answer"] < len(item["options"])
        )

    @classmethod
    def load_local(cls) -> list[dict]:
        if not QUESTIONS_FILE.exists():
            write_json(QUESTIONS_FILE, DEFAULT_QUESTIONS)
        raw = read_json(QUESTIONS_FILE, None)
        items = [i for i in raw if cls._valid(i)] if isinstance(raw, list) else []
        if not items:
            items = [dict(q) for q in DEFAULT_QUESTIONS]
        for i in items:
            i["category"] = str(i.get("category") or "General")
        return items

    @staticmethod
    def prepare(q: dict) -> dict:
        """Return a copy with shuffled options and a corrected answer index."""
        opts = list(q["options"])
        correct = opts[q["answer"]]
        random.shuffle(opts)
        return {"category": q.get("category", "General"), "question": q["question"],
                "options": opts, "answer": opts.index(correct)}

    @staticmethod
    def fetch_online(amount: int, category: str, difficulty: str) -> list[dict]:
        params = {"amount": min(max(amount, 1), 50), "type": "multiple",
                  "difficulty": difficulty.lower()}
        if category in OPENTDB_CATEGORY_IDS:
            params["category"] = OPENTDB_CATEGORY_IDS[category]
        url = OPENTDB_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "TkAdvancedQuiz/2.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("response_code") != 0 or not payload.get("results"):
            raise ValueError("API returned no questions")
        out = []
        for item in payload["results"]:
            correct = html.unescape(item["correct_answer"])
            options = [html.unescape(x) for x in item["incorrect_answers"]] + [correct]
            random.shuffle(options)
            out.append({"category": html.unescape(item.get("category", "Trivia")),
                        "question": html.unescape(item["question"]),
                        "options": options, "answer": options.index(correct)})
        return out


class HighScores:
    MAX = 5

    def __init__(self, path: Path):
        self.path = path
        data = read_json(path, [])
        self.entries = [e for e in data if isinstance(e, dict) and "score" in e] if isinstance(data, list) else []
        self._sort()

    def _sort(self):
        self.entries.sort(key=lambda e: (-int(e.get("score", 0)), str(e.get("date", ""))))
        self.entries = self.entries[: self.MAX]

    def add(self, entry: dict):
        """Add an entry; return its 0-based rank, or None if it didn't make the top 5."""
        self.entries.append(entry)
        self._sort()
        write_json(self.path, self.entries)
        for i, e in enumerate(self.entries):
            if e is entry:
                return i
        return None


# ----------------------------------------------------------------------------
# Custom widgets
# ----------------------------------------------------------------------------
class FancyButton(tk.Label):
    """
    A Label-based button. Real tk.Button ignores colours on macOS, so this keeps
    the look identical on Windows, macOS and Linux, and allows smooth hover fades.
    Modes: normal | selected | disabled | correct | wrong
    """

    def __init__(self, master, app, text, command, kind="secondary", font=None,
                 anchor="center", padx=16, pady=10):
        super().__init__(master, text=text, font=font or app.font(12, "bold"),
                         anchor=anchor, padx=padx, pady=pady, bd=0)
        self.app, self.command, self.kind = app, command, kind
        self.mode, self.hover = "normal", False
        self._cur, self._anim = None, None
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Destroy>", lambda e: self._cancel_fade())
        self.apply(animate=False)

    @property
    def interactive(self) -> bool:
        return self.mode in ("normal", "selected")

    def colors(self):
        t = self.app.t
        if self.mode == "correct":
            return t["good"], "#ffffff"
        if self.mode == "wrong":
            return t["bad"], "#ffffff"
        if self.mode == "disabled":
            return t["btn_disabled"], t["muted"]
        if self.mode == "selected" or self.kind == "primary":
            return (t["accent_hover"] if self.hover else t["accent"]), "#ffffff"
        return (t["btn_hover"] if self.hover else t["btn"]), t["fg"]

    def set_mode(self, mode, animate=True):
        self.mode = mode
        if not self.interactive:
            self.hover = False
        self.apply(animate)

    def apply(self, animate=True):
        bg, fg = self.colors()
        self.configure(fg=fg, cursor="hand2" if self.interactive else "arrow")
        if animate and self._cur and self._cur != bg:
            self._fade(self._cur, bg)
        else:
            self._cancel_fade()
            self._set_bg(bg)

    def _set_bg(self, color):
        self._cur = color
        self.configure(bg=color)

    def _cancel_fade(self):
        if self._anim is not None:
            try:
                self.after_cancel(self._anim)
            except tk.TclError:
                pass
            self._anim = None

    def _fade(self, c1, c2, steps=6, delay=14):
        self._cancel_fade()

        def step(i):
            try:
                self._set_bg(lerp_color(c1, c2, i / steps))
                if i < steps:
                    self._anim = self.after(delay, lambda: step(i + 1))
                else:
                    self._anim = None
            except tk.TclError:
                pass

        step(1)

    def _enter(self, _e):
        if self.interactive and not self.app.busy:
            self.hover = True
            self.apply(True)

    def _leave(self, _e):
        if self.hover:
            self.hover = False
            self.apply(True)

    def _press(self, _e):
        if self.interactive and not self.app.busy and self._cur:
            self._cancel_fade()
            self._set_bg(lerp_color(self._cur, "#000000", 0.18))

    def _release(self, e):
        if not self.interactive or self.app.busy:
            return
        inside = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        self.apply(animate=False)
        if inside and self.command:
            self.command()


class Banner(tk.Canvas):
    """Animated header: drifting bubbles, or falling confetti for celebrations."""
    CONFETTI = ["#f43f5e", "#f59e0b", "#22c55e", "#38bdf8", "#a78bfa", "#f472b6"]

    def __init__(self, master, app, title, subtitle="", mode="bubbles", height=130):
        super().__init__(master, height=height, bd=0, highlightthickness=0, bg=app.t["bg"])
        self._surface = "bg"
        self.app, self.mode, self.h = app, mode, height
        self.parts, self.frame_no, self.job = [], 0, None
        self.title_id = self.create_text(0, height * 0.42, text=title, font=app.font(30, "bold"))
        self.sub_id = self.create_text(0, height * 0.78, text=subtitle, font=app.font(12))
        for _ in range(16 if mode == "bubbles" else 70):
            if mode == "bubbles":
                p = {"x": random.random(), "y": random.uniform(0, height), "r": random.uniform(8, 30),
                     "v": random.uniform(0.3, 1.0), "ph": random.uniform(0, 6.28),
                     "tint": random.uniform(0.10, 0.30), "id": self.create_oval(0, 0, 0, 0, width=0)}
            else:
                p = {"x": random.random(), "y": random.uniform(-height, 0), "r": random.uniform(3, 6),
                     "v": random.uniform(1.5, 4.0), "ph": random.uniform(0, 6.28),
                     "id": self.create_rectangle(0, 0, 0, 0, width=0,
                                                 fill=random.choice(self.CONFETTI))}
            self.parts.append(p)
        self.bind("<Destroy>", self._on_destroy)
        self._tick()

    def _on_destroy(self, _e):
        if self.job is not None:
            try:
                self.after_cancel(self.job)
            except tk.TclError:
                pass

    def _tick(self):
        try:
            t, h = self.app.t, self.h
            w = max(self.winfo_width(), 600)
            self.configure(bg=t["bg"])
            self.itemconfigure(self.title_id, fill=t["fg"])
            self.itemconfigure(self.sub_id, fill=t["muted"])
            self.coords(self.title_id, w / 2, h * 0.42)
            self.coords(self.sub_id, w / 2, h * 0.78)
            self.frame_no += 1
            for p in self.parts:
                if self.mode == "bubbles":
                    p["y"] -= p["v"]
                    if p["y"] < -p["r"]:
                        p["y"], p["x"] = h + p["r"], random.random()
                    x = p["x"] * w + math.sin(self.frame_no / 40 + p["ph"]) * 12
                    self.coords(p["id"], x - p["r"], p["y"] - p["r"], x + p["r"], p["y"] + p["r"])
                    self.itemconfigure(p["id"], fill=lerp_color(t["bg"], t["accent"], p["tint"]))
                else:
                    p["y"] += p["v"]
                    if p["y"] > h + 10 and self.frame_no < 150:
                        p["y"] = random.uniform(-30, 0)  # keep raining for ~5 seconds
                    x = p["x"] * w + math.sin(self.frame_no / 12 + p["ph"]) * 18
                    self.coords(p["id"], x, p["y"], x + p["r"] * 2, p["y"] + p["r"])
            self.tag_raise(self.title_id)
            self.tag_raise(self.sub_id)
            self.job = self.after(33, self._tick)
        except tk.TclError:
            pass


class ScrollFrame(tk.Frame):
    """Vertically scrollable container; put children in `.inner`."""

    def __init__(self, master, app):
        super().__init__(master, bd=0, highlightthickness=0, bg=app.t["bg"])
        self._surface = "bg"
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, bg=app.t["bg"])
        self.canvas._surface = "bg"
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                 style="Quiz.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bd=0, highlightthickness=0, bg=app.t["bg"])
        self.inner._surface = "bg"
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        top = self.winfo_toplevel()
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            top.bind(seq, self._wheel, add="+")

    def _wheel(self, e):
        try:
            if getattr(e, "num", None) == 4:
                step = -1
            elif getattr(e, "num", None) == 5:
                step = 1
            else:
                step = -1 if e.delta > 0 else 1
            self.canvas.yview_scroll(step, "units")
        except tk.TclError:
            pass


# ----------------------------------------------------------------------------
# The application
# ----------------------------------------------------------------------------
class QuizApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Advanced Quiz")
        root.resizable(False, False)
        w = 780
        h = min(760, root.winfo_screenheight() - 90)
        root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+"
                      f"{max(10, (root.winfo_screenheight() - h) // 2 - 20)}")

        self.settings = read_json(SETTINGS_FILE, {})
        if not isinstance(self.settings, dict):
            self.settings = {}
        self.dark = bool(self.settings.get("dark", True))
        self.t = dict(THEMES["dark" if self.dark else "light"])
        self.local_questions = QuestionBank.load_local()
        self.scores = HighScores(SCORES_FILE)

        # menu selections
        self.difficulty = self.settings.get("difficulty")
        if self.difficulty not in DIFFICULTIES:
            self.difficulty = "Medium"
        self.n_questions = self.settings.get("count")
        if self.n_questions not in QUESTION_COUNTS:
            self.n_questions = 10
        self.use_api = bool(self.settings.get("use_api", False))
        self.player_name = str(self.settings.get("name", ""))[:MAX_NAME_LEN]
        self.name_var = tk.StringVar(value=self.player_name)
        self.name_var.trace_add("write", self._limit_name)
        self.category_var = tk.StringVar(value=str(self.settings.get("category", "All")))

        # runtime plumbing
        self.busy = False
        self.loading = False
        self._jobs: set = set()
        self.timer_id = None
        self.next_job = None
        self.screen = "menu"
        self.screen_frame = None
        self.review_win = None
        self.category_cb = None
        self.status_label = None
        self.start_btn = None
        self.fallback_note = ""
        self.time_limit = DIFFICULTIES[self.difficulty]
        self.reset_state()

        try:
            root.attributes("-alpha", 1.0)
            self.alpha_ok = True
        except tk.TclError:
            self.alpha_ok = False

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        root.configure(bg=self.t["bg"])
        self.configure_ttk()

        # persistent top bar with the theme toggle
        self.topbar = self.frame(root, "bg")
        self.topbar.pack(fill="x", padx=18, pady=(10, 0))
        self.label(self.topbar, "\u26A1 Advanced Quiz", 11, "bold", "muted").pack(side="left")
        self.theme_btn = FancyButton(self.topbar, self, "", self.toggle_theme, font=self.font(10, "bold"),
                                     padx=12, pady=5)
        self.theme_btn.pack(side="right")
        self._update_theme_btn()
        self.container = self.frame(root, "bg")
        self.container.pack(fill="both", expand=True)

        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_menu()

    # ------------------------------------------------------------------ state
    def reset_state(self):
        self.quiz: list[dict] = []
        self.index = 0
        self.correct = 0
        self.points = 0
        self.shown_points = 0
        self.streak = 0
        self.best_streak = 0
        self.missed: list[dict] = []
        self.lifeline_5050 = True
        self.lifeline_skip = True
        self.accepting = False
        self.awaiting_next = False
        self.removed: set = set()
        self.deadline = 0.0

    def save_settings(self):
        write_json(SETTINGS_FILE, {
            "dark": self.dark, "name": self.player_name, "difficulty": self.difficulty,
            "count": self.n_questions, "use_api": self.use_api, "category": self.category_var.get(),
        })

    def _limit_name(self, *_):
        v = self.name_var.get()
        if len(v) > MAX_NAME_LEN:
            self.name_var.set(v[:MAX_NAME_LEN])

    # ---------------------------------------------------------------- widgets
    @staticmethod
    def font(size, weight="normal"):
        return (FONT_FAMILY, size, weight)

    def frame(self, parent, surface="bg"):
        f = tk.Frame(parent, bd=0, highlightthickness=0, bg=self.t[surface])
        f._surface = surface
        return f

    def label(self, parent, text="", size=12, weight="normal", fg="fg", surface="bg", **kw):
        lbl = tk.Label(parent, text=text, font=self.font(size, weight), bd=0,
                       bg=self.t[surface], fg=self.t[fg], **kw)
        lbl._surface, lbl._fg = surface, fg
        return lbl

    def entry(self, parent, var):
        e = tk.Entry(parent, textvariable=var, font=self.font(13), relief="flat", bd=0,
                     highlightthickness=2)
        self._style_entry(e)
        return e

    def _style_entry(self, e):
        t = self.t
        e.configure(bg=t["input"], fg=t["fg"], insertbackground=t["fg"],
                    highlightbackground=t["border"], highlightcolor=t["accent"],
                    selectbackground=t["accent"], selectforeground="#ffffff")

    def chip_row(self, parent, options, selected, on_pick, surface="card"):
        """Segmented selector. options = [(key, label)]."""
        row = self.frame(parent, surface)
        buttons = {}

        def pick(key):
            for k, b in buttons.items():
                b.set_mode("selected" if k == key else "normal")
            on_pick(key)

        for key, text in options:
            b = FancyButton(row, self, text, lambda k=key: pick(k), padx=14, pady=7,
                            font=self.font(11, "bold"))
            b.pack(side="left", padx=(0, 8))
            b.set_mode("selected" if key == selected else "normal", animate=False)
            buttons[key] = b
        return row

    # ------------------------------------------------------------------ theme
    def configure_ttk(self):
        t, s = self.t, self.style
        s.configure("Quiz.Horizontal.TProgressbar", troughcolor=t["btn"], background=t["accent"],
                    bordercolor=t["bg"], lightcolor=t["accent"], darkcolor=t["accent"], thickness=10)
        s.configure("Quiz.Vertical.TScrollbar", background=t["btn_hover"], troughcolor=t["bg"],
                    bordercolor=t["bg"], arrowcolor=t["fg"], lightcolor=t["btn_hover"],
                    darkcolor=t["btn_hover"])
        s.configure("Quiz.TCombobox", fieldbackground=t["input"], background=t["btn"],
                    foreground=t["fg"], arrowcolor=t["fg"], bordercolor=t["border"],
                    lightcolor=t["input"], darkcolor=t["input"], selectbackground=t["input"],
                    selectforeground=t["fg"], padding=6)
        s.map("Quiz.TCombobox",
              fieldbackground=[("readonly", t["input"])], foreground=[("readonly", t["fg"])],
              selectbackground=[("readonly", t["input"])], selectforeground=[("readonly", t["fg"])])

    def _fix_combobox_popdown(self):
        t = self.t
        for opt, val in (("background", t["input"]), ("foreground", t["fg"]),
                         ("selectBackground", t["accent"]), ("selectForeground", "#ffffff")):
            self.root.option_add(f"*TCombobox*Listbox.{opt}", val)
        if self.category_cb is not None:
            try:
                pop = self.root.tk.call("ttk::combobox::PopdownWindow", str(self.category_cb))
                self.root.tk.call(f"{pop}.f.l", "configure", "-background", t["input"],
                                  "-foreground", t["fg"], "-selectbackground", t["accent"],
                                  "-selectforeground", "#ffffff")
            except tk.TclError:
                pass

    def _restyle(self, w):
        t = self.t
        if isinstance(w, FancyButton):
            w.apply(animate=False)
        elif isinstance(w, tk.Entry):
            self._style_entry(w)
        elif hasattr(w, "_surface"):
            bg = t[w._surface]
            if isinstance(w, tk.Label):
                w.configure(bg=bg, fg=t[w._fg])
            else:
                w.configure(bg=bg)
        for child in w.winfo_children():
            self._restyle(child)

    def apply_theme(self):
        self.root.configure(bg=self.t["bg"])
        self.configure_ttk()
        self._fix_combobox_popdown()
        self._restyle(self.root)
        if self.review_win is not None:
            try:
                if self.review_win.winfo_exists():
                    self.review_win.configure(bg=self.t["bg"])
                    self._restyle(self.review_win)
            except tk.TclError:
                pass
        if self.screen == "quiz":
            self._redraw_timer()

    def _update_theme_btn(self):
        self.theme_btn.configure(text="\u2600  Light mode" if self.dark else "\u263E  Dark mode")

    def toggle_theme(self):
        old = dict(self.t)
        self.dark = not self.dark
        new = THEMES["dark" if self.dark else "light"]
        self._update_theme_btn()
        steps = 8

        def step(i):
            self.t = dict(new) if i >= steps else {k: lerp_color(old[k], new[k], i / steps) for k in new}
            self.apply_theme()
            if i < steps:
                self.root.after(20, lambda: step(i + 1))
            else:
                self.save_settings()

        step(1)

    # -------------------------------------------------------- job management
    def later(self, ms, fn):
        job = None

        def run():
            self._jobs.discard(job)
            fn()

        job = self.root.after(ms, run)
        self._jobs.add(job)
        return job

    def cancel_jobs(self):
        for j in list(self._jobs):
            try:
                self.root.after_cancel(j)
            except tk.TclError:
                pass
        self._jobs.clear()
        self.next_job = None

    def cancel_timer(self):
        if self.timer_id is not None:
            try:
                self.root.after_cancel(self.timer_id)
            except tk.TclError:
                pass
            self.timer_id = None

    # ------------------------------------------------------------ transitions
    def new_screen(self):
        self.screen_frame = self.frame(self.container, "bg")
        self.screen_frame.pack(fill="both", expand=True)
        return self.screen_frame

    def _set_alpha(self, a):
        try:
            self.root.attributes("-alpha", a)
        except tk.TclError:
            pass

    def close_review(self):
        if self.review_win is not None:
            try:
                self.review_win.destroy()
            except tk.TclError:
                pass
            self.review_win = None

    def transition(self, builder):
        """Fade out, swap the screen, fade back in."""
        self.cancel_jobs()
        self.cancel_timer()
        self.busy = True

        def swap():
            self.close_review()
            if self.screen_frame is not None:
                self.screen_frame.destroy()
                self.screen_frame = None
            builder()

        if not (ENABLE_FADE and self.alpha_ok):
            try:
                swap()
            finally:
                self.busy = False
            return
        steps = 5

        def fade_out(i=0):
            self._set_alpha(1 - 0.85 * i / steps)
            if i < steps:
                self.root.after(14, lambda: fade_out(i + 1))
            else:
                try:
                    swap()
                except Exception:
                    self.busy = False
                    self._set_alpha(1.0)
                    raise
                fade_in(0)

        def fade_in(i):
            self._set_alpha(0.15 + 0.85 * i / steps)
            if i < steps:
                self.root.after(14, lambda: fade_in(i + 1))
            else:
                self.busy = False

        fade_out()

    # --------------------------------------------------------- small effects
    def count_up(self, lbl, start, target, fmt="{}", duration=900):
        steps = max(1, duration // 30)

        def step(i):
            ease = 1 - (1 - i / steps) ** 3
            lbl.configure(text=fmt.format(int(start + (target - start) * ease)))
            if i < steps:
                self.later(30, lambda: step(i + 1))

        step(0)

    def pop(self, widget, base, weight="bold", extra=(6, 4, 2, 1, 0)):
        def step(i):
            widget.configure(font=self.font(base + extra[i], weight))
            if i + 1 < len(extra):
                self.later(35, lambda: step(i + 1))

        step(0)

    def shake(self, btn):
        offsets = [12, -12, 9, -9, 5, -5, 2, 0]

        def step(i):
            o = offsets[i] if i < len(offsets) else 0
            try:
                btn.pack_configure(padx=(max(o, 0), max(-o, 0)))
            except tk.TclError:
                return
            if i < len(offsets):
                self.later(28, lambda: step(i + 1))

        step(0)

    def slide_in(self, btn, text, delay):
        def start():
            btn.configure(text=text)
            self._slide(btn, 0)

        self.later(delay, start)

    def _slide(self, btn, step, steps=8):
        ease = 1 - (1 - step / steps) ** 3
        try:
            btn.pack_configure(padx=(int(90 * (1 - ease)), 0))
        except tk.TclError:
            return
        if step < steps:
            self.later(16, lambda: self._slide(btn, step + 1))

    def score_badge(self, btn, text):
        """A '+150' badge that pops out of the correct answer."""
        badge = tk.Label(self.screen_frame, text=text, font=self.font(13, "bold"), bd=0, padx=8, pady=2,
                         bg=self.t["btn_disabled"], fg=self.t["warn"])
        frames = 28

        def step(i):
            lift = int(18 * (1 - (1 - min(i, 14) / 14) ** 3))
            badge.place(in_=btn, relx=1.0, x=-14, y=-lift, rely=0.5, anchor="e")
            if i < frames:
                self.later(30, lambda: step(i + 1))
            else:
                badge.destroy()

        step(0)

    def pulse_label(self, lbl, a="warn", b="fg"):
        def step():
            k = (math.sin(time.monotonic() * 4) + 1) / 2
            lbl.configure(fg=lerp_color(self.t[a], self.t[b], k * 0.6))
            self.later(50, step)

        step()

    # ---------------------------------------------------------------- keyboard
    KEYMAP = {"a": 0, "b": 1, "c": 2, "d": 3, "1": 0, "2": 1, "3": 2, "4": 3}

    def on_key(self, e):
        if self.busy:
            return
        if self.screen == "menu":
            if e.keysym in ("Return", "KP_Enter"):
                self.on_start()
            return
        if self.screen != "quiz":
            return
        if e.keysym == "Escape":
            self.confirm_quit()
            return
        if e.keysym in ("Return", "KP_Enter", "space") and self.awaiting_next:
            self.next_question()
            return
        ch = (e.char or "").lower()
        if ch in self.KEYMAP:
            idx = self.KEYMAP[ch]
            if self.quiz and idx < len(self.quiz[self.index]["options"]):
                self.check_answer(idx)
        elif ch == "f":
            self.use_5050()
        elif ch == "s":
            self.skip_question()

    def on_close(self):
        self.cancel_jobs()
        self.cancel_timer()
        self.root.destroy()

    # ------------------------------------------------------------- menu screen
    def build_menu(self):
        self.screen = "menu"
        self.category_cb = None
        s = self.new_screen()
        Banner(s, self, "Advanced Quiz", "Pick your challenge and beat the clock").pack(fill="x")

        card = self.frame(s, "card")
        card.pack(fill="x", padx=40, pady=(6, 0))
        inner = self.frame(card, "card")
        inner.pack(fill="x", padx=26, pady=(8, 20))

        def caption(text):
            self.label(inner, text, 10, "bold", "muted", "card").pack(anchor="w", pady=(12, 4))

        caption("YOUR NAME")
        name_entry = self.entry(inner, self.name_var)
        name_entry.pack(fill="x", ipady=7)

        caption("CATEGORY")
        cats = sorted({q["category"] for q in self.local_questions} | set(OPENTDB_CATEGORY_IDS))
        values = ["All"] + cats
        if self.category_var.get() not in values:
            self.category_var.set("All")
        cb = ttk.Combobox(inner, textvariable=self.category_var, values=values, state="readonly",
                          style="Quiz.TCombobox", font=self.font(12))
        cb.bind("<<ComboboxSelected>>", lambda e: cb.selection_clear())
        cb.pack(fill="x")
        self.category_cb = cb
        self._fix_combobox_popdown()

        caption("DIFFICULTY  (time per question)")
        self.chip_row(inner, [(k, f"{k}  \u00B7  {v}s") for k, v in DIFFICULTIES.items()],
                      self.difficulty, self._set_difficulty).pack(anchor="w")

        caption("NUMBER OF QUESTIONS")
        self.chip_row(inner, [(n, str(n)) for n in QUESTION_COUNTS],
                      self.n_questions, self._set_count).pack(anchor="w")

        caption("QUESTION SOURCE")
        self.api_btn = FancyButton(inner, self, "", self._toggle_api, anchor="w",
                                   font=self.font(11, "bold"), padx=14, pady=7)
        self.api_btn.pack(anchor="w")
        self._refresh_api_btn(animate=False)

        self.start_btn = FancyButton(inner, self, "Start Quiz   \u2192", self.on_start, kind="primary",
                                     font=self.font(15, "bold"), pady=13)
        self.start_btn.pack(fill="x", pady=(22, 0))
        self.status_label = self.label(inner, "", 11, "normal", "muted", "card")
        self.status_label.pack(pady=(8, 0))

        best = self.scores.entries[0] if self.scores.entries else None
        if best:
            self.label(s, f"\u2605 Best score: {best['score']} pts by {best.get('name', '?')}",
                       11, "bold", "warn").pack(pady=(12, 0))
        self.label(s, "Keys:  A\u2013D / 1\u20134 answer   \u00B7   F = 50/50   \u00B7   S = skip   \u00B7   "
                      "Enter = next   \u00B7   Esc = menu", 10, "normal", "muted").pack(pady=(6, 0))
        name_entry.focus_set()
        name_entry.icursor("end")

    def _set_difficulty(self, key):
        self.difficulty = key

    def _set_count(self, key):
        self.n_questions = key

    def _toggle_api(self):
        self.use_api = not self.use_api
        self._refresh_api_btn()

    def _refresh_api_btn(self, animate=True):
        self.api_btn.configure(text=("\u25C9" if self.use_api else "\u25CB") +
                               "   Live trivia from Open Trivia DB (falls back to local if offline)")
        self.api_btn.set_mode("selected" if self.use_api else "normal", animate)

    def set_status(self, text):
        try:
            self.status_label.configure(text=text)
        except (AttributeError, tk.TclError):
            pass

    def on_start(self):
        if self.busy or self.loading:
            return
        self.player_name = self.name_var.get().strip() or "Player"
        self.save_settings()
        try:
            self.start_btn.set_mode("disabled")
        except (AttributeError, tk.TclError):
            pass
        self.launch_quiz(self.set_status)

    # ------------------------------------------------------- starting a quiz
    def launch_quiz(self, status_cb=None):
        """Fetch/choose questions according to the current selections, then start."""
        if self.loading:
            return
        self.time_limit = DIFFICULTIES[self.difficulty]
        self.fallback_note = ""
        if not self.use_api:
            self._begin_local()
            return
        self.loading = True
        q: queue.Queue = queue.Queue()
        category = self.category_var.get()

        def worker():
            try:
                q.put(("ok", QuestionBank.fetch_online(self.n_questions, category, self.difficulty)))
            except Exception as exc:  # network, timeout, bad JSON, rate limit ...
                q.put(("err", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        tick = [0]

        def poll():
            try:
                kind, data = q.get_nowait()
            except queue.Empty:
                tick[0] += 1
                if status_cb:
                    status_cb("Fetching live questions" + "." * (tick[0] % 4))
                self.later(150, poll)
                return
            self.loading = False
            if kind == "ok" and data:
                self._start_with(data)
            else:
                self.fallback_note = "Offline - using the local question bank."
                self._begin_local()

        poll()

    def _begin_local(self):
        cat = self.category_var.get()
        pool = [q for q in self.local_questions if cat == "All" or q["category"] == cat]
        if not pool:
            pool = list(self.local_questions)
        self._start_with(random.sample(pool, min(self.n_questions, len(pool))))

    def _start_with(self, questions):
        self.reset_state()
        self.quiz = [QuestionBank.prepare(q) for q in questions]
        self.transition(self.build_quiz)

    def restart_quiz(self, button=None):
        """Clean restart: new state + freshly built UI, no recursive __init__."""
        cb = (lambda text: button.configure(text=text)) if button is not None else None
        self.launch_quiz(cb)

    def go_menu(self):
        self.reset_state()
        self.transition(self.build_menu)

    # ------------------------------------------------------------ quiz screen
    def build_quiz(self):
        self.screen = "quiz"
        s = self.new_screen()
        body = self.frame(s, "bg")
        body.pack(fill="both", expand=True, padx=40, pady=(14, 10))

        top = self.frame(body, "bg")
        top.pack(fill="x")
        self.progress_label = self.label(top, "", 11, "bold", "muted")
        self.progress_label.pack(side="left")
        self.category_label = self.label(top, "", 11, "bold", "accent")
        self.category_label.pack(side="right")
        self.progress = ttk.Progressbar(body, style="Quiz.Horizontal.TProgressbar",
                                        maximum=len(self.quiz) * 100, value=self.index * 100)
        self.progress.pack(fill="x", pady=(6, 12))

        stat = self.frame(body, "bg")
        stat.pack(fill="x")
        for c in range(3):
            stat.columnconfigure(c, weight=1, uniform="stat")
        self.score_label = self.label(stat, f"Score: {self.shown_points}", 14, "bold")
        self.score_label.grid(row=0, column=0, sticky="w")
        self.streak_label = self.label(stat, "", 12, "bold", "warn")
        self.streak_label.grid(row=0, column=1)
        self.timer_label = self.label(stat, "", 14, "bold")
        self.timer_label.grid(row=0, column=2, sticky="e")

        self.timer_canvas = tk.Canvas(body, height=8, bd=0, highlightthickness=0, bg=self.t["btn"])
        self.timer_canvas._surface = "btn"
        self.timer_canvas.pack(fill="x", pady=(6, 12))
        self.timer_bar = self.timer_canvas.create_rectangle(0, 0, 0, 8, width=0, fill=self.t["good"])
        self._timer_frac = 1.0

        qcard = self.frame(body, "card")
        qcard.pack(fill="x")
        self.question_label = self.label(qcard, "", 17, "bold", "fg", "card", wraplength=620,
                                         justify="left", anchor="nw", height=4)
        self.question_label.pack(fill="x", padx=22, pady=18)

        self.answers_frame = self.frame(body, "bg")
        self.answers_frame.pack(fill="x", pady=(14, 0))
        self.answer_btns = [
            FancyButton(self.answers_frame, self, "", lambda i=i: self.check_answer(i), anchor="w",
                        padx=20, pady=11, font=self.font(13))
            for i in range(4)
        ]

        row = self.frame(body, "bg")
        row.pack(fill="x", pady=(12, 0))
        small = self.font(11, "bold")
        self.btn_5050 = FancyButton(row, self, "50/50  (F)", self.use_5050, padx=14, pady=7, font=small)
        self.btn_5050.pack(side="left")
        self.btn_skip = FancyButton(row, self, "Skip  (S)", self.skip_question, padx=14, pady=7, font=small)
        self.btn_skip.pack(side="left", padx=8)
        FancyButton(row, self, "Menu  (Esc)", self.confirm_quit, padx=14, pady=7,
                    font=small).pack(side="right")

        self.feedback = self.label(body, "", 13, "bold", "muted")
        self.feedback.pack(pady=(12, 0))
        self.show_question()

    def _redraw_timer(self):
        try:
            self.draw_timer(self._timer_frac * self.time_limit)
        except (AttributeError, tk.TclError):
            pass

    def draw_timer(self, remaining):
        frac = max(0.0, min(1.0, remaining / self.time_limit))
        self._timer_frac = frac
        t = self.t
        color = (lerp_color(t["warn"], t["good"], (frac - 0.5) / 0.5) if frac > 0.5
                 else lerp_color(t["bad"], t["warn"], frac / 0.5))
        w = max(self.timer_canvas.winfo_width(), 1)
        self.timer_canvas.coords(self.timer_bar, 0, 0, w * frac, 8)
        self.timer_canvas.itemconfigure(self.timer_bar, fill=color)
        secs = math.ceil(remaining)
        self.timer_label.configure(text=f"{secs}s", fg=t["bad_text"] if secs <= 3 else t["fg"])

    def update_streak_label(self):
        if self.streak >= 1:
            mult = 1 + 0.25 * min(self.streak, 4)
            self.streak_label.configure(text=f"\u2605 Streak {self.streak}  (\u00D7{mult:g} bonus)")
            self.pop(self.streak_label, 12)
        else:
            self.streak_label.configure(text="")

    def refresh_lifelines(self):
        self.btn_5050.configure(text="50/50  (F)" if self.lifeline_5050 else "50/50  used")
        self.btn_5050.set_mode("normal" if self.lifeline_5050 else "disabled", animate=False)
        self.btn_skip.configure(text="Skip  (S)" if self.lifeline_skip else "Skip  used")
        self.btn_skip.set_mode("normal" if self.lifeline_skip else "disabled", animate=False)

    def show_question(self):
        self.cancel_timer()
        if self.index >= len(self.quiz):
            self.finish_quiz()
            return
        q = self.quiz[self.index]
        self.accepting = False
        self.removed = set()
        self.progress_label.configure(text=f"Question {self.index + 1} of {len(self.quiz)}")
        self.category_label.configure(text=q["category"].upper())
        note = self.fallback_note if self.index == 0 else ""
        self.feedback.configure(text=note, fg=self.t["muted"])
        self.feedback._fg = "muted"
        self.draw_timer(self.time_limit)
        self.refresh_lifelines()

        for b in self.answer_btns:
            b.pack_forget()
        for i, _ in enumerate(q["options"]):
            b = self.answer_btns[i]
            b.configure(text=" ", font=self.font(13))
            b.set_mode("normal", animate=False)
            b.pack(fill="x", pady=5, padx=(90, 0))

        self.question_label.configure(text="")
        self._typewriter(q["question"], 0)

    def _typewriter(self, text, i):
        if i >= len(text):
            self.question_label.configure(text=text)
            self._reveal_options()
            return
        self.question_label.configure(text=text[:i])
        self.later(14, lambda: self._typewriter(text, i + (2 if len(text) > 80 else 1)))

    def _reveal_options(self):
        q = self.quiz[self.index]
        for i, opt in enumerate(q["options"]):
            self.slide_in(self.answer_btns[i], f"{LETTERS[i]}   {opt}", 70 * i)
        self.later(70 * len(q["options"]) + 150, self.start_timer)

    def start_timer(self):
        self.accepting = True
        self.deadline = time.monotonic() + self.time_limit
        self.tick()

    def tick(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            self.draw_timer(0)
            self.check_answer(None)
            return
        self.draw_timer(remaining)
        self.timer_id = self.root.after(50, self.tick)

    # ----------------------------------------------------------------- answers
    def check_answer(self, selected):
        if not self.accepting or (selected is not None and selected in self.removed):
            return
        self.accepting = False
        self.cancel_timer()  # stop the countdown during the reveal delay

        q = self.quiz[self.index]
        correct = q["answer"]
        remaining = max(0.0, self.deadline - time.monotonic()) if selected is not None else 0.0

        if selected == correct:
            mult = 1 + 0.25 * min(self.streak, 4)
            gained = int(round((100 + int(50 * remaining / self.time_limit)) * mult))
            self.points += gained
            self.correct += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            msg, key = "Correct!", "good_text"
            badge = f"+{gained}" + (f"  \u00D7{mult:g}" if mult > 1 else "")
        else:
            self.streak = 0
            msg, key, badge = ("Time's up!" if selected is None else "Not quite!"), "bad_text", None
            self.missed.append({
                "number": self.index + 1, "category": q["category"], "question": q["question"],
                "your": "No answer (time ran out)" if selected is None else q["options"][selected],
                "correct": q["options"][correct]})

        for i in range(len(q["options"])):
            b = self.answer_btns[i]
            if i == correct:
                b.set_mode("correct")
                self.pop(b, 13, "normal", (3, 2, 1, 0))
                if badge:
                    self.score_badge(b, badge)
            elif i == selected:
                b.set_mode("wrong")
                self.shake(b)
            elif i not in self.removed:
                b.set_mode("disabled")
        self.feedback.configure(text=msg, fg=self.t[key])
        self.feedback._fg = key
        self._after_answer()

    def _after_answer(self):
        self.refresh_lifelines()
        self.btn_5050.set_mode("disabled", animate=False)
        self.btn_skip.set_mode("disabled", animate=False)
        self.count_up(self.score_label, self.shown_points, self.points, "Score: {}", 420)
        self.pop(self.score_label, 14)
        self.shown_points = self.points
        self.update_streak_label()
        self.animate_progress((self.index + 1) * 100)
        self.awaiting_next = True
        self.next_job = self.later(1600, self.next_question)

    def next_question(self):
        if not self.awaiting_next:
            return
        if self.next_job is not None:
            try:
                self.root.after_cancel(self.next_job)
            except tk.TclError:
                pass
            self._jobs.discard(self.next_job)
            self.next_job = None
        self.awaiting_next = False
        self.index += 1
        self.show_question()

    def animate_progress(self, target):
        def step():
            cur = float(self.progress["value"])
            if abs(target - cur) < 1:
                self.progress["value"] = target
                return
            self.progress["value"] = cur + (target - cur) * 0.25
            self.later(16, step)

        step()

    # --------------------------------------------------------------- lifelines
    def use_5050(self):
        if not (self.accepting and self.lifeline_5050):
            return
        q = self.quiz[self.index]
        wrong = [i for i in range(len(q["options"])) if i != q["answer"]]
        self.removed = set(random.sample(wrong, len(q["options"]) // 2))
        for i in self.removed:
            self.answer_btns[i].configure(text=f"{LETTERS[i]}   \u2715")
            self.answer_btns[i].set_mode("disabled")
        self.lifeline_5050 = False
        self.refresh_lifelines()

    def skip_question(self):
        if not (self.accepting and self.lifeline_skip):
            return
        self.accepting = False
        self.cancel_timer()
        self.lifeline_skip = False
        q = self.quiz[self.index]
        self.missed.append({"number": self.index + 1, "category": q["category"],
                            "question": q["question"], "your": "Skipped",
                            "correct": q["options"][q["answer"]]})
        for i in range(len(q["options"])):
            if i == q["answer"]:
                self.answer_btns[i].set_mode("correct")
            elif i not in self.removed:
                self.answer_btns[i].set_mode("disabled")
        self.feedback.configure(text="Skipped - no points, streak kept", fg=self.t["warn"])
        self.feedback._fg = "warn"
        self._after_answer()

    def confirm_quit(self):
        paused = None
        if self.accepting and self.timer_id is not None:
            paused = self.deadline - time.monotonic()
            self.cancel_timer()
        if messagebox.askyesno("Back to menu", "Leave this quiz and return to the main menu?",
                               parent=self.root):
            self.go_menu()
        elif paused is not None:
            self.deadline = time.monotonic() + paused
            self.tick()

    # ------------------------------------------------------------- end screen
    def finish_quiz(self):
        entry = {"name": self.player_name, "score": self.points, "correct": self.correct,
                 "total": len(self.quiz), "difficulty": self.difficulty,
                 "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
        rank = self.scores.add(entry)
        self.transition(lambda: self.build_end(rank))

    def build_end(self, rank):
        self.screen = "end"
        s = self.new_screen()
        total = len(self.quiz)
        pct = self.correct / total if total else 0
        if pct == 1:
            title = "Perfect score!"
        elif pct >= 0.7:
            title = "Great job!"
        elif pct >= 0.4:
            title = "Nice effort!"
        else:
            title = "Keep practicing!"
        celebrate = pct >= 0.7 or rank is not None
        Banner(s, self, title, f"{self.player_name}  \u00B7  {self.difficulty}  \u00B7  "
                              f"{self.category_var.get()}",
               mode="confetti" if celebrate else "bubbles", height=120).pack(fill="x")

        card = self.frame(s, "card")
        card.pack(fill="x", padx=40, pady=(6, 0))
        inner = self.frame(card, "card")
        inner.pack(fill="x", padx=20, pady=14)
        stats = [("Points", None), ("Correct", f"{self.correct}/{total}"),
                 ("Accuracy", f"{round(pct * 100)}%"), ("Best streak", str(self.best_streak))]
        for c, (cap, val) in enumerate(stats):
            inner.columnconfigure(c, weight=1, uniform="end")
            big = self.label(inner, val or "0", 24, "bold", "fg", "card")
            big.grid(row=0, column=c)
            self.label(inner, cap, 10, "normal", "muted", "card").grid(row=1, column=c)
            if val is None:
                self.count_up(big, 0, self.points, "{}", 1000)

        if rank is not None:
            badge = self.label(s, f"\u2605  New high score!  Rank #{rank + 1}  \u2605", 13, "bold", "warn")
            badge.pack(pady=(10, 0))
            self.pulse_label(badge)

        board = self.frame(s, "card")
        board.pack(fill="x", padx=40, pady=(10, 0))
        binner = self.frame(board, "card")
        binner.pack(fill="x", padx=20, pady=12)
        self.label(binner, "LEADERBOARD  \u00B7  TOP 5", 10, "bold", "muted", "card").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))
        heads = ["#", "Player", "Score", "Level", "Date"]
        for c, h in enumerate(heads):
            self.label(binner, h, 10, "bold", "muted", "card").grid(row=1, column=c, sticky="w", padx=6)
        binner.columnconfigure(1, weight=1)
        if not self.scores.entries:
            self.label(binner, "No scores yet", 11, "normal", "muted", "card").grid(row=2, column=0, columnspan=5)
        for r, e in enumerate(self.scores.entries):
            key = "accent" if r == rank else "fg"
            weight = "bold" if r == rank else "normal"
            cells = [str(r + 1), str(e.get("name", "?")), str(e.get("score", 0)),
                     str(e.get("difficulty", "")), str(e.get("date", ""))[:10]]
            for c, text in enumerate(cells):
                self.label(binner, text, 11, weight, key, "card").grid(
                    row=r + 2, column=c, sticky="w", padx=6, pady=1)

        row = self.frame(s, "bg")
        row.pack(fill="x", padx=40, pady=(14, 0))
        for c in range(4):
            row.columnconfigure(c, weight=1, uniform="btn")
        again = FancyButton(row, self, "Play Again", lambda: self.restart_quiz(again), kind="primary")
        again.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        review = FancyButton(row, self, "Review Missed", self.open_review)
        review.grid(row=0, column=1, sticky="ew", padx=6)
        if not self.missed:
            review.configure(text="Nothing missed!")
            review.set_mode("disabled", animate=False)
        FancyButton(row, self, "Main Menu", self.go_menu).grid(row=0, column=2, sticky="ew", padx=6)
        FancyButton(row, self, "Exit", self.on_close).grid(row=0, column=3, sticky="ew", padx=(6, 0))

    def open_review(self):
        if not self.missed:
            return
        if self.review_win is not None:
            try:
                if self.review_win.winfo_exists():
                    self.review_win.lift()
                    return
            except tk.TclError:
                pass
        win = tk.Toplevel(self.root)
        self.review_win = win
        win.title("Review Missed Questions")
        win.geometry("640x560")
        win.configure(bg=self.t["bg"])
        win.transient(self.root)
        self.label(win, f"Missed questions ({len(self.missed)})", 16, "bold").pack(
            anchor="w", padx=24, pady=(18, 8))
        sf = ScrollFrame(win, self)
        sf.pack(fill="both", expand=True, padx=(24, 12), pady=(0, 12))
        for m in self.missed:
            card = self.frame(sf.inner, "card")
            card.pack(fill="x", pady=6, padx=(0, 12))
            self.label(card, f"Q{m['number']}  \u00B7  {m['category']}", 10, "bold", "accent", "card").pack(
                anchor="w", padx=16, pady=(12, 2))
            self.label(card, m["question"], 13, "bold", "fg", "card", wraplength=500,
                       justify="left").pack(anchor="w", padx=16)
            self.label(card, f"Your answer:  {m['your']}", 12, "normal", "bad_text", "card",
                       wraplength=500, justify="left").pack(anchor="w", padx=16, pady=(8, 0))
            self.label(card, f"Correct answer:  {m['correct']}", 12, "normal", "good_text", "card",
                       wraplength=500, justify="left").pack(anchor="w", padx=16, pady=(2, 12))
        FancyButton(win, self, "Close", win.destroy, kind="primary", pady=8).pack(
            fill="x", padx=24, pady=(0, 16))


# ----------------------------------------------------------------------------
def main():
    try:  # crisp text on high-DPI Windows displays
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    load_icon(root)
    QuizApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
