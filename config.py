"""
Uygulama genelinde kullanılan sabitler ve ayarlar.
"""

APP_NAME = "MedyaMate"
APP_VERSION = "1.0.0"
GITHUB_REPO = "TearsFearsxf/MedyaMate"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Varsayılan indirme klasörü (Masaüstü/MedyaMate İndirilenler)
import os
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "MedyaMate İndirilenler")

# Desteklenen platformlar (yt-dlp zaten bunların hepsini destekliyor)
SUPPORTED_PLATFORMS = [
    {"name": "YouTube",   "icon": "▶",  "color": "#FF0000"},
    {"name": "TikTok",    "icon": "♪",  "color": "#000000"},
    {"name": "Instagram", "icon": "📷", "color": "#C13584"},
    {"name": "Twitter/X", "icon": "✕",  "color": "#1DA1F2"},
    {"name": "Facebook",  "icon": "f",  "color": "#1877F2"},
]

# Kalite seçenekleri
MP3_QUALITIES = [
    {"label": "64 kbps  (Küçük Boyut)",      "value": "64"},
    {"label": "128 kbps (Standart)",          "value": "128"},
    {"label": "192 kbps (İyi Kalite)",        "value": "192"},
    {"label": "256 kbps (Yüksek Kalite)",     "value": "256"},
    {"label": "320 kbps (Stüdyo Kalitesi)",   "value": "320"},
]

MP4_QUALITIES = [
    {"label": "360p  (Veri Tasarrufu)",       "value": "360"},
    {"label": "480p  (Standart)",             "value": "480"},
    {"label": "720p  (HD)",                   "value": "720"},
    {"label": "1080p (Full HD)",              "value": "1080"},
    {"label": "1440p (2K)",                   "value": "1440"},
    {"label": "2160p (4K - Ultra HD)",        "value": "2160"},
    {"label": "En Yüksek Mevcut",             "value": "best"},
]

# WAV/FLAC are lossless containers; their bitrate is determined by the source.
LOSSLESS_QUALITIES = [
    {"label": "En iyi mevcut kaynak", "value": "best"},
]

# Tema renkleri (Koyu - Spotify/Discord tarzı)
THEME = {
    "dark": {
        "bg_primary":    "#0F0F13",
        "bg_secondary":  "#1A1A24",
        "bg_card":       "#22223A",
        "accent":        "#7C3AED",      # Mor (ana vurgu)
        "accent_hover":  "#6D28D9",
        "accent2":       "#10B981",      # Neon yeşil (başarı)
        "text_primary":  "#F0F0F5",
        "text_secondary":"#9090B0",
        "text_muted":    "#505070",
        "border":        "#2A2A45",
        "progress_bg":   "#1A1A24",
        "error":         "#EF4444",
        "warning":       "#F59E0B",
    },
    "light": {
        "bg_primary":    "#F5F5FF",
        "bg_secondary":  "#EEEEF8",
        "bg_card":       "#FFFFFF",
        "accent":        "#7C3AED",
        "accent_hover":  "#6D28D9",
        "accent2":       "#10B981",
        "text_primary":  "#111128",
        "text_secondary":"#444460",
        "text_muted":    "#888898",
        "border":        "#DDDDEF",
        "progress_bg":   "#E0E0F0",
        "error":         "#DC2626",
        "warning":       "#D97706",
    },
}

# İlerleme güncelleme hızı (ms)
PROGRESS_UPDATE_MS = 100

# Eş zamanlı max indirme sayısı
MAX_CONCURRENT_DOWNLOADS = 2
