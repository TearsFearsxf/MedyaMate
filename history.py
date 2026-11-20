"""
Geçmiş ve URL geçmişi yönetimi (JSON tabanlı).
"""
import json
import os
import sys
from datetime import datetime

if getattr(sys, "frozen", False):
    _data_root = os.environ.get("APPDATA") or os.path.expanduser("~")
    _data_dir = os.path.join(_data_root, "MedyaMate")
else:
    _data_dir = os.path.dirname(os.path.abspath(__file__))
os.makedirs(_data_dir, exist_ok=True)
HISTORY_FILE = os.path.join(_data_dir, "history.json")
MAX_URL_HISTORY = 50
MAX_DOWNLOADS   = 200


def _load() -> dict:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"urls": [], "downloads": [], "settings": {}}


def _save(data: dict):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ------------------------------------------------------------------
# URL Geçmişi (Girilmiş linkler)
# ------------------------------------------------------------------

def add_url(url: str, title: str = ""):
    data = _load()
    urls = data.get("urls", [])
    # Aynı URL varsa güncelle, yoksa başa ekle
    urls = [u for u in urls if u["url"] != url]
    urls.insert(0, {
        "url":   url,
        "title": title or url,
        "date":  datetime.now().strftime("%d.%m.%Y %H:%M"),
    })
    data["urls"] = urls[:MAX_URL_HISTORY]
    _save(data)


def get_url_history() -> list:
    return _load().get("urls", [])


def clear_url_history():
    data = _load()
    data["urls"] = []
    _save(data)


# ------------------------------------------------------------------
# İndirme Geçmişi (Tamamlanan dosyalar)
# ------------------------------------------------------------------

def add_download(title: str, file_path: str, fmt: str, quality: str, url: str = ""):
    data = _load()
    dls  = data.get("downloads", [])
    dls.insert(0, {
        "title":     title,
        "file_path": file_path,
        "fmt":       fmt,
        "quality":   quality,
        "url":       url,
        "date":      datetime.now().strftime("%d.%m.%Y %H:%M"),
    })
    data["downloads"] = dls[:MAX_DOWNLOADS]
    _save(data)


def get_downloads() -> list:
    return _load().get("downloads", [])


def clear_downloads():
    data = _load()
    data["downloads"] = []
    _save(data)


# ------------------------------------------------------------------
# Ayarlar (Tema, indirme klasörü vb.)
# ------------------------------------------------------------------

def get_setting(key: str, default=None):
    return _load().get("settings", {}).get(key, default)


def set_setting(key: str, value):
    data = _load()
    if "settings" not in data:
        data["settings"] = {}
    data["settings"][key] = value
    _save(data)
