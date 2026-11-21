import base64
from concurrent.futures import ThreadPoolExecutor
import ctypes
import hashlib
from ctypes import wintypes
import json
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

VERSION = "1.6.0"
PROVIDERS = {
    "Google Gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.8-flash",
    },
    "Groq": {
        "url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
    },
    "NVIDIA NIM": {
        "url": "https://integrate.api.nvidia.com/v1",
        "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    },
    "OpenRouter Free": {
        "url": "https://openrouter.ai/api/v1",
        "model": "openrouter/free",
    },
    "Cloudflare Workers AI": {
        "url": "https://api.cloudflare.com/client/v4/accounts/ACCOUNT_ID/ai/run",
        "model": "@cf/meta/m2m100-1.2b",
    },
    "MyMemory Translation": {
        "url": "https://api.mymemory.translated.net",
        "model": "en-US|si-LK",
    },
    "Google Translate (Fast)": {
        "url": "https://translate.googleapis.com/translate_a/t",
        "model": "en|si",
    },
}
NO_KEY_PROVIDERS = {"MyMemory Translation", "Google Translate (Fast)"}
BG = "#080d16"
SIDEBAR = "#0d1420"
PANEL = "#111b2a"
PANEL_2 = "#162235"
PANEL_3 = "#0d1725"
BORDER = "#26364c"
TEXT = "#f4f7fc"
MUTED = "#93a3b9"
ACCENT = "#f0526c"
ACCENT_HOVER = "#ff6b83"
GREEN = "#6ce0ae"
YELLOW = "#ffcb72"
FONT = "Segoe UI"


@dataclass
class Subtitle:
    number: str
    timing: str
    original: str
    translated: str = ""


def parse_srt(raw):
    raw = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    time_re = re.compile(
        r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}"
    )
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


class ProviderFailure(RuntimeError):
    def __init__(self, provider_name, status_code, message, retry_after=None):
        super().__init__(message)
        self.provider_name = provider_name
        self.status_code = status_code
        self.retry_after = retry_after


def source_fingerprint(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_retry_seconds(headers):
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value:
        try:
            return max(1, min(86400, int(float(value))))
        except (TypeError, ValueError):
            pass
    for name in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = headers.get(name)
        if not value:
            continue
        match = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", value.strip())
        if match and any(match.groups()):
            seconds = (float(match.group(1) or 0) * 3600 +
                       float(match.group(2) or 0) * 60 +
                       float(match.group(3) or 0))
            return max(1, min(86400, int(seconds)))
    return None


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


def extract_cloudflare_translation(data):
    """Extract a translated string from the Workers AI REST API envelope."""
    if not isinstance(data, dict):
        raise ValueError("Cloudflare returned an unexpected response.")

    if data.get("success") is False:
        errors = data.get("errors") or []
        detail = "; ".join(
            str(item.get("message", item)) if isinstance(item, dict) else str(item)
            for item in errors
        )
        raise ValueError(detail or "Cloudflare reported an unsuccessful request.")

    result = data.get("result", data)
    if isinstance(result, dict):
        translated = (
            result.get("translated_text")
            or result.get("translation")
            or result.get("answer")
        )
    elif isinstance(result, str):
        translated = result
    else:
        translated = None

    if not isinstance(translated, str) or not translated.strip():
        raise ValueError("Cloudflare response did not contain translated_text.")
    return translated.strip()


def cloudflare_model_endpoint(base_url, model):
    return base_url.rstrip("/") + "/" + model.lstrip("/")


def build_google_translate_url(base_url, texts, source="en", target="si"):
    params = [
        ("client", "dict-chrome-ex"),
        ("sl", source),
        ("tl", target),
    ]
    params.extend(("q", text) for text in texts)
    return base_url.rstrip("/") + "?" + urllib.parse.urlencode(params)


def extract_google_translate_translations(data, expected_count):
    if not isinstance(data, list):
        raise ValueError("Google Translate returned an unexpected response.")
    if len(data) != expected_count:
        raise ValueError(
            f"Google Translate returned {len(data)} translations for {expected_count} subtitles."
        )

    translations = []
    for row in data:
        translated = None
        if isinstance(row, str):
            translated = row
        elif isinstance(row, list) and row:
            if isinstance(row[0], str):
                translated = row[0]
            elif isinstance(row[0], list):
                segments = [
                    part[0] for part in row[0]
                    if isinstance(part, list) and part and isinstance(part[0], str)
                ]
                translated = "".join(segments)
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError("Google Translate returned an empty or unreadable subtitle.")
        translations.append(translated.strip())
    return translations


def build_mymemory_url(base_url, text, email="", langpair="en-US|si-LK"):
    params = {"q": text, "langpair": langpair, "mt": "1"}
    if email:
        params["de"] = email
    return base_url.rstrip("/") + "/get?" + urllib.parse.urlencode(params)


def extract_mymemory_translation(data):
    if not isinstance(data, dict):
        raise ValueError("MyMemory returned an unexpected response.")
    try:
        status = int(data.get("responseStatus", 0))
    except (TypeError, ValueError):
        status = 0
    if status != 200:
        detail = data.get("responseDetails") or "MyMemory could not translate this subtitle."
        if data.get("quotaFinished"):
            detail = "MyMemory daily free quota has been reached. " + str(detail)
        raise ValueError(str(detail))
    response = data.get("responseData") or {}
    translated = response.get("translatedText") if isinstance(response, dict) else None
    if not isinstance(translated, str) or not translated.strip():
        raise ValueError(data.get("responseDetails") or "MyMemory returned an empty translation.")
    return translated.strip()


def split_mymemory_chunks(text, max_bytes=450):
    """Split oversized subtitle text into UTF-8-safe chunks under MyMemory's 500-byte limit."""
    chunks = []
    current = ""
    for word in text.split():
        if len(word.encode("utf-8")) > max_bytes:
            if current:
                chunks.append(current)
                current = ""
            piece = ""
            for char in word:
                if len((piece + char).encode("utf-8")) > max_bytes:
                    if piece:
                        chunks.append(piece)
                    piece = char
                else:
                    piece += char
            if piece:
                current = piece
            continue
        candidate = (current + " " + word).strip()
        if len(candidate.encode("utf-8")) > max_bytes and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


def _dpapi_blob(data):
    class DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    buffer = ctypes.create_string_buffer(data)
    blob = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return DataBlob, buffer, blob


def protect_secret(secret):
    if os.name != "nt":
        raise RuntimeError("Secure API-key storage requires Windows DPAPI.")
    crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    DataBlob, input_buffer, input_blob = _dpapi_blob(secret.encode("utf-8"))
    output_blob = DataBlob()
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DataBlob)
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob), "HADOC Sub API key", None, None, None, 0,
        ctypes.byref(output_blob)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def unprotect_secret(encoded):
    if os.name != "nt":
        return ""
    try:
        crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        decoded = base64.b64decode(encoded.encode("ascii"))
        DataBlob, input_buffer, input_blob = _dpapi_blob(decoded)
        output_blob = DataBlob()
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob),
            wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DataBlob)
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        if not crypt32.CryptUnprotectData(
            ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
        ):
            return ""
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))
    except Exception:
        return ""


