import json
import os
import queue
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

VERSION = "1.0.0"
DEFAULT_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
BG, PANEL, ALT = "#0b0f17", "#121927", "#0e1623"
BORDER, TEXT, MUTED = "#29364b", "#f2f5fb", "#8d9bb1"
RED, GREEN, YELLOW = "#f0526c", "#6ce0ae", "#ffcb72"


@dataclass
class Subtitle:
    number: str
    timing: str
    original: str
    translated: str = ""


def parse_srt(raw):
    raw = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    time_re = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
    result = []
    for block in re.split(r"\n[ \t]*\n+", raw.strip()):
        lines = block.split("\n")
        pos = next((i for i, line in enumerate(lines) if time_re.search(line)), None)
        if pos is None or pos + 1 >= len(lines):
            continue
        number = lines[pos - 1].strip() if pos else str(len(result) + 1)
        if not number.isdigit():
            number = str(len(result) + 1)
        body = "\n".join(lines[pos + 1:]).strip()
        if body:
            result.append(Subtitle(number, lines[pos].strip(), body))
    if not result:
        raise ValueError("No valid SRT subtitle entries were found.")
    return result


def parse_json_response(value):
    value = value.strip()
    fence = chr(96) * 3
    value = value.replace(fence + "json", "").replace(fence, "").strip()
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The translation model did not return valid JSON.")
        data = json.loads(value[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Unexpected translation response.")
    return data


class HadocSub:
    def __init__(self, root):
        self.root = root
        root.title("HADOC Sub — Sinhala Subtitle Translator")
        root.geometry("1180x780")
        root.minsize(950, 640)
        root.configure(bg=BG)
        self.items = []
        self.source_path = None
        self.selected = None
        self.busy = False
        self.events = queue.Queue()
        self.settings_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "HADOC-Sub" / "settings.json"
        self.api_url = tk.StringVar(value=DEFAULT_URL)
        self.model = tk.StringVar(value=DEFAULT_MODEL)
        self.api_key = tk.StringVar()
        self.file_name = tk.StringVar(value="No subtitle file loaded")
        self.count = tk.StringVar(value="0")
        self.done = tk.StringVar(value="0%")
        self.progress_text = tk.StringVar(value="Ready • Open an English SRT file")
        self.filter_text = tk.StringVar()
        self.reveal_key = False
        self.load_settings()
        self.setup_styles()
        self.build_ui()
        root.after(120, self.poll_events)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=ALT, fieldbackground=ALT, foreground=TEXT,
                        rowheight=36, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#1b2637", foreground="#b9c5d8",
                        relief="flat", borderwidth=0, font=("Segoe UI", 8, "bold"), padding=9)
        style.map("Treeview", background=[("selected", "#563042")], foreground=[("selected", "white")])
        style.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=RED,
                        bordercolor=BORDER, lightcolor=RED, darkcolor=RED)

    def load_settings(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            self.api_url.set(data.get("api_url", DEFAULT_URL))
            self.model.set(data.get("model", DEFAULT_MODEL))
        except (OSError, ValueError, TypeError):
            pass

    def save_settings(self):
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps({
                "api_url": self.api_url.get().strip(), "model": self.model.get().strip()
            }, indent=2), encoding="utf-8")
        except OSError:
            pass

    def label(self, parent, text, color=MUTED, size=9, bold=False, **kwargs):
        bg = kwargs.pop("bg", parent.cget("bg"))
        return tk.Label(parent, text=text, bg=bg, fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def button(self, parent, text, command, primary=False, compact=False):
        return tk.Button(parent, text=text, command=command,
                         bg=RED if primary else "#202d40",
                         fg="white" if primary else "#dce5f3",
                         activebackground="#ff6c82" if primary else "#304057",
                         activeforeground="white", relief="flat", bd=0,
                         padx=14 if compact else 17, pady=8 if compact else 11,
                         font=("Segoe UI", 9, "bold"), cursor="hand2")

    def field(self, parent, variable, show=None):
        return tk.Entry(parent, textvariable=variable, bg="#0a111b", fg=TEXT,
                        insertbackground=TEXT, relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=RED, font=("Segoe UI", 9), show=show)

    def build_ui(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=22, pady=17)

        header = tk.Frame(wrap, bg=BG)
        header.pack(fill="x", pady=(0, 18))
        logo = tk.Frame(header, bg=RED, width=42, height=42)
        logo.pack(side="left")
        logo.pack_propagate(False)
        self.label(logo, "H", "white", 20, True).pack(expand=True)
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left", padx=11)
        self.label(brand, "HADOC SUB", TEXT, 14, True).pack(anchor="w")
        self.label(brand, "SINHALA SUBTITLE TRANSLATOR", MUTED, 8, True).pack(anchor="w")
        self.label(header, "WINDOWS DESKTOP  •  v" + VERSION, "#bac6d8", 8, True,
                   bg="#182233", padx=12, pady=7).pack(side="right", pady=5)

        intro = tk.Frame(wrap, bg=BG)
        intro.pack(fill="x", pady=(0, 16))
        self.label(intro, "ENGLISH  →  SINHALA", "#ff8496", 9, True).pack(anchor="w")
        self.label(intro, "Your movie. Your language.", TEXT, 24, True).pack(anchor="w", pady=(3, 0))
        self.label(intro, "Translate SRT subtitles while preserving every timestamp and subtitle number.",
                   MUTED, 10).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(wrap, bg=BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, minsize=305, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.sidebar = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.workspace = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.workspace.grid(row=0, column=1, sticky="nsew")
        self.build_sidebar()
        self.build_workspace()

        footer = tk.Frame(wrap, bg=BG)
        footer.pack(fill="x", pady=(10, 0))
        self.label(footer, "HADOC • Built for Windows 10 / 11", "#66758d", 8).pack(side="left")
        self.label(footer, "API key is kept in memory only — never saved to disk.", "#71819a", 8).pack(side="right")

    def build_sidebar(self):
        self.label(self.sidebar, "01  SOURCE FILE", "#c6d0e0", 9, True).pack(anchor="w", padx=17, pady=(17, 3))
        self.label(self.sidebar, "Load an English subtitle file", MUTED, 8).pack(anchor="w", padx=17, pady=(0, 10))
        drop = tk.Frame(self.sidebar, bg="#111e2d", highlightbackground="#3b4a62", highlightthickness=1, height=137)
        drop.pack(fill="x", padx=17)
        drop.pack_propagate(False)
        self.label(drop, "⇧", "#ff8496", 23, True, bg="#111e2d").pack(pady=(8, 0))
        self.label(drop, "Choose your .SRT file", TEXT, 10, True, bg="#111e2d").pack()
        self.label(drop, "UTF-8 and Windows text supported", MUTED, 8, bg="#111e2d").pack(pady=(2, 7))
        self.button(drop, "Browse files", self.open_file, compact=True).pack()
        self.label(self.sidebar, "SELECTED FILE", "#aebbd0", 8, True).pack(anchor="w", padx=18, pady=(12, 4))
        self.label(self.sidebar, "", "#d6deeb", 8, wraplength=260, justify="left",
                   textvariable=self.file_name).pack(anchor="w", padx=18)

        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x", padx=17, pady=15)
        self.label(self.sidebar, "02  TRANSLATION ENGINE", "#c6d0e0", 9, True).pack(anchor="w", padx=17, pady=(0, 10))
        self.label(self.sidebar, "API BASE URL", "#aebbd0", 8, True).pack(anchor="w", padx=18, pady=(0, 4))
        self.field(self.sidebar, self.api_url).pack(fill="x", padx=17, ipady=8)
        self.label(self.sidebar, "MODEL", "#aebbd0", 8, True).pack(anchor="w", padx=18, pady=(10, 4))
        self.field(self.sidebar, self.model).pack(fill="x", padx=17, ipady=8)
        self.label(self.sidebar, "API KEY", "#aebbd0", 8, True).pack(anchor="w", padx=18, pady=(10, 4))
        keyrow = tk.Frame(self.sidebar, bg=PANEL)
        keyrow.pack(fill="x", padx=17)
        self.key_entry = self.field(keyrow, self.api_key, show="•")
        self.key_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.button(keyrow, "Show", self.toggle_key, compact=True).pack(side="left", padx=(5, 0))
        self.label(self.sidebar, "OpenAI-compatible API. Groq is preconfigured; change URL and model for another provider.",
                   "#8190a7", 8, wraplength=260, justify="left").pack(anchor="w", padx=18, pady=(7, 0))

        privacy = tk.Frame(self.sidebar, bg="#12231f", highlightbackground="#234338", highlightthickness=1)
        privacy.pack(fill="x", padx=17, pady=13)
        self.label(privacy, "✓  PRIVATE BY DEFAULT", GREEN, 8, True, bg="#12231f").pack(anchor="w", padx=10, pady=(7, 2))
        self.label(privacy, "API key stays in memory for this session. It is not saved in settings.",
                   "#a8c4b7", 8, bg="#12231f", wraplength=245, justify="left").pack(anchor="w", padx=10, pady=(0, 8))
        self.translate_button = self.button(self.sidebar, "↗   Translate to Sinhala", self.start_translation, primary=True)
        self.translate_button.pack(fill="x", padx=17, pady=(0, 7))
        self.button(self.sidebar, "Save Sinhala SRT", self.save_file).pack(fill="x", padx=17, pady=(0, 16))

    def build_workspace(self):
        top = tk.Frame(self.workspace, bg=PANEL)
        top.pack(fill="x", padx=16, pady=(15, 10))
        left = tk.Frame(top, bg=PANEL)
        left.pack(side="left")
        self.label(left, "SUBTITLE WORKSPACE", TEXT, 10, True).pack(anchor="w")
        self.label(left, "Review and edit your Sinhala translation", MUTED, 8).pack(anchor="w", pady=(2, 0))
        self.status = self.label(top, "● READY", GREEN, 8, True)
        self.status.pack(side="right", pady=5)

        stats = tk.Frame(self.workspace, bg=ALT)
        stats.pack(fill="x", padx=16, pady=(0, 10))
        for title, variable in (("SUBTITLES", self.count), ("TRANSLATED", self.done)):
            cell = tk.Frame(stats, bg=ALT)
            cell.pack(side="left", fill="x", expand=True, padx=11, pady=7)
            self.label(cell, title, MUTED, 7, True).pack(anchor="w")
            self.label(cell, "", TEXT, 17, True, textvariable=variable).pack(anchor="w")

        tools = tk.Frame(self.workspace, bg=PANEL)
        tools.pack(fill="x", padx=16, pady=(0, 9))
        self.button(tools, "＋ Open SRT", self.open_file, compact=True).pack(side="left")
        self.button(tools, "Save As…", self.save_file, compact=True).pack(side="left", padx=(7, 0))
        self.field(tools, self.filter_text).pack(side="right", ipady=7)
        self.filter_text.trace_add("write", lambda *_: self.refresh_table())

        table_frame = tk.Frame(self.workspace, bg=PANEL)
        table_frame.pack(fill="both", expand=True, padx=16)
        cols = ("number", "time", "english", "sinhala")
        self.table = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        for col, title in zip(cols, ("#", "TIMESTAMP", "ENGLISH", "SINHALA")):
            self.table.heading(col, text=title)
        self.table.column("number", width=38, minwidth=35, stretch=False, anchor="center")
        self.table.column("time", width=145, minwidth=135, stretch=False)
        self.table.column("english", width=220, minwidth=110, stretch=True)
        self.table.column("sinhala", width=220, minwidth=110, stretch=True)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self.select_row)

        editor = tk.Frame(self.workspace, bg=ALT, highlightbackground=BORDER, highlightthickness=1)
        editor.pack(fill="x", padx=16, pady=(9, 10))
        edit_head = tk.Frame(editor, bg=ALT)
        edit_head.pack(fill="x", padx=10, pady=(8, 5))
        self.label(edit_head, "SELECTED SUBTITLE", "#aebbd0", 8, True).pack(side="left")
        self.selected_label = self.label(edit_head, "No subtitle selected", MUTED, 8)
        self.selected_label.pack(side="right")
        columns = tk.Frame(editor, bg=ALT)
        columns.pack(fill="x", padx=10, pady=(0, 6))
        original_col = tk.Frame(columns, bg=ALT)
        original_col.pack(side="left", fill="both", expand=True, padx=(0, 5))
        translated_col = tk.Frame(columns, bg=ALT)
        translated_col.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.label(original_col, "ENGLISH SOURCE", MUTED, 7, True, bg=ALT).pack(anchor="w", pady=(0, 4))
        self.label(translated_col, "SINHALA TRANSLATION · EDITABLE", MUTED, 7, True, bg=ALT).pack(anchor="w", pady=(0, 4))
        self.original_box = tk.Text(original_col, height=3, wrap="word", bg="#121c2b", fg="#aab8cc",
                                    relief="flat", font=("Segoe UI", 9), padx=7, pady=6)
        self.original_box.pack(fill="both", expand=True)
        self.original_box.configure(state="disabled")
        self.translated_box = tk.Text(translated_col, height=3, wrap="word", bg="#121c2b", fg=TEXT,
                                      insertbackground=TEXT, relief="flat", font=("Nirmala UI", 10),
                                      padx=7, pady=6)
        self.translated_box.pack(fill="both", expand=True)
        self.button(editor, "Apply edit", self.apply_edit, compact=True).pack(anchor="e", padx=10, pady=(0, 8))

        progress_row = tk.Frame(self.workspace, bg=PANEL)
        progress_row.pack(fill="x", padx=16, pady=(0, 5))
        self.label(progress_row, "", MUTED, 8, textvariable=self.progress_text).pack(side="left")
        self.progress_percent = self.label(progress_row, "0%", "#ff8496", 8, True)
        self.progress_percent.pack(side="right")
        self.progress = ttk.Progressbar(self.workspace, maximum=100, style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=16, pady=(0, 14))

    def toggle_key(self):
        self.reveal_key = not self.reveal_key
        self.key_entry.configure(show="" if self.reveal_key else "•")

    def set_status(self, text, mode="ready"):
        self.status.configure(text="● " + ("WORKING" if mode == "working" else "READY"),
                              fg=YELLOW if mode == "working" else (GREEN if mode == "success" else MUTED))
        self.progress_text.set(text)

    def open_file(self):
        if self.busy:
            return
        name = filedialog.askopenfilename(
            title="Open English SRT",
            filetypes=[("SRT subtitles", "*.srt"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not name:
            return
        try:
            try:
                raw = Path(name).read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                raw = Path(name).read_text(encoding="cp1252")
            self.items = parse_srt(raw)
        except Exception as exc:
            messagebox.showerror("Could not open subtitle", str(exc))
            return
        self.source_path = Path(name)
        self.file_name.set(self.source_path.name + "  •  " + str(len(self.items)) + " subtitles")
        self.count.set(f"{len(self.items):,}")
        self.done.set("0%")
        self.progress.configure(value=0)
        self.progress_percent.configure(text="0%")
        self.selected = None
        self.clear_editor()
        self.refresh_table()
        self.set_status(f"Loaded {len(self.items):,} subtitle entries", "success")

    def refresh_table(self):
        if not hasattr(self, "table"):
            return
        query = self.filter_text.get().strip().casefold()
        self.table.delete(*self.table.get_children())
        for i, item in enumerate(self.items):
            if query and query not in item.original.casefold() and query not in item.translated.casefold() and query not in item.number:
                continue
            self.table.insert("", "end", iid=str(i), values=(
                item.number, item.timing, item.original.replace("\n", " / "),
                item.translated.replace("\n", " / ") if item.translated else "—"
            ))

    def clear_editor(self):
        self.selected_label.configure(text="No subtitle selected")
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.configure(state="disabled")
        self.translated_box.delete("1.0", "end")

    def select_row(self, _event=None):
        selected = self.table.selection()
        if not selected:
            return
        self.selected = int(selected[0])
        item = self.items[self.selected]
        self.selected_label.configure(text="#" + item.number + "  •  " + item.timing)
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.insert("1.0", item.original)
        self.original_box.configure(state="disabled")
        self.translated_box.delete("1.0", "end")
        self.translated_box.insert("1.0", item.translated)

    def apply_edit(self):
        if self.selected is None:
            return
        self.items[self.selected].translated = self.translated_box.get("1.0", "end-1c").strip()
        self.refresh_table()
        iid = str(self.selected)
        if self.table.exists(iid):
            self.table.selection_set(iid)
            self.table.see(iid)
        self.update_stats()
        self.set_status("Subtitle #" + self.items[self.selected].number + " updated", "success")

    def update_stats(self):
        translated = sum(bool(row.translated.strip()) for row in self.items)
        pct = round(translated * 100 / len(self.items)) if self.items else 0
        self.done.set(str(pct) + "%")
        self.progress.configure(value=pct)
        self.progress_percent.configure(text=str(pct) + "%")

    def start_translation(self):
        if self.busy:
            return
        if not self.items:
            messagebox.showinfo("Load subtitles first", "Choose an English SRT file before translating.")
            return
        base = self.api_url.get().strip().rstrip("/")
        model = self.model.get().strip()
        key = self.api_key.get().strip()
        if not base or not model or not key:
            messagebox.showwarning("Missing API settings", "Enter an API base URL, model name and API key.")
            return
        if not (base.startswith("https://") or base.startswith("http://localhost")):
            messagebox.showwarning("Check API URL", "Use an HTTPS API URL. HTTP is allowed only for localhost.")
            return
        self.save_settings()
        self.busy = True
        self.translate_button.configure(state="disabled", text="Translating…")
        self.progress.configure(value=0)
        self.progress_percent.configure(text="0%")
        self.set_status("Sending subtitle batches to translation model", "working")
        snapshot = [(i, row.original) for i, row in enumerate(self.items)]
        threading.Thread(target=self.translation_worker, args=(snapshot, base, model, key), daemon=True).start()

    def translation_worker(self, snapshot, base, model, key):
        size = 18
        try:
            total = len(snapshot)
            for start in range(0, total, size):
                batch = snapshot[start:start + size]
                translations = self.translate_batch(batch, base, model, key)
                for index, value in translations.items():
                    self.events.put(("row", index, value))
                self.events.put(("progress", min(start + len(batch), total), total))
            self.events.put(("complete", total))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def translate_batch(self, batch, base, model, key):
        payload = [{"index": index + 1, "text": text} for index, text in batch]
        system = (
            "You are a professional English-to-Sinhala movie subtitle translator. "
            "Translate into natural, concise, emotionally appropriate Sri Lankan Sinhala. "
            "Preserve character names, meaning, tone, line breaks where practical, and all formatting tags exactly, "
            "including <i>, </i>, and {\\\\an8}. Do not add explanations, speaker labels, quotes, or notes. "
            "Return ONLY valid JSON in this exact shape: "
            '{"translations":[{"index":1,"text":"Sinhala translation"}]}. '
            "Include every supplied index exactly once."
        )
        user = "Translate these subtitle items from English to Sinhala. Keep indices unchanged. JSON only:\n"
        user += json.dumps(payload, ensure_ascii=False)
        body = json.dumps({
            "model": model, "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(base + "/chat/completions", data=body, headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "User-Agent": "HADOC-Sub/" + VERSION
        }, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
            if exc.code in (401, 403):
                raise RuntimeError("API authentication failed. Check your API key and provider permissions.") from exc
            if exc.code == 429:
                raise RuntimeError("API rate limit or quota reached. Check provider limits and try again.") from exc
            raise RuntimeError(f"Translation API error ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not connect to translation API: {exc.reason}") from exc
        try:
            answer = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("The API response did not contain a chat completion.")
        result = parse_json_response(answer)
        rows = result.get("translations")
        if not isinstance(rows, list):
            raise RuntimeError("The model response did not include a translations list.")
        expected = {index + 1 for index, _ in batch}
        mapped = {}
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("text"), str):
                try:
                    idx = int(row.get("index"))
                except (TypeError, ValueError):
                    continue
                if idx in expected and row["text"].strip():
                    mapped[idx - 1] = row["text"].strip()
        missing = expected - {index + 1 for index in mapped}
        if missing:
            raise RuntimeError("The model missed subtitle item(s): " + ", ".join(map(str, sorted(missing))) + ". Try again or choose another model.")
        return mapped

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "row":
                    _, index, value = event
                    self.items[index].translated = value
                    iid = str(index)
                    if self.table.exists(iid):
                        values = list(self.table.item(iid, "values"))
                        values[3] = value.replace("\n", " / ")
                        self.table.item(iid, values=values)
                    if self.selected == index:
                        self.translated_box.delete("1.0", "end")
                        self.translated_box.insert("1.0", value)
                elif event[0] == "progress":
                    _, completed, total = event
                    pct = round(completed * 100 / total)
                    self.progress.configure(value=pct)
                    self.progress_percent.configure(text=str(pct) + "%")
                    self.progress_text.set(f"Translated {completed:,} of {total:,} subtitles")
                    self.done.set(str(pct) + "%")
                elif event[0] == "complete":
                    total = event[1]
                    self.busy = False
                    self.translate_button.configure(state="normal", text="↗   Translate to Sinhala")
                    self.progress.configure(value=100)
                    self.progress_percent.configure(text="100%")
                    self.done.set("100%")
                    self.set_status(f"Translation complete • {total:,} subtitles", "success")
                    messagebox.showinfo("Translation complete", f"Translated {total:,} subtitle entries.\n\nReview the result and click Save Sinhala SRT.")
                elif event[0] == "error":
                    self.busy = False
                    self.translate_button.configure(state="normal", text="↗   Translate to Sinhala")
                    self.set_status("Translation stopped • " + event[1])
                    messagebox.showerror("Translation failed", event[1])
        except queue.Empty:
            pass
        self.root.after(120, self.poll_events)

    def save_file(self):
        if not self.items:
            messagebox.showinfo("Nothing to save", "Load an SRT file first.")
            return
        if self.busy:
            messagebox.showwarning("Translation in progress", "Wait until translation finishes before saving.")
            return
        if self.selected is not None:
            self.apply_edit()
        default_name = self.source_path.stem + "_si.srt" if self.source_path else "subtitles_si.srt"
        folder = str(self.source_path.parent) if self.source_path else str(Path.home())
        name = filedialog.asksaveasfilename(title="Save Sinhala SRT", initialdir=folder,
                initialfile=default_name, defaultextension=".srt",
                filetypes=[("SubRip subtitles", "*.srt")])
        if not name:
            return
        output = "\n\n".join(
            f"{row.number}\n{row.timing}\n{row.translated if row.translated.strip() else row.original}"
            for row in self.items
        ) + "\n"
        try:
            Path(name).write_text(output, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not save file", str(exc))
            return
        self.set_status("Saved " + Path(name).name, "success")
        messagebox.showinfo("Saved successfully", "Sinhala SRT saved to:\n" + name)


def main():
    root = tk.Tk()
    HadocSub(root)
    root.mainloop()


if __name__ == "__main__":
    main()