class HadocSub:
    def __init__(self, root):
        self.root = root
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.root.title("HADOC Sub")
        self.root.configure(fg_color=BG)
        self.root.minsize(1100, 700)
        try:
            self.root.state("zoomed")
        except tk.TclError:
            self.root.geometry("1440x900")
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

        self.events = queue.Queue()
        self.items = []
        self.source_path = None
        self.selected = None
        self.busy = False
        self.fullscreen = False
        self.on_setup_screen = False
        self.settings_path = Path(os.environ.get("APPDATA", str(Path.home()))) / "HADOC-Sub" / "settings.json"
        self.progress_dir = self.settings_path.parent / "progress"
        self.providers = []
        self.mymemory_cache = {}
        self.mymemory_cache_lock = threading.Lock()

        self.provider = tk.StringVar(value="Google Translate (Fast)")
        self.api_url = tk.StringVar(value=PROVIDERS["Google Translate (Fast)"]["url"])
        self.model = tk.StringVar(value=PROVIDERS["Google Translate (Fast)"]["model"])
        self.api_key = tk.StringVar()
        self.key_visible = False
        self.search_text = tk.StringVar()
        self.search_text.trace_add("write", lambda *_: self.refresh_table())
        self.progress_value = tk.DoubleVar(value=0)
        self.status_text = tk.StringVar(value="Ready")
        self.file_text = tk.StringVar(value="No subtitle file selected")
        self.count_text = tk.StringVar(value="0")
        self.translated_text = tk.StringVar(value="0")
        self.setup_status = tk.StringVar(value="Enter your API details to get started.")
        self.settings = {}
        self.load_settings()

        self.root.after(120, self.poll_events)
        if self.providers:
            self.show_main()
        else:
            self.show_setup(first_run=True)

    def clear_root(self):
        for child in self.root.winfo_children():
            child.destroy()

    def toggle_fullscreen(self, _event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def exit_fullscreen(self, _event=None):
        if self.fullscreen:
            self.fullscreen = False
            self.root.attributes("-fullscreen", False)

    def load_settings(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            self.settings = data
            saved = data.get("providers")
            if isinstance(saved, list):
                for item in saved:
                    key = unprotect_secret(item.get("api_key_protected", ""))
                    name = item.get("name", "Custom")
                    if (key or name in NO_KEY_PROVIDERS) and item.get("url") and item.get("model"):
                        self.providers.append({
                            "name": name,
                            "url": item["url"].rstrip("/"),
                            "model": item["model"],
                            "key": key,
                        })
            else:
                # Migrate settings from HADOC Sub v1.0–v1.2.
                key = unprotect_secret(data.get("api_key_protected", ""))
                if key:
                    self.providers.append({
                        "name": data.get("provider", "Google Gemini"),
                        "url": data.get("api_url", PROVIDERS["Google Gemini"]["url"]).rstrip("/"),
                        "model": data.get("model", PROVIDERS["Google Gemini"]["model"]),
                        "key": key,
                    })
            # A MyMemory-only v1.5 installation gets Google Translate as the
            # fast batched first choice, with the saved MyMemory account as fallback.
            if (
                any(item["name"] == "MyMemory Translation" for item in self.providers)
                and not any(item["name"] == "Google Translate (Fast)" for item in self.providers)
            ):
                self.providers.insert(0, {
                    "name": "Google Translate (Fast)",
                    "url": PROVIDERS["Google Translate (Fast)"]["url"],
                    "model": PROVIDERS["Google Translate (Fast)"]["model"],
                    "key": "",
                })
            if self.providers:
                first = self.providers[0]
                self.provider.set(first["name"])
                self.api_url.set(first["url"])
                self.model.set(first["model"])
        except (OSError, ValueError, TypeError):
            self.settings = {}
            self.providers = []

    def persist_settings(self):
        if not self.providers:
            raise ValueError("Add at least one API provider before saving.")
        saved = []
        for item in self.providers:
            saved.append({
                "name": item["name"],
                "url": item["url"],
                "model": item["model"],
                "api_key_protected": protect_secret(item["key"]) if item["key"] else "",
            })
        first = self.providers[0]
        data = {
            "providers": saved,
            # Retain encrypted legacy fields so older versions can still read a default provider.
            "provider": first["name"],
            "api_url": first["url"],
            "model": first["model"],
            "api_key_protected": saved[0]["api_key_protected"],
            "version": VERSION,
        }
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.settings_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_path.replace(self.settings_path)
        self.settings = data

    def make_label(self, parent, text, color=MUTED, size=12, weight="normal", **kwargs):
        return ctk.CTkLabel(
            parent, text=text, text_color=color,
            font=ctk.CTkFont(family=FONT, size=size, weight=weight), **kwargs
        )

    def make_button(self, parent, text, command, primary=False, height=42, **kwargs):
        button_color = kwargs.pop("fg_color", ACCENT if primary else PANEL_2)
        hover_color = kwargs.pop("hover_color", ACCENT_HOVER if primary else "#20324a")
        return ctk.CTkButton(
            parent, text=text, command=command, height=height, corner_radius=10,
            fg_color=button_color,
            hover_color=hover_color,
            text_color="#ffffff", font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
            border_width=0, **kwargs
        )

    def make_entry(self, parent, variable, placeholder="", show=None, height=42):
        return ctk.CTkEntry(
            parent, textvariable=variable, placeholder_text=placeholder,
            height=height, corner_radius=9, fg_color="#0a1320",
            border_color=BORDER, border_width=1, text_color=TEXT,
            placeholder_text_color="#64758d",
            font=ctk.CTkFont(family=FONT, size=13), show=show
        )

    def open_settings(self):
        if self.busy:
            messagebox.showinfo("Translation in progress", "Finish the current translation before changing API settings.")
            return
        self.show_setup(first_run=False)

    def show_setup(self, first_run=False):
        self.on_setup_screen = True
        self.clear_root()
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        canvas = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.grid_columnconfigure(0, weight=1)
        canvas.grid_rowconfigure(0, weight=1)
        center = ctk.CTkFrame(canvas, fg_color="transparent")
        center.grid(row=0, column=0, sticky="nsew")
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)

        card = ctk.CTkScrollableFrame(
            center, fg_color=PANEL, corner_radius=22, border_width=1,
            border_color=BORDER, width=740, height=680
        )
        card.place(relx=0.5, rely=0.49, anchor="center")
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=30, pady=(25, 8))
        mark = ctk.CTkFrame(head, fg_color=ACCENT, width=48, height=48, corner_radius=14)
        mark.pack(side="left")
        mark.pack_propagate(False)
        self.make_label(mark, "H", "#ffffff", 24, "bold").place(relx=0.5, rely=0.5, anchor="center")
        title_box = ctk.CTkFrame(head, fg_color="transparent")
        title_box.pack(side="left", padx=13)
        self.make_label(title_box, "HADOC SUB", TEXT, 19, "bold").pack(anchor="w")
        self.make_label(title_box, "API PROVIDER POOL" if not first_run else "FIRST-TIME SETUP",
                        MUTED, 10, "bold").pack(anchor="w", pady=(2, 0))

        self.make_label(card, "Choose a fast translation provider.", TEXT, 23, "bold",
                        anchor="w").grid(row=1, column=0, sticky="ew", padx=32, pady=(10, 4))
        self.make_label(
            card, "Google Translate can translate several subtitle lines in one request. MyMemory is kept as a no-key backup if Google is unavailable.",
            MUTED, 12, anchor="w", wraplength=650, justify="left"
        ).grid(row=2, column=0, sticky="ew", padx=32, pady=(0, 18))

        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=3, column=0, sticky="ew", padx=32)
        form.grid_columnconfigure(0, weight=1)

        self.make_label(form, "PROVIDER", "#c3cede", 10, "bold").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.provider_menu = ctk.CTkOptionMenu(
            form, values=list(PROVIDERS.keys()) + ["Custom"],
            variable=self.provider, command=self.provider_changed,
            height=41, corner_radius=9, fg_color=PANEL_2, button_color="#253951",
            button_hover_color="#314966", text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=13)
        )
        self.provider_menu.grid(row=1, column=0, sticky="ew", pady=(0, 11))

        self.api_url_label = self.make_label(form, "API BASE URL", "#c3cede", 10, "bold")
        self.api_url_label.grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.make_entry(form, self.api_url, "https://provider.example/v1").grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self.model_label = self.make_label(form, "MODEL NAME", "#c3cede", 10, "bold")
        self.model_label.grid(row=4, column=0, sticky="w", pady=(0, 5))
        self.make_entry(form, self.model, "Model ID from your provider").grid(row=5, column=0, sticky="ew", pady=(0, 10))

        self.api_key_label = self.make_label(form, "API KEY", "#c3cede", 10, "bold")
        self.api_key_label.grid(row=6, column=0, sticky="w", pady=(0, 5))
        key_row = ctk.CTkFrame(form, fg_color="transparent")
        key_row.grid(row=7, column=0, sticky="ew", pady=(0, 8))
        key_row.grid_columnconfigure(0, weight=1)
        self.setup_key_entry = self.make_entry(key_row, self.api_key, "Paste this provider's API key", show="•")
        self.setup_key_entry.grid(row=0, column=0, sticky="ew")
        self.make_button(key_row, "Show", self.toggle_setup_key, height=41, width=76).grid(row=0, column=1, padx=(8, 0))
        self.update_provider_field_labels(self.provider.get())

        provider_actions = ctk.CTkFrame(form, fg_color="transparent")
        provider_actions.grid(row=8, column=0, sticky="ew", pady=(0, 13))
        provider_actions.grid_columnconfigure(0, weight=1)
        provider_actions.grid_columnconfigure(1, weight=1)
        self.make_button(provider_actions, "Test API", self.test_api, height=40).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.make_button(provider_actions, "＋ Add to provider pool", self.add_provider, primary=True, height=40).grid(row=0, column=1, sticky="ew", padx=(5, 0))

        pool_head = ctk.CTkFrame(form, fg_color="transparent")
        pool_head.grid(row=9, column=0, sticky="ew", pady=(2, 6))
        self.make_label(pool_head, "CONFIGURED PROVIDERS", "#c3cede", 10, "bold").pack(side="left")
        self.pool_count_label = self.make_label(pool_head, "", GREEN, 10, "bold")
        self.pool_count_label.pack(side="right")

        self.pool_list_frame = ctk.CTkScrollableFrame(
            form, fg_color=PANEL_3, corner_radius=10, height=118,
            border_width=1, border_color=BORDER
        )
        self.pool_list_frame.grid(row=10, column=0, sticky="ew", pady=(0, 10))
        self.render_provider_pool()

        self.make_label(
            form, "Google Translate Web is an unofficial no-key endpoint and may be rate-limited. MyMemory is the backup; its optional email is stored securely.",
            "#91aa9f", 10, anchor="w", wraplength=650, justify="left"
        ).grid(row=11, column=0, sticky="ew", pady=(0, 9))

        self.setup_status_label = self.make_label(
            form, self.setup_status.get(), YELLOW, 10, anchor="w", wraplength=650, justify="left"
        )
        self.setup_status_label.grid(row=12, column=0, sticky="ew", pady=(0, 9))

        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=13, column=0, sticky="ew", pady=(0, 16))
        actions.grid_columnconfigure(0, weight=1)
        label = "Save & Start HADOC Sub  →" if first_run else "Save provider pool & Return  →"
        self.make_button(actions, label, self.save_and_continue, primary=True, height=46).grid(
            row=0, column=0, sticky="ew"
        )

        bottom = ctk.CTkFrame(canvas, fg_color="transparent")
        bottom.place(relx=0.5, rely=0.975, anchor="center")
        self.make_label(bottom, "HADOC • KYZER_HADOC   |   F11 FULLSCREEN   |   PROVIDERS AUTO-FAILOVER",
                        "#64758d", 9, "bold").pack()

    def update_provider_field_labels(self, choice):
        if not hasattr(self, "api_key_label"):
            return
        if choice == "Google Translate (Fast)":
            self.api_url_label.configure(text="GOOGLE TRANSLATE ENDPOINT")
            self.model_label.configure(text="LANGUAGE PAIR")
            self.api_key_label.configure(text="API KEY (NOT REQUIRED)")
            self.setup_key_entry.configure(placeholder_text="No API key needed — leave this blank")
        elif choice == "MyMemory Translation":
            self.api_url_label.configure(text="TRANSLATION SERVICE URL")
            self.model_label.configure(text="LANGUAGE PAIR")
            self.api_key_label.configure(text="EMAIL (OPTIONAL — 50,000 CHARACTERS/DAY)")
            self.setup_key_entry.configure(
                placeholder_text="Optional email address — leave blank for 5,000/day"
            )
        elif choice == "Cloudflare Workers AI":
            self.api_url_label.configure(text="API BASE URL  •  Replace ACCOUNT_ID with your Account ID")
            self.model_label.configure(text="MODEL NAME")
            self.api_key_label.configure(text="API TOKEN")
            self.setup_key_entry.configure(placeholder_text="Paste your Cloudflare Workers AI token")
        else:
            self.api_url_label.configure(text="API BASE URL")
            self.model_label.configure(text="MODEL NAME")
            self.api_key_label.configure(text="API KEY")
            self.setup_key_entry.configure(placeholder_text="Paste this provider's API key")

    def provider_changed(self, choice):
        if choice in PROVIDERS:
            self.api_url.set(PROVIDERS[choice]["url"])
            self.model.set(PROVIDERS[choice]["model"])
        else:
            self.api_url.set("")
            self.model.set("")
        self.update_provider_field_labels(choice)

    def toggle_setup_key(self):
        self.key_visible = not self.key_visible
        self.setup_key_entry.configure(show="" if self.key_visible else "•")

    def render_provider_pool(self):
        if not hasattr(self, "pool_list_frame"):
            return
        for child in self.pool_list_frame.winfo_children():
            child.destroy()
        self.pool_count_label.configure(text=f"{len(self.providers)} ready")
        if not self.providers:
            self.make_label(
                self.pool_list_frame, "No providers added yet. Add Gemini, Groq, NVIDIA NIM or another compatible API above.",
                MUTED, 10, anchor="w", wraplength=630
            ).pack(fill="x", padx=10, pady=11)
            return
        for index, provider in enumerate(self.providers):
            row = ctk.CTkFrame(self.pool_list_frame, fg_color=PANEL_2, corner_radius=8)
            row.pack(fill="x", padx=5, pady=4)
            details = ctk.CTkFrame(row, fg_color="transparent")
            details.pack(side="left", fill="x", expand=True, padx=10, pady=7)
            self.make_label(details, provider["name"], TEXT, 11, "bold").pack(anchor="w")
            self.make_label(details, provider["model"], MUTED, 9).pack(anchor="w", pady=(2, 0))
            self.make_button(
                row, "Remove", lambda i=index: self.remove_provider(i),
                height=30, width=76, fg_color="#3a2631", hover_color="#5a3040"
            ).pack(side="right", padx=8)

    def add_provider(self):
        name = self.provider.get().strip()
        base = self.api_url.get().strip().rstrip("/")
        model = self.model.get().strip()
        key = self.api_key.get().strip()
        if not base.startswith("https://") and not base.startswith("http://localhost"):
            messagebox.showwarning("Invalid API URL", "Enter a valid HTTPS API base URL.")
            return
        if not name or not model or (not key and name not in NO_KEY_PROVIDERS):
            messagebox.showwarning("Missing details", "Choose a provider and enter the required details. Google Translate and MyMemory do not require API keys.")
            return
        if name == "MyMemory Translation" and key and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", key):
            messagebox.showwarning("Invalid email", "For MyMemory, the optional field is an email address, not an API key.")
            return
        if name == "Cloudflare Workers AI" and "ACCOUNT_ID" in base.upper():
            messagebox.showwarning("Account ID required", "Replace ACCOUNT_ID in the API Base URL with your Cloudflare Account ID.")
            return
        existing = next(
            (
                item for item in self.providers
                if item["url"] == base and item["model"] == model and item["name"] == name
            ),
            None,
        )
        if existing:
            if name == "MyMemory Translation" and key:
                existing["key"] = key
                self.providers.remove(existing)
                google_index = next(
                    (i for i, item in enumerate(self.providers)
                     if item["name"] == "Google Translate (Fast)"),
                    None,
                )
                if google_index is None:
                    self.providers.insert(0, existing)
                else:
                    self.providers.insert(google_index + 1, existing)
                self.api_key.set("")
                self.setup_status.set("MyMemory email updated. Its higher daily allowance will be used.")
                self.setup_status_label.configure(text=self.setup_status.get(), text_color=GREEN)
                self.render_provider_pool()
                return
            messagebox.showinfo("Already added", "This provider and model are already in your pool.")
            return
        provider_entry = {"name": name, "url": base, "model": model, "key": key}
        if name == "Google Translate (Fast)":
            self.providers.insert(0, provider_entry)
        elif name == "MyMemory Translation":
            google_index = next(
                (i for i, item in enumerate(self.providers)
                 if item["name"] == "Google Translate (Fast)"),
                None,
            )
            if google_index is None:
                self.providers.insert(0, provider_entry)
            else:
                self.providers.insert(google_index + 1, provider_entry)
        else:
            self.providers.append(provider_entry)
        self.api_key.set("")
        self.setup_status.set(f"{name} added. Add another provider or save your provider pool.")
        self.setup_status_label.configure(text=self.setup_status.get(), text_color=GREEN)
        self.render_provider_pool()

    def remove_provider(self, index):
        if index < 0 or index >= len(self.providers):
            return
        removed = self.providers.pop(index)
        self.setup_status.set(removed["name"] + " removed from the provider pool.")
        self.setup_status_label.configure(text=self.setup_status.get(), text_color=YELLOW)
        self.render_provider_pool()

    def save_and_continue(self):
        # Add the current form only when it has not already been added.
        name = self.provider.get().strip()
        base = self.api_url.get().strip().rstrip("/")
        model = self.model.get().strip()
        already_added = any(
            item["name"] == name and item["url"] == base and item["model"] == model
            for item in self.providers
        )
        if self.api_key.get().strip() or (name in NO_KEY_PROVIDERS and not already_added):
            self.add_provider()
        if not self.providers:
            messagebox.showwarning("No API providers", "Add at least one API provider before continuing.")
            return
        try:
            self.persist_settings()
        except Exception as exc:
            messagebox.showerror("Could not save provider pool", str(exc))
            return
        self.show_main()

    def test_api(self):
        base = self.api_url.get().strip().rstrip("/")
        model = self.model.get().strip()
        key = self.api_key.get().strip()
        provider_name = self.provider.get().strip()
        needs_key = provider_name not in NO_KEY_PROVIDERS
        if not base.startswith("https://") or not model or (needs_key and not key):
            self.setup_status.set("Enter the service URL and required details. Google Translate and MyMemory need no API key.")
            self.setup_status_label.configure(text=self.setup_status.get(), text_color=YELLOW)
            return
        if provider_name == "MyMemory Translation" and key and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", key):
            self.setup_status.set("Enter a valid email address or leave it blank.")
            self.setup_status_label.configure(text=self.setup_status.get(), text_color=YELLOW)
            return
        if provider_name == "Cloudflare Workers AI" and "ACCOUNT_ID" in base.upper():
            self.setup_status.set("Replace ACCOUNT_ID in the URL with your Cloudflare Account ID.")
            self.setup_status_label.configure(text=self.setup_status.get(), text_color=YELLOW)
            return
        self.setup_status.set("Testing " + provider_name + " connection…")
        self.setup_status_label.configure(text=self.setup_status.get(), text_color=YELLOW)
        threading.Thread(target=self.api_test_worker, args=(base, model, key, provider_name), daemon=True).start()

    def api_test_worker(self, base, model, key, provider_name):
        if provider_name == "Google Translate (Fast)":
            try:
                translated = self.request_google_translate_batch(
                    {"url": base, "model": model}, ["Hello, how are you?"]
                )[0]
                self.events.put(("api_test_ok", "Google Translate connected. Test translation: " + translated))
            except Exception as exc:
                self.events.put(("api_test_error", "Google Translate test failed: " + str(exc)))
            return

        if provider_name == "MyMemory Translation":
            try:
                translated = self.request_mymemory_translation({"url": base, "key": key}, "Hello, how are you?")
                self.events.put(("api_test_ok", "MyMemory connected. Test translation: " + translated))
            except Exception as exc:
                self.events.put(("api_test_error", "MyMemory test failed: " + str(exc)))
            return

        if provider_name == "Cloudflare Workers AI":
            provider = {"url": base, "model": model, "key": key}
            try:
                translated = self.request_cloudflare_translation(provider, "Hello, how are you?")
                self.events.put(("api_test_ok", "Cloudflare connection successful. Test translation: " + translated))
            except Exception as exc:
                self.events.put(("api_test_error", "Cloudflare test failed: " + str(exc)))
            return

        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Reply with only the word OK."}],
        }).encode("utf-8")
        request = urllib.request.Request(
            base + "/chat/completions", data=body,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not data.get("choices"):
                raise RuntimeError("Provider returned an unexpected response.")
            self.events.put(("api_test_ok", "Connection successful. Your API is ready."))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:350]
            self.events.put(("api_test_error", f"API error {exc.code}: {detail}"))
        except Exception as exc:
            self.events.put(("api_test_error", "Connection failed: " + str(exc)))

    def show_main(self):
        self.on_setup_screen = False
        self.clear_root()
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        shell = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(shell, fg_color=SIDEBAR, corner_radius=0, width=238)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=22, pady=(25, 34))
        logo = ctk.CTkFrame(brand, fg_color=ACCENT, width=42, height=42, corner_radius=12)
        logo.pack(side="left")
        logo.pack_propagate(False)
        self.make_label(logo, "H", "#ffffff", 22, "bold").place(relx=0.5, rely=0.5, anchor="center")
        title = ctk.CTkFrame(brand, fg_color="transparent")
        title.pack(side="left", padx=10)
        self.make_label(title, "HADOC SUB", TEXT, 14, "bold").pack(anchor="w")
        self.make_label(title, "SUBTITLE STUDIO", MUTED, 8, "bold").pack(anchor="w")

        self.make_label(sidebar, "WORKSPACE", "#64758d", 9, "bold").pack(anchor="w", padx=22, pady=(0, 10))
        self.make_button(sidebar, "▤    SRT Translator", lambda: None, primary=True, height=43).pack(fill="x", padx=14, pady=4)
        self.make_button(sidebar, "⚙    API Settings", self.open_settings, height=43).pack(fill="x", padx=14, pady=4)

        spacer = ctk.CTkFrame(sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)
        api_card = ctk.CTkFrame(sidebar, fg_color="#12251f", corner_radius=12, border_width=1, border_color="#254536")
        api_card.pack(fill="x", padx=14, pady=(0, 18))
        self.make_label(api_card, "●  API CONFIGURED", GREEN, 10, "bold").pack(anchor="w", padx=12, pady=(12, 4))
        self.make_label(api_card, f"{len(self.providers)} providers ready", "#b3c8bc", 10).pack(anchor="w", padx=12, pady=(0, 12))
        self.make_label(sidebar, "HADOC SUB  v" + VERSION, "#64758d", 9, "bold").pack(anchor="w", padx=22, pady=(0, 20))

        content = ctk.CTkFrame(shell, fg_color=BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew", padx=32, pady=25)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(content, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        top.grid_columnconfigure(0, weight=1)
        title_area = ctk.CTkFrame(top, fg_color="transparent")
        title_area.grid(row=0, column=0, sticky="w")
        self.make_label(title_area, "Subtitle Studio", TEXT, 27, "bold").pack(anchor="w")
        self.make_label(title_area, "Translate, review and export your movie subtitles.", MUTED, 12).pack(anchor="w", pady=(4, 0))
        self.make_button(top, "⚙  Settings", self.open_settings, height=39, width=125).grid(row=0, column=1, sticky="e")

        body = ctk.CTkFrame(content, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=0, minsize=315)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        file_card = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        file_card.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        file_card.grid_columnconfigure(0, weight=1)
        self.make_label(file_card, "01  SOURCE SUBTITLE", "#c8d4e5", 11, "bold").grid(row=0, column=0, sticky="w", padx=20, pady=(20, 6))
        self.make_label(file_card, "Open an English .srt file from your PC.", MUTED, 11, anchor="w", wraplength=270).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 17))

        drop = ctk.CTkFrame(file_card, fg_color=PANEL_3, corner_radius=13, border_width=1, border_color="#31435c")
        drop.grid(row=2, column=0, sticky="ew", padx=17, pady=(0, 15))
        self.make_label(drop, "＋", ACCENT, 34, "bold").pack(pady=(18, 4))
        self.make_label(drop, "Choose subtitle file", TEXT, 13, "bold").pack()
        self.make_label(drop, "SRT format  •  UTF-8 supported", MUTED, 10).pack(pady=(4, 14))
        self.make_button(drop, "Browse SRT file", self.open_file, primary=True, height=40, width=190).pack(pady=(0, 18))

        self.make_label(file_card, "SELECTED FILE", "#8fa1b8", 9, "bold").grid(row=3, column=0, sticky="w", padx=20, pady=(3, 5))
        self.file_name_label = self.make_label(file_card, self.file_text.get(), TEXT, 11, anchor="w", wraplength=270, justify="left")
        self.file_name_label.grid(row=4, column=0, sticky="ew", padx=20)
        work_card = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        work_card.grid(row=0, column=1, sticky="nsew")
        work_card.grid_columnconfigure(0, weight=1)
        work_card.grid_rowconfigure(2, weight=1, minsize=190)
        work_head = ctk.CTkFrame(work_card, fg_color="transparent")
        work_head.grid(row=0, column=0, sticky="ew", padx=19, pady=(18, 12))
        self.make_label(work_head, "02  TRANSLATION WORKSPACE", TEXT, 12, "bold").pack(anchor="w")
        self.make_label(work_head, "Review the original and translated subtitle lines.", MUTED, 10).pack(anchor="w", pady=(3, 0))

        toolbar = ctk.CTkFrame(work_card, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=17, pady=(0, 9))
        self.make_label(toolbar, "SUBTITLES", "#91a4bd", 9, "bold").pack(side="left", padx=(0, 9))
        self.make_button(toolbar, "＋ Open SRT", self.open_file, height=35, width=105).pack(side="left", padx=(0, 6))
        self.start_button = self.make_button(toolbar, "▶  Start translation", self.start_translation, primary=True, height=35, width=150)
        self.start_button.pack(side="left", padx=(0, 6))
        self.make_button(toolbar, "↓  Save SRT", self.save_file, height=35, width=112).pack(side="left", padx=(0, 8))
        self.search_entry = self.make_entry(toolbar, self.search_text, "Search…", height=35)
        self.search_entry.pack(side="right", fill="x", expand=True)

        table_wrap = ctk.CTkFrame(work_card, fg_color=PANEL_3, corner_radius=10)
        table_wrap.grid(row=2, column=0, sticky="nsew", padx=17)
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)
        self.build_table(table_wrap)

        editor = ctk.CTkFrame(work_card, fg_color=PANEL_3, corner_radius=11)
        editor.grid(row=3, column=0, sticky="ew", padx=17, pady=(12, 13))
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_columnconfigure(1, weight=1)
        edtop = ctk.CTkFrame(editor, fg_color="transparent")
        edtop.grid(row=0, column=0, columnspan=2, sticky="ew", padx=13, pady=(10, 7))
        self.make_label(edtop, "SELECTED SUBTITLE", "#9bacbf", 9, "bold").pack(side="left")
        self.selected_label = self.make_label(edtop, "No line selected", MUTED, 9)
        self.selected_label.pack(side="right")
        self.make_label(editor, "ENGLISH", MUTED, 9, "bold").grid(row=1, column=0, sticky="w", padx=13, pady=(0, 5))
        self.make_label(editor, "SINHALA · EDITABLE", MUTED, 9, "bold").grid(row=1, column=1, sticky="w", padx=13, pady=(0, 5))
        self.original_box = ctk.CTkTextbox(editor, height=52, corner_radius=8, fg_color="#111b29",
                                           text_color="#b8c5d7", border_width=1, border_color=BORDER,
                                           font=ctk.CTkFont(family=FONT, size=11), wrap="word")
        self.original_box.grid(row=2, column=0, sticky="ew", padx=(13, 6), pady=(0, 10))
        self.original_box.configure(state="disabled")
        self.translated_box = ctk.CTkTextbox(editor, height=52, corner_radius=8, fg_color="#111b29",
                                             text_color=TEXT, border_width=1, border_color=BORDER,
                                             font=ctk.CTkFont(family="Nirmala UI", size=12), wrap="word")
        self.translated_box.grid(row=2, column=1, sticky="ew", padx=(6, 13), pady=(0, 10))
        self.make_button(editor, "Apply edit", self.apply_edit, height=34, width=108).grid(row=3, column=1, sticky="e", padx=13, pady=(0, 10))

        progress_area = ctk.CTkFrame(content, fg_color="transparent")
        progress_area.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        progress_area.grid_columnconfigure(0, weight=1)
        self.status_label = self.make_label(progress_area, self.status_text.get(), MUTED, 10)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress_percent = self.make_label(progress_area, "0%", ACCENT, 10, "bold")
        self.progress_percent.grid(row=0, column=1, sticky="e")
        self.progress_bar = ctk.CTkProgressBar(progress_area, height=7, corner_radius=4,
                                               progress_color=ACCENT, fg_color=BORDER)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self.progress_bar.set(0)

        self.refresh_table()
        self.update_stats_cards()

    def stat_card(self, parent, column, title, value, caption):
        card = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=13, border_width=1, border_color=BORDER, height=88)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 7, 7 if column < 2 else 0))
        card.grid_propagate(False)
        self.make_label(card, title, "#8fa1b8", 9, "bold").pack(anchor="w", padx=15, pady=(12, 3))
        value_label = self.make_label(card, value, TEXT, 15, "bold")
        value_label.pack(anchor="w", padx=15)
        self.make_label(card, caption, MUTED, 9).pack(anchor="w", padx=15, pady=(1, 8))
        if title == "SUBTITLE LINES":
            self.stat_count_label = value_label
        elif title == "SOURCE FILE":
            self.stat_source_label = value_label
        elif title == "TRANSLATION":
            self.stat_provider_label = value_label

    def update_stats_cards(self):
        if hasattr(self, "stat_count_label"):
            self.stat_count_label.configure(text=str(len(self.items)))
            self.stat_source_label.configure(text=self.source_path.name if self.source_path else "No file loaded")
            self.stat_provider_label.configure(text=f"{len(self.providers)} APIs")

    def build_table(self, parent):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Hadoc.Treeview", background=PANEL_3, fieldbackground=PANEL_3,
                        foreground=TEXT, rowheight=34, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Hadoc.Treeview.Heading", background="#1c2a3e", foreground="#aebcd0",
                        relief="flat", borderwidth=0, font=("Segoe UI", 8, "bold"), padding=8)
        style.map("Hadoc.Treeview", background=[("selected", "#5b3042")], foreground=[("selected", "#ffffff")])
        self.table = ttk.Treeview(parent, columns=("n", "time", "english", "sinhala"),
                                  show="headings", style="Hadoc.Treeview", selectmode="browse", height=9)
        for col, heading in zip(("n", "time", "english", "sinhala"),
                                ("#", "TIMESTAMP", "ENGLISH", "SINHALA")):
            self.table.heading(col, text=heading)
        self.table.column("n", width=45, minwidth=40, stretch=False, anchor="center")
        self.table.column("time", width=150, minwidth=135, stretch=False)
        self.table.column("english", width=240, minwidth=100, stretch=True)
        self.table.column("sinhala", width=240, minwidth=100, stretch=True)
        scroll = ctk.CTkScrollbar(parent, orientation="vertical", command=self.table.yview, fg_color="transparent", button_color="#31435c", button_hover_color="#506681")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.table.bind("<<TreeviewSelect>>", self.select_row)

    def checkpoint_file_for(self, source_path):
        identity = os.path.normcase(os.path.abspath(str(source_path))).encode("utf-8")
        name = hashlib.sha256(identity).hexdigest() + ".json"
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        return self.progress_dir / name

    def restore_checkpoint(self):
        if not self.source_path:
            return 0
        try:
            checkpoint = self.checkpoint_file_for(self.source_path)
            if not checkpoint.exists():
                return 0
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            if data.get("fingerprint") != self.source_fingerprint:
                return 0
            saved_rows = data.get("rows", [])
            if len(saved_rows) != len(self.items):
                return 0
            restored = 0
            for index, (saved, current) in enumerate(zip(saved_rows, self.items)):
                if (saved.get("number") != current.number or
                        saved.get("timing") != current.timing or
                        saved.get("original") != current.original):
                    return 0
                value = saved.get("translated", "")
                if isinstance(value, str) and value.strip():
                    current.translated = value
                    restored += 1
            return restored
        except (OSError, ValueError, TypeError, AttributeError):
            return 0

    def write_checkpoint(self, source_path, fingerprint, rows, translations):
        if not source_path or not fingerprint:
            return
        checkpoint = self.checkpoint_file_for(source_path)
        payload = {
            "source_path": str(source_path),
            "fingerprint": fingerprint,
            "saved_at": time.time(),
            "rows": [
                {
                    "number": row[0],
                    "timing": row[1],
                    "original": row[2],
                    "translated": translations.get(index, ""),
                }
                for index, row in enumerate(rows)
            ],
        }
        temp = checkpoint.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp.replace(checkpoint)

    def remove_checkpoint(self):
        if not self.source_path:
            return
        try:
            checkpoint = self.checkpoint_file_for(self.source_path)
            checkpoint.unlink(missing_ok=True)
        except OSError:
            pass

    def write_current_checkpoint(self):
        if not self.source_path or not getattr(self, "source_fingerprint", None):
            return
        rows = [(item.number, item.timing, item.original) for item in self.items]
        translations = {i: item.translated for i, item in enumerate(self.items) if item.translated.strip()}
        try:
            self.write_checkpoint(self.source_path, self.source_fingerprint, rows, translations)
        except OSError:
            pass

    def open_file(self):
        if self.busy:
            return
        name = filedialog.askopenfilename(
            title="Open English SRT",
            filetypes=[("SubRip subtitle", "*.srt"), ("Text files", "*.txt"), ("All files", "*.*")]
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
        try:
            self.source_fingerprint = source_fingerprint(self.source_path)
        except OSError as exc:
            messagebox.showerror("Could not read subtitle", str(exc))
            return
        restored = self.restore_checkpoint()
        self.file_text.set(self.source_path.name + "  •  " + f"{len(self.items):,} subtitles")
        self.file_name_label.configure(text=self.file_text.get())
        self.count_text.set(str(len(self.items)))
        self.selected = None
        self.clear_editor()
        self.refresh_table()
        self.update_stats_cards()
        self.update_translation_progress()
        if restored:
            self.set_status(
                f"Restored {restored:,}/{len(self.items):,} saved translations. Click Start translation to resume.",
                "success"
            )
        else:
            self.set_status(f"Loaded {len(self.items):,} subtitle entries", "success")

    def refresh_table(self):
        if not hasattr(self, "table"):
            return
        query = self.search_text.get().strip().casefold()
        self.table.delete(*self.table.get_children())
        for index, item in enumerate(self.items):
            if query and query not in item.original.casefold() and query not in item.translated.casefold() and query not in item.number:
                continue
            self.table.insert("", "end", iid=str(index), values=(
                item.number, item.timing, item.original.replace("\n", " / "),
                item.translated.replace("\n", " / ") if item.translated else "—"
            ))

    def clear_editor(self):
        self.selected_label.configure(text="No line selected")
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.configure(state="disabled")
        self.translated_box.delete("1.0", "end")

    def select_row(self, _event=None):
        selection = self.table.selection()
        if not selection:
            return
        self.selected = int(selection[0])
        item = self.items[self.selected]
        self.selected_label.configure(text=f"#{item.number}  •  {item.timing}")
        self.original_box.configure(state="normal")
        self.original_box.delete("1.0", "end")
        self.original_box.insert("1.0", item.original)
        self.original_box.configure(state="disabled")
        self.translated_box.delete("1.0", "end")
        self.translated_box.insert("1.0", item.translated)

    def apply_edit(self):
        if self.selected is None:
            return
        if self.busy:
            messagebox.showinfo("Translation in progress", "You can edit subtitle lines after the current translation finishes.")
            return
        self.items[self.selected].translated = self.translated_box.get("1.0", "end-1c").strip()
        self.refresh_table()
        if self.table.exists(str(self.selected)):
            self.table.selection_set(str(self.selected))
            self.table.see(str(self.selected))
        self.update_translation_progress()
        self.write_current_checkpoint()
        self.set_status(f"Subtitle #{self.items[self.selected].number} updated", "success")

    def update_translation_progress(self):
        done = sum(bool(item.translated.strip()) for item in self.items)
        total = len(self.items)
        pct = round(done * 100 / total) if total else 0
        self.translated_text.set(str(done))
        self.progress_bar.set(pct / 100)
        self.progress_percent.configure(text=f"{pct}%")

    def set_status(self, text, mode="ready"):
        self.status_text.set(text)
        if hasattr(self, "status_label"):
            self.status_label.configure(text=text)
        if hasattr(self, "progress_percent"):
            color = GREEN if mode == "success" else (YELLOW if mode == "working" else ACCENT)
            self.progress_percent.configure(text_color=color)

    def start_translation(self):
        if self.busy:
            return
        if not self.items:
            messagebox.showinfo("Load subtitles first", "Open an English SRT file before starting translation.")
            return
        if not self.providers:
            messagebox.showwarning("No API providers", "Open API Settings and add at least one provider.")
            return
        pending = [(i, item.original) for i, item in enumerate(self.items) if not item.translated.strip()]
        if not pending:
            messagebox.showinfo("Already translated", "All subtitle lines already have Sinhala text. Save your SRT file.")
            return
        if not self.source_path:
            messagebox.showwarning("No source file", "Open the original SRT file again before translating.")
            return
        providers = [dict(item) for item in self.providers]
        all_rows = [(item.number, item.timing, item.original) for item in self.items]
        existing = {i: item.translated for i, item in enumerate(self.items) if item.translated.strip()}
        try:
            fingerprint = self.source_fingerprint
        except AttributeError:
            fingerprint = source_fingerprint(self.source_path)
            self.source_fingerprint = fingerprint

        self.busy = True
        self.start_button.configure(state="disabled", text="Translating…")
        self.set_status(
            f"Starting {len(pending):,} remaining lines with {len(providers)} API provider(s)…",
            "working"
        )
        self.progress_bar.set(sum(bool(item.translated.strip()) for item in self.items) / len(self.items))
        self.progress_percent.configure(text=f"{round(sum(bool(item.translated.strip()) for item in self.items) * 100 / len(self.items))}%")
        source_path = str(self.source_path)
        threading.Thread(
            target=self.translation_worker,
            args=(pending, providers, source_path, fingerprint, all_rows, existing),
            daemon=True
        ).start()

    def translation_worker(self, snapshot, providers, source_path, fingerprint, all_rows, existing):
        # Smaller batches reduce per-request token spikes. Provider fallback protects the job
        # when one service returns 429, a temporary server error, or an invalid model/key.
        batch_size = 20 if providers and providers[0].get("name") == "Google Translate (Fast)" else 10
        blocked_providers = set()
        translations = dict(existing)
        try:
            total = len(snapshot)
            completed = 0
            last_provider = None
            for offset in range(0, total, batch_size):
                batch = snapshot[offset:offset + batch_size]
                result, provider_name = self.translate_with_pool(batch, providers, blocked_providers)
                translations.update(result)
                completed += len(batch)

                # Persist after every successful batch so a closed app can resume safely.
                try:
                    self.write_checkpoint(source_path, fingerprint, all_rows, translations)
                except OSError as checkpoint_error:
                    self.events.put(("checkpoint_warning", str(checkpoint_error)))

                if provider_name != last_provider:
                    self.events.put(("provider_used", provider_name))
                    last_provider = provider_name
                for index, value in result.items():
                    self.events.put(("translated_row", index, value))
                self.events.put(("translation_progress", completed, total))

            self.events.put(("translation_complete", total))
        except Exception as exc:
            self.events.put(("translation_error", str(exc)))

    def translate_with_pool(self, batch, providers, blocked_providers):
        failures = []
        for index, provider in enumerate(providers):
            if index in blocked_providers:
                continue
            try:
                result = self.translate_batch(batch, provider)
                return result, provider["name"]
            except Exception as exc:
                blocked_providers.add(index)
                failures.append(f"{provider['name']}: {exc}")
                self.events.put(("provider_fallback", provider["name"], str(exc)))
                continue

        if not failures:
            detail = "Every configured provider has already been marked unavailable for this run."
        else:
            detail = "\n".join("• " + item for item in failures)
        raise RuntimeError(
            "All configured APIs are currently unavailable for this translation batch.\n\n"
            + detail
            + "\n\nHADOC Sub has saved completed subtitle batches. Add another provider or wait for a quota reset, "
              "then click Start translation again to resume only the remaining lines."
        )

    def request_google_translate_batch(self, provider, texts):
        language_pair = provider.get("model", "en|si")
        try:
            source, target = language_pair.split("|", 1)
        except ValueError as exc:
            raise RuntimeError("Google Translate language pair must use source|target format.") from exc

        url = build_google_translate_url(provider["url"], texts, source, target)
        if len(url.encode("utf-8")) > 7000:
            raise RuntimeError("Google Translate request is too long; the subtitle batch must be reduced.")

        # Keep a small gap between calls; bursts can trigger Google's anti-bot protection.
        last_request = getattr(self, "google_last_request", 0.0)
        wait = 0.15 - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        self.google_last_request = time.monotonic()

        request = urllib.request.Request(
            url,
            headers={
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://translate.google.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/157.0.0.0 Safari/537.36"
                ),
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 429:
                raise RuntimeError("Google Translate web endpoint rate-limited this request. " + detail) from exc
            if exc.code in (401, 403):
                raise RuntimeError("Google Translate web endpoint blocked this request. " + detail) from exc
            raise RuntimeError(f"Google Translate returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Google Translate network or timeout error: " + str(exc)) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Google Translate returned invalid JSON: " + str(exc)) from exc

        try:
            return extract_google_translate_translations(data, len(texts))
        except Exception as exc:
            raise RuntimeError("Could not read Google Translate response: " + str(exc)) from exc

    def translate_google_batch(self, batch, provider):
        # Google Translate's web endpoint accepts repeated q parameters, so several
        # subtitle entries can be translated in one HTTP request.
        groups = []
        current = []
        source, target = provider.get("model", "en|si").split("|", 1)
        line_parts = {}

        for index, text in batch:
            line_parts[index] = {}
            source_lines = text.split("\n")
            for line_number, line in enumerate(source_lines):
                if not line.strip():
                    line_parts[index][line_number] = []
                    continue
                chunks = (
                    split_mymemory_chunks(line, max_bytes=1800)
                    if len(line.encode("utf-8")) > 1800
                    else [line]
                )
                line_parts[index][line_number] = []
                for chunk in chunks:
                    candidate = current + [(index, line_number, chunk)]
                    candidate_url = build_google_translate_url(
                        provider["url"], [entry[2] for entry in candidate], source, target
                    )
                    if current and len(candidate_url.encode("utf-8")) > 6500:
                        groups.append(current)
                        current = [(index, line_number, chunk)]
                    else:
                        current = candidate

        if current:
            groups.append(current)

        translated_parts = {index: {} for index, _ in batch}
        for group in groups:
            translated = self.request_google_translate_batch(
                provider, [text for _, _, text in group]
            )
            for (index, line_number, _), value in zip(group, translated):
                translated_parts[index].setdefault(line_number, []).append(value)

        results = {}
        for index, _ in batch:
            lines = []
            for line_number in sorted(line_parts[index]):
                parts = translated_parts[index].get(line_number, [])
                lines.append(" ".join(parts).strip())
            results[index] = "\n".join(lines)
        return results

    def request_mymemory_chunk(self, provider, text):
        url = build_mymemory_url(
            provider["url"], text, provider.get("key", ""), provider.get("model", "en-US|si-LK")
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "HADOC-Sub/" + VERSION,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 429:
                raise RuntimeError("MyMemory rate limit reached. " + detail) from exc
            raise RuntimeError(f"MyMemory returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("MyMemory network or timeout error: " + str(exc)) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("MyMemory returned invalid JSON: " + str(exc)) from exc
        return extract_mymemory_translation(data)

    def request_mymemory_translation(self, provider, text):
        if len(text.encode("utf-8")) <= 450:
            return self.request_mymemory_chunk(provider, text)

        translated_lines = []
        for line in text.splitlines():
            if not line.strip():
                translated_lines.append("")
                continue
            chunks = split_mymemory_chunks(line)
            translations = [self.request_mymemory_chunk(provider, chunk) for chunk in chunks]
            translated_lines.append(" ".join(translations))
        return "\n".join(translated_lines)

    def _translate_mymemory_item(self, item, provider):
        index, text = item
        return index, self.request_mymemory_translation(provider, text)

    def translate_mymemory_batch(self, batch, provider):
        # Repeated movie subtitles are translated once per app session and reused.
        pending = {}
        results = {}
        for index, text in batch:
            with self.mymemory_cache_lock:
                cached = self.mymemory_cache.get(text)
            if cached:
                results[index] = cached
            else:
                pending.setdefault(text, []).append(index)

        if pending:
            unique_texts = list(pending)
            with ThreadPoolExecutor(max_workers=min(4, len(unique_texts))) as executor:
                translated_rows = executor.map(
                    lambda text: self.request_mymemory_translation(provider, text),
                    unique_texts,
                )
                for text, translated in zip(unique_texts, translated_rows):
                    with self.mymemory_cache_lock:
                        self.mymemory_cache[text] = translated
                    for index in pending[text]:
                        results[index] = translated
        return results

    def request_cloudflare_translation(self, provider, text):
        body = json.dumps({
            "text": text,
            "source_lang": "en",
            "target_lang": "si",
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            cloudflare_model_endpoint(provider["url"], provider["model"]),
            data=body,
            headers={
                "Authorization": "Bearer " + provider["key"],
                "Content-Type": "application/json",
                "User-Agent": "HADOC-Sub/" + VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:700]
            if exc.code == 429:
                raise RuntimeError("Cloudflare Workers AI quota or rate limit reached. " + detail) from exc
            if exc.code in (401, 403):
                raise RuntimeError("Cloudflare token rejected or missing Workers AI permission. " + detail) from exc
            raise RuntimeError(f"Cloudflare Workers AI returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Cloudflare network or timeout error: " + str(exc)) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("Cloudflare returned invalid JSON: " + str(exc)) from exc

        try:
            return extract_cloudflare_translation(data)
        except Exception as exc:
            raise RuntimeError("Could not read Cloudflare translation: " + str(exc)) from exc

    def _translate_cloudflare_item(self, item, provider):
        index, text = item
        translated = self.request_cloudflare_translation(provider, text)
        return index, translated

    def translate_cloudflare_batch(self, batch, provider):
        # Keep concurrency conservative to respect the provider rate limit while
        # allowing subtitle lines to translate faster than a fully serial loop.
        with ThreadPoolExecutor(max_workers=min(4, len(batch))) as executor:
            pairs = list(executor.map(
                lambda item: self._translate_cloudflare_item(item, provider), batch
            ))
        return dict(pairs)

    def translate_batch(self, batch, provider):
        if provider.get("name") == "Google Translate (Fast)":
            return self.translate_google_batch(batch, provider)
        if provider.get("name") == "MyMemory Translation":
            return self.translate_mymemory_batch(batch, provider)
        if provider.get("name") == "Cloudflare Workers AI":
            return self.translate_cloudflare_batch(batch, provider)

        payload = [{"index": index + 1, "text": text} for index, text in batch]
        system = (
            "You are a professional English-to-Sinhala movie subtitle translator. "
            "Translate into natural, concise, emotionally appropriate Sri Lankan Sinhala. "
            "Use everyday spoken Sinhala that fits the scene and subtitle reading speed. "
            "Preserve character names, meaning, tone, line breaks when practical, and formatting tags exactly, "
            "including <i>, </i>, and {\\\\an8}. Do not add explanations, speaker labels, quotes, or notes. "
            "Return ONLY valid JSON in this exact shape: "
            '{"translations":[{"index":1,"text":"Sinhala translation"}]}. '
            "Include every supplied index exactly once."
        )
        user = "Translate these subtitle items from English to Sinhala. Keep indices unchanged. JSON only:\n"
        user += json.dumps(payload, ensure_ascii=False)
        body = json.dumps({
            "model": provider["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            provider["url"].rstrip("/") + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + provider["key"],
                "Content-Type": "application/json",
                "User-Agent": "HADOC-Sub/" + VERSION,
                "HTTP-Referer": "https://github.com/KyZer-HADOC/HADOC-Sub",
                "X-Title": "HADOC Sub",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=150) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:700]
            retry_after = parse_retry_seconds(exc.headers)
            if exc.code == 429:
                extra = f" Retry window: about {retry_after}s." if retry_after else ""
                raise ProviderFailure(
                    provider["name"], exc.code,
                    "Rate limit or quota reached." + extra + " " + detail,
                    retry_after
                ) from exc
            if exc.code in (401, 403):
                raise ProviderFailure(
                    provider["name"], exc.code,
                    "Authentication or access denied. Check this API key and model access. " + detail
                ) from exc
            raise ProviderFailure(
                provider["name"], exc.code,
                f"Provider returned HTTP {exc.code}. " + detail,
                retry_after
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderFailure(
                provider["name"], None, "Network or timeout error: " + str(exc)
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderFailure(
                provider["name"], None, "Provider returned invalid JSON: " + str(exc)
            ) from exc

        try:
            answer = data["choices"][0]["message"]["content"]
            result = parse_json_response(answer)
        except Exception as exc:
            raise ProviderFailure(
                provider["name"], None, "Could not read a valid translation response: " + str(exc)
            ) from exc

        rows = result.get("translations")
        if not isinstance(rows, list):
            raise ProviderFailure(provider["name"], None, "The model response did not include a translations list.")
        expected = {index + 1 for index, _ in batch}
        mapped = {}
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("text"), str):
                try:
                    index = int(row.get("index"))
                except (TypeError, ValueError):
                    continue
                if index in expected and row["text"].strip():
                    mapped[index - 1] = row["text"].strip()
        missing = expected - {index + 1 for index in mapped}
        if missing:
            raise ProviderFailure(
                provider["name"], None,
                "The model omitted subtitle item(s): " + ", ".join(map(str, sorted(missing))) + "."
            )
        return mapped

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "api_test_ok":
                    self.setup_status.set(event[1])
                    if self.on_setup_screen and hasattr(self, "setup_status_label"):
                        self.setup_status_label.configure(text=event[1], text_color=GREEN)
                elif kind == "api_test_error":
                    self.setup_status.set(event[1])
                    if hasattr(self, "setup_status_label") and self.setup_status_label.winfo_exists():
                        self.setup_status_label.configure(text=event[1], text_color=YELLOW)
                elif kind == "provider_fallback":
                    provider_name, reason = event[1], event[2]
                    self.set_status(
                        f"{provider_name} unavailable ({reason[:100]}). Switching to next API…",
                        "working"
                    )
                elif kind == "provider_used":
                    self.set_status(f"Translating with {event[1]}…", "working")
                elif kind == "checkpoint_warning":
                    self.set_status("Warning: could not save resume data. " + event[1], "ready")
                elif kind == "translated_row":
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
                elif kind == "translation_progress":
                    _, completed, total = event
                    pct = round(completed * 100 / total) if total else 0
                    self.progress_bar.set(pct / 100)
                    self.progress_percent.configure(text=f"{pct}%")
                    self.status_text.set(f"Processed {completed:,} of {total:,} remaining subtitle lines")
                    self.status_label.configure(text=self.status_text.get())
                    self.update_translation_progress()
                elif kind == "translation_complete":
                    total = event[1]
                    self.busy = False
                    self.start_button.configure(state="normal", text="▶   Start translation")
                    self.progress_bar.set(1)
                    self.progress_percent.configure(text="100%", text_color=GREEN)
                    translated_total = sum(bool(item.translated.strip()) for item in self.items)
                    self.status_text.set(f"Translation complete • {translated_total:,}/{len(self.items):,} lines")
                    self.status_label.configure(text=self.status_text.get())
                    messagebox.showinfo(
                        "Translation complete",
                        f"Completed {total:,} remaining subtitle lines.\n"
                        f"Total Sinhala lines: {translated_total:,}/{len(self.items):,}.\n\n"
                        "Review the translation and click Save SRT."
                    )
                elif kind == "translation_error":
                    self.busy = False
                    self.start_button.configure(state="normal", text="▶   Start translation")
                    self.status_text.set("Translation stopped • completed batches were saved")
                    self.status_label.configure(text=self.status_text.get())
                    self.progress_percent.configure(text_color=YELLOW)
                    messagebox.showerror("Translation paused", event[1])
        except queue.Empty:
            pass
        self.root.after(120, self.poll_events)

    def save_file(self):
        if not self.items:
            messagebox.showinfo("Nothing to save", "Open an SRT file first.")
            return
        if self.busy:
            messagebox.showwarning("Translation in progress", "Wait for translation to finish before saving.")
            return
        if self.selected is not None:
            self.apply_edit()
        default_name = self.source_path.stem + "_si.srt" if self.source_path else "subtitles_si.srt"
        folder = str(self.source_path.parent) if self.source_path else str(Path.home())
        name = filedialog.asksaveasfilename(
            title="Save Sinhala SRT", initialdir=folder, initialfile=default_name,
            defaultextension=".srt", filetypes=[("SubRip subtitles", "*.srt")]
        )
        if not name:
            return
        output = "\n\n".join(
            f"{item.number}\n{item.timing}\n{item.translated if item.translated.strip() else item.original}"
            for item in self.items
        ) + "\n"
        try:
            Path(name).write_text(output, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Could not save file", str(exc))
            return
        if all(item.translated.strip() for item in self.items):
            self.remove_checkpoint()
        else:
            self.write_current_checkpoint()
        self.set_status("Saved " + Path(name).name, "success")
        messagebox.showinfo("Saved successfully", "Sinhala SRT saved to:\n" + name)


def main():
    root = ctk.CTk()
    HadocSub(root)
    root.mainloop()


if __name__ == "__main__":
    main()
