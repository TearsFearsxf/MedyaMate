"""
Ana Arayüz — CustomTkinter tabanlı modern koyu/açık tema.
"""
import os
import sys
import threading
import subprocess
import shutil
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw
from io import BytesIO
import requests

import history as hist
from config import (APP_NAME, APP_VERSION, GITHUB_REPO, THEME, MP3_QUALITIES, MP4_QUALITIES,
                    LOSSLESS_QUALITIES, DEFAULT_DOWNLOAD_DIR, SUPPORTED_PLATFORMS)
from downloader import Downloader, DownloadTask, fetch_preview, AUDIO_FORMATS, VIDEO_FORMATS
from updater import check_for_update, apply_update, update_ytdlp

# Karanlık mod varsayılan
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

FORMAT_LABELS = {
    "MP3 · Ses": "mp3",
    "M4A · Ses": "m4a",
    "WAV · Ses": "wav",
    "FLAC · Ses": "flac",
    "MP4 · Video": "mp4",
    "MKV · Video": "mkv",
}
FORMAT_LABEL_BY_VALUE = {value: label for label, value in FORMAT_LABELS.items()}


def _resource_path(relative_path: str) -> str:
    """Resolve a bundled asset both in source runs and PyInstaller builds."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


# ══════════════════════════════════════════════════════════════
#  YARDIMCI: Thumbnail → CTkImage
# ══════════════════════════════════════════════════════════════

def pil_to_ctk(pil_img: Image.Image, size=(80, 45)) -> ctk.CTkImage:
    pil_img = pil_img.resize(size, Image.LANCZOS)
    return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)


def rounded_image(pil_img: Image.Image, radius=10) -> Image.Image:
    img  = pil_img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, img.size[0]-1, img.size[1]-1], radius=radius, fill=255)
    img.putalpha(mask)
    return img


# ══════════════════════════════════════════════════════════════
#  KART: Kuyruk satırı
# ══════════════════════════════════════════════════════════════

class DownloadCard(ctk.CTkFrame):
    STATUS_COLORS = {
        DownloadTask.STATUS_QUEUED:      "#9090B0",
        DownloadTask.STATUS_FETCHING:    "#F59E0B",
        DownloadTask.STATUS_DOWNLOADING: "#7C3AED",
        DownloadTask.STATUS_CONVERTING:  "#3B82F6",
        DownloadTask.STATUS_DONE:        "#10B981",
        DownloadTask.STATUS_ERROR:       "#EF4444",
        DownloadTask.STATUS_CANCELLED:   "#6B7280",
    }
    STATUS_LABELS = {
        DownloadTask.STATUS_QUEUED:      "⏳ Sırada",
        DownloadTask.STATUS_FETCHING:    "🔍 Bilgi alınıyor...",
        DownloadTask.STATUS_DOWNLOADING: "⬇ İndiriliyor",
        DownloadTask.STATUS_CONVERTING:  "⚙ Dönüştürülüyor...",
        DownloadTask.STATUS_DONE:        "✅ Tamamlandı",
        DownloadTask.STATUS_ERROR:       "❌ Hata",
        DownloadTask.STATUS_CANCELLED:   "🚫 İptal",
    }

    def __init__(self, master, task: DownloadTask, on_remove=None, **kwargs):
        super().__init__(master, corner_radius=12, fg_color="#1A1A24",
                         border_width=1, border_color="#2A2A45", **kwargs)
        self.task      = task
        self.on_remove = on_remove
        self._thumb_img = None
        self._build()

        # Callback'leri bağla
        task.on_progress = self._update
        task.on_done     = self._on_done
        task.on_error    = self._on_error

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        # Sol: Thumbnail alanı
        self.thumb_label = ctk.CTkLabel(self, text="▶", width=80, height=45,
                                         font=("Arial", 24),
                                         fg_color="#22223A", corner_radius=8)
        self.thumb_label.grid(row=0, column=0, rowspan=3, padx=(12,10), pady=10, sticky="nsew")

        # Başlık
        self.title_lbl = ctk.CTkLabel(self, text=self.task.title,
                                       font=("Segoe UI", 13, "bold"),
                                       anchor="w", wraplength=380)
        self.title_lbl.grid(row=0, column=1, padx=0, pady=(10,0), sticky="ew")

        # Durum + meta
        if self.task.fmt in {"mp3", "m4a"}:
            quality_text = f"{self.task.quality} kbps"
        elif self.task.fmt in VIDEO_FORMATS:
            quality_text = "En yüksek" if self.task.quality == "best" else f"{self.task.quality}p"
        else:
            quality_text = "Kaynak kalitesi"
        meta = f"{self.task.fmt.upper()} • {quality_text}"
        self.meta_lbl = ctk.CTkLabel(self, text=meta,
                                      font=("Segoe UI", 10),
                                      text_color="#9090B0", anchor="w")
        self.meta_lbl.grid(row=1, column=1, padx=0, pady=0, sticky="ew")

        # İlerleme çubuğu
        self.progress = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                            progress_color="#7C3AED",
                                            fg_color="#22223A")
        self.progress.set(0)
        self.progress.grid(row=2, column=1, padx=0, pady=(4,0), sticky="ew")

        # Alt satır: hız / ETA / boyut / durum
        self.info_lbl = ctk.CTkLabel(self, text="⏳ Sırada bekleniyor...",
                                      font=("Segoe UI", 10),
                                      text_color="#9090B0", anchor="w")
        self.info_lbl.grid(row=3, column=1, padx=0, pady=(2,8), sticky="ew")

        # Sağ: Butonlar
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=4, padx=(8,12), pady=10)

        self.cancel_btn = ctk.CTkButton(btn_frame, text="✕", width=32, height=32,
                                         corner_radius=8, fg_color="#2A2A45",
                                         hover_color="#3A3A55",
                                         command=self._cancel)
        self.cancel_btn.pack(pady=(0,4))

        self.folder_btn = ctk.CTkButton(btn_frame, text="📂", width=32, height=32,
                                         corner_radius=8, fg_color="#2A2A45",
                                         hover_color="#3A3A55",
                                         command=self._open_folder,
                                         state="disabled")
        self.folder_btn.pack()

    def _update(self, task: DownloadTask):
        """UI thread'inde çağrılmak üzere after() ile planlanır."""
        self.after(0, self._apply_update)

    def _apply_update(self):
        t = self.task
        # Başlık güncellemesi
        self.title_lbl.configure(text=t.title[:60] + ("..." if len(t.title) > 60 else ""))

        # Thumbnail
        if t.thumbnail and self._thumb_img is None:
            img = rounded_image(t.thumbnail.resize((80, 45), Image.LANCZOS))
            self._thumb_img = ctk.CTkImage(light_image=img, dark_image=img, size=(80, 45))
            self.thumb_label.configure(image=self._thumb_img, text="")

        # İlerleme
        pct = t.percent / 100.0
        self.progress.set(min(pct, 1.0))
        color = self.STATUS_COLORS.get(t.status, "#7C3AED")
        self.progress.configure(progress_color=color)

        # Bilgi etiketi
        label = self.STATUS_LABELS.get(t.status, t.status)
        if t.status == DownloadTask.STATUS_DOWNLOADING:
            info = (f"{label}  {t.percent:.1f}%  •  "
                    f"{t.downloaded} / {t.total_size}  •  "
                    f"⚡ {t.speed}  •  ⏱ {t.eta}")
        elif t.status == DownloadTask.STATUS_DONE:
            info = f"{label}  •  {t.file_path}"
        elif t.status == DownloadTask.STATUS_ERROR:
            info = f"{label}: {t.error_msg[:80]}"
        else:
            info = label
        self.info_lbl.configure(text=info, text_color=color)

    def _on_done(self, task):
        self.after(0, self._apply_update)
        self.after(0, lambda: self.folder_btn.configure(state="normal"))
        self.after(0, lambda: self.cancel_btn.configure(state="disabled"))
        # Windows bildirimi
        self.after(0, lambda: _notify(task.title, "İndirme tamamlandı! Klasörü açmak için tıkla."))
        # Geçmişe ekle
        hist.add_download(task.title, task.file_path, task.fmt, task.quality, task.url)

    def _on_error(self, task):
        self.after(0, self._apply_update)

    def _cancel(self):
        self.task.cancel()
        self.after(100, self._apply_update)

    def _open_folder(self):
        path = self.task.file_path
        if path and os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{path}"')
        else:
            subprocess.Popen(f'explorer "{self.task.out_dir}"')


# ══════════════════════════════════════════════════════════════
#  WINDOWS BİLDİRİMİ (wintoast yoksa geçersiz kıl)
# ══════════════════════════════════════════════════════════════

def _notify(title: str, msg: str):
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, msg, duration=5, threaded=True)
    except Exception:
        pass  # Bildirim desteklenmiyorsa sessizce geç


# ══════════════════════════════════════════════════════════════
#  ANA PENCERE
# ══════════════════════════════════════════════════════════════

class App(ctk.CTk):
    def __init__(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MedyaMate.DesktopApp")
            except Exception:
                pass
        super().__init__()

        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("860x720")
        self.minsize(760, 600)

        # Tema durumu
        saved_theme = hist.get_setting("theme", "dark")
        self._dark = saved_theme == "dark"
        ctk.set_appearance_mode("dark" if self._dark else "light")

        # FFmpeg yolu (PyInstaller ile paketlendiğinde yanında olacak)
        self._ffmpeg = self._find_ffmpeg()

        # İndirici
        self.downloader = Downloader(
            ffmpeg_path=self._ffmpeg,
            max_concurrent=hist.get_setting("concurrent", 2),
        )

        # İndirme klasörü
        self._out_dir = hist.get_setting("out_dir", DEFAULT_DOWNLOAD_DIR)
        self._keep_thumbnail = bool(hist.get_setting("keep_thumbnail", False))

        # Kart listesi
        self._cards: list[DownloadCard] = []
        self._preview_after_id = None
        self._preview_request_id = 0
        self._preview_image = None
        self._preview_url = ""
        self._preview_results = queue.Queue()
        self._preview_data = None
        self._vlc_instance = None
        self._vlc_player = None
        self._tray_icon = None
        self._is_exiting = False

        self._build_ui()
        try:
            icon_path = _resource_path(os.path.join("assets", "medyamate.ico"))
            self.iconbitmap(default=icon_path)
            self._window_icon_image = ImageTk.PhotoImage(
                Image.open(icon_path).convert("RGBA")
            )
            self.iconphoto(True, self._window_icon_image)
        except Exception:
            pass
        self._check_update_bg()
        self.after(100, self._poll_preview_results)
        self.protocol("WM_DELETE_WINDOW", self._close_app)

    # ------------------------------------------------------------------
    # UI İnşası
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Üst Bar ──────────────────────────────────────────────────
        topbar = ctk.CTkFrame(self, height=52, corner_radius=0,
                               fg_color="#12121C")
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(topbar, text=f"  {APP_NAME}",
                     font=("Segoe UI", 16, "bold"),
                     text_color="#7C3AED").grid(row=0, column=0, padx=8, pady=10)

        # Platform ikonları
        icon_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        icon_frame.grid(row=0, column=1, sticky="w", padx=8)
        for p in SUPPORTED_PLATFORMS:
            ctk.CTkLabel(icon_frame, text=p["icon"],
                         font=("Segoe UI", 13),
                         text_color="#505070").pack(side="left", padx=4)

        # Tema butonu
        self.theme_btn = ctk.CTkButton(topbar, text="🌙", width=36, height=36,
                                        corner_radius=18, fg_color="#22223A",
                                        hover_color="#2A2A45",
                                        command=self._toggle_theme)
        self.theme_btn.grid(row=0, column=2, padx=4)

        # Ayarlar butonu
        ctk.CTkButton(topbar, text="⚙", width=36, height=36,
                      corner_radius=18, fg_color="#22223A",
                      hover_color="#2A2A45",
                      command=self._open_settings).grid(row=0, column=3, padx=(0,8))

        # ── URL Giriş Alanı ───────────────────────────────────────────
        url_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#1A1A24")
        url_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        url_frame.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(url_frame, fg_color="transparent")
        inner.grid(row=0, column=0, padx=16, pady=12, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        # URL kutusu + "Panodan Yapıştır"
        entry_row = ctk.CTkFrame(inner, fg_color="transparent")
        entry_row.grid(row=0, column=0, sticky="ew")
        entry_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkTextbox(entry_row, height=72, corner_radius=10,
                                         border_width=1, border_color="#2A2A45",
                                         fg_color="#12121C",
                                         font=("Segoe UI", 12))
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.insert("0.0", "Buraya YouTube, TikTok, Instagram... linkini yapıştır\n"
                                      "(Birden fazla link için alt alta yaz)")
        self.url_entry.bind("<FocusIn>",  self._clear_placeholder)
        self.url_entry.bind("<FocusOut>", self._restore_placeholder)
        self.url_entry.bind("<KeyRelease>", self._schedule_preview, add="+")
        self.url_entry.bind("<<Paste>>", self._preview_after_paste, add="+")

        paste_btn = ctk.CTkButton(entry_row, text="📋 Pano", width=80,
                                   corner_radius=8, height=72,
                                   fg_color="#22223A", hover_color="#2A2A45",
                                   command=self._paste_clipboard)
        paste_btn.grid(row=0, column=1, padx=(8,0))

        self.preview_card = ctk.CTkFrame(inner, fg_color="#12121C", corner_radius=8)
        self.preview_card.grid(row=1, column=0, pady=(8,0), sticky="ew")
        self.preview_card.grid_columnconfigure(1, weight=1)
        placeholder = Image.new("RGB", (120, 68), "#22223A")
        self._preview_placeholder_image = ctk.CTkImage(
            light_image=placeholder, dark_image=placeholder, size=(120, 68),
        )
        self.preview_image_label = ctk.CTkLabel(
            self.preview_card, text="▶", image=self._preview_placeholder_image,
            compound="center", width=120, height=68,
            fg_color="#22223A", corner_radius=6, font=("Arial", 24),
        )
        self.preview_image_label.grid(row=0, column=0, padx=8, pady=8)
        preview_text = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        preview_text.grid(row=0, column=1, padx=(2,10), pady=8, sticky="ew")
        preview_text.grid_columnconfigure(0, weight=1)
        self.preview_title_lbl = ctk.CTkLabel(
            preview_text, text="Önizleme yükleniyor...", anchor="w",
            font=("Segoe UI", 12, "bold"), wraplength=520,
        )
        self.preview_title_lbl.grid(row=0, column=0, sticky="ew")
        self.preview_meta_lbl = ctk.CTkLabel(
            preview_text, text="", anchor="w", text_color="#9090B0",
            font=("Segoe UI", 10),
        )
        self.preview_meta_lbl.grid(row=1, column=0, pady=(3,0), sticky="ew")
        self.preview_video_btn = ctk.CTkButton(
            preview_text, text="▶  İzle", width=100, height=28,
            corner_radius=7, fg_color="#7C3AED", hover_color="#6D28D9",
            command=lambda: self._open_preview("video"), state="disabled",
        )
        self.preview_video_btn.grid(row=2, column=0, pady=(6,0), sticky="w")
        self.preview_audio_btn = ctk.CTkButton(
            preview_text, text="🎧  Dinle", width=100, height=28,
            corner_radius=7, fg_color="#22223A", hover_color="#2A2A45",
            command=lambda: self._open_preview("audio"), state="disabled",
        )
        self.preview_audio_btn.grid(row=2, column=1, padx=(8,0), pady=(6,0), sticky="w")

        self.preview_player_frame = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        self.preview_player_frame.grid(row=1, column=0, columnspan=2, padx=8, pady=(0,8), sticky="ew")
        self.preview_player_frame.grid_columnconfigure(0, weight=1)
        self.preview_video_host = ctk.CTkFrame(
            self.preview_player_frame, fg_color="#050508", height=300, corner_radius=6,
        )
        self.preview_video_host.grid(row=0, column=0, sticky="ew")
        self.preview_video_host.grid_propagate(False)
        self.preview_audio_overlay = ctk.CTkLabel(
            self.preview_video_host, text="🎧 Ses önizlemesi oynuyor",
            font=("Segoe UI", 14, "bold"), text_color="white", fg_color="transparent",
        )
        self.preview_audio_overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.preview_audio_overlay.place_forget()
        player_controls = ctk.CTkFrame(self.preview_player_frame, fg_color="transparent")
        player_controls.grid(row=1, column=0, pady=(6,0), sticky="ew")
        self.preview_toggle_btn = ctk.CTkButton(
            player_controls, text="⏸ Duraklat", width=105, height=28,
            command=self._toggle_preview_playback,
        )
        self.preview_toggle_btn.pack(side="left", padx=(0,6))
        ctk.CTkButton(
            player_controls, text="■ Durdur", width=90, height=28,
            fg_color="#22223A", hover_color="#2A2A45",
            command=self._stop_preview_playback,
        ).pack(side="left")
        ctk.CTkLabel(player_controls, text="Ses", font=("Segoe UI", 10)).pack(side="left", padx=(14,4))
        self.preview_volume = ctk.CTkSlider(
            player_controls, from_=0, to=100, number_of_steps=20,
            command=self._set_preview_volume, width=140,
        )
        self.preview_volume.set(75)
        self.preview_volume.pack(side="left")
        self.preview_player_frame.grid_remove()
        self.preview_card.grid_remove()
        self._preview_image = self._preview_placeholder_image

        # Format / Kalite / Zaman aralığı
        opts_row = ctk.CTkFrame(inner, fg_color="transparent")
        opts_row.grid(row=2, column=0, pady=(10,0), sticky="ew")

        # Format seçimi
        self.fmt_var = ctk.StringVar(value="mp3")
        self.format_label_var = ctk.StringVar(value=FORMAT_LABEL_BY_VALUE["mp3"])
        self.format_menu = ctk.CTkOptionMenu(
            opts_row, values=list(FORMAT_LABELS), variable=self.format_label_var,
            command=self._on_format_change, width=150, corner_radius=8,
        )
        self.format_menu.pack(side="left", padx=(0,12))

        # Kalite dropdown
        self.quality_values = [q["label"] for q in MP3_QUALITIES]
        self.quality_var    = ctk.StringVar(value=self.quality_values[-1])
        self.quality_menu   = ctk.CTkOptionMenu(opts_row,
                                                 values=self.quality_values,
                                                 variable=self.quality_var,
                                                 width=220, corner_radius=8)
        self.quality_menu.pack(side="left", padx=(0,12))

        # Trim alanı
        trim_frame = ctk.CTkFrame(opts_row, fg_color="#12121C", corner_radius=8)
        trim_frame.pack(side="left", padx=(0,12))
        ctk.CTkLabel(trim_frame, text="✂ Başlangıç:", font=("Segoe UI", 10)).pack(side="left", padx=(8,2))
        self.trim_start = ctk.CTkEntry(trim_frame, placeholder_text="00:00", width=60,
                                        height=30, corner_radius=6)
        self.trim_start.pack(side="left")
        ctk.CTkLabel(trim_frame, text="Bitiş:", font=("Segoe UI", 10)).pack(side="left", padx=(8,2))
        self.trim_end = ctk.CTkEntry(trim_frame, placeholder_text="03:40", width=60,
                                      height=30, corner_radius=6)
        self.trim_end.pack(side="left", padx=(0,8))

        # İndir butonu
        self.dl_btn = ctk.CTkButton(opts_row, text="⬇  İNDİR", width=120, height=38,
                                     corner_radius=10,
                                     fg_color="#7C3AED", hover_color="#6D28D9",
                                     font=("Segoe UI", 13, "bold"),
                                     command=self._start_download)
        self.dl_btn.pack(side="left")

        # Klasör seçimi
        dir_row = ctk.CTkFrame(inner, fg_color="transparent")
        dir_row.grid(row=4, column=0, pady=(8,0), sticky="ew")
        self.dir_lbl = ctk.CTkLabel(dir_row,
                                     text=f"📁  {self._out_dir}",
                                     font=("Segoe UI", 10), text_color="#9090B0",
                                     anchor="w")
        self.dir_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(dir_row, text="Klasör Seç", width=100, height=26,
                       corner_radius=6, fg_color="#22223A", hover_color="#2A2A45",
                       font=("Segoe UI", 10),
                       command=self._pick_dir).pack(side="right")

        media_opts = ctk.CTkFrame(inner, fg_color="transparent")
        media_opts.grid(row=3, column=0, pady=(6,0), sticky="w")
        self.keep_thumbnail_var = ctk.BooleanVar(value=self._keep_thumbnail)
        ctk.CTkCheckBox(
            media_opts,
            text="Kapak görselini ayrıca kaydet",
            variable=self.keep_thumbnail_var,
            command=self._save_thumbnail_preference,
            font=("Segoe UI", 10),
        ).pack(side="left")

        # ── Kuyruk / Geçmiş Sekmeleri ────────────────────────────────
        self.tabview = ctk.CTkTabview(self, corner_radius=10,
                                       fg_color="#12121C",
                                       segmented_button_fg_color="#1A1A24",
                                       segmented_button_selected_color="#7C3AED",
                                       segmented_button_selected_hover_color="#6D28D9")
        self.tabview.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)

        footer = ctk.CTkFrame(self, fg_color="transparent", height=22)
        footer.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 4))
        ctk.CTkLabel(
            footer, text=f"{APP_NAME}  ·  v{APP_VERSION}",
            font=("Segoe UI", 9), text_color="#777790", anchor="e",
        ).pack(side="right")

        self.tabview.add("⬇ İndirme Kuyruğu")
        self.tabview.add("🕑 Geçmiş")
        self.tabview.add("📋 URL Geçmişi")

        # Kuyruk sekmesi
        q_tab = self.tabview.tab("⬇ İndirme Kuyruğu")
        q_tab.grid_columnconfigure(0, weight=1)
        q_tab.grid_rowconfigure(0, weight=1)

        self.queue_scroll = ctk.CTkScrollableFrame(q_tab, fg_color="transparent")
        self.queue_scroll.grid(row=0, column=0, sticky="nsew")
        self.queue_scroll.grid_columnconfigure(0, weight=1)

        self._empty_lbl = ctk.CTkLabel(self.queue_scroll,
                                        text="Henüz indirme eklenmedi. Yukarıdan bir link gir!",
                                        font=("Segoe UI", 13), text_color="#505070")
        self._empty_lbl.grid(row=0, column=0, pady=40)

        # Kuyruk kontrol butonları
        q_btns = ctk.CTkFrame(q_tab, fg_color="transparent")
        q_btns.grid(row=1, column=0, pady=4, sticky="e")
        ctk.CTkButton(q_btns, text="Tümünü İptal Et", width=130, height=28,
                       corner_radius=6, fg_color="#22223A", hover_color="#2A2A45",
                       font=("Segoe UI", 10),
                       command=self.downloader.pause_all).pack(side="left", padx=4)
        ctk.CTkButton(q_btns, text="Tamamlananları Temizle", width=170, height=28,
                       corner_radius=6, fg_color="#22223A", hover_color="#2A2A45",
                       font=("Segoe UI", 10),
                       command=self._clear_done).pack(side="left", padx=4)

        # Geçmiş sekmesi
        h_tab = self.tabview.tab("🕑 Geçmiş")
        h_tab.grid_columnconfigure(0, weight=1)
        h_tab.grid_rowconfigure(0, weight=1)
        self.hist_scroll = ctk.CTkScrollableFrame(h_tab, fg_color="transparent")
        self.hist_scroll.grid(row=0, column=0, sticky="nsew")
        self.hist_scroll.grid_columnconfigure(0, weight=1)
        self._refresh_history()

        # URL Geçmişi sekmesi
        u_tab = self.tabview.tab("📋 URL Geçmişi")
        u_tab.grid_columnconfigure(0, weight=1)
        u_tab.grid_rowconfigure(0, weight=1)
        self.url_hist_scroll = ctk.CTkScrollableFrame(u_tab, fg_color="transparent")
        self.url_hist_scroll.grid(row=0, column=0, sticky="nsew")
        self.url_hist_scroll.grid_columnconfigure(0, weight=1)
        self._refresh_url_history()

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _find_ffmpeg(self) -> str:
        """Return the executable path so yt-dlp can locate sibling ffprobe."""
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS  # type: ignore[attr-defined]
            candidate = os.path.join(base, "ffmpeg.exe")
            probe = os.path.join(base, "ffprobe.exe")
            if os.path.exists(candidate) and os.path.exists(probe):
                return candidate
        return shutil.which("ffmpeg") or "ffmpeg"

    def _save_thumbnail_preference(self):
        self._keep_thumbnail = bool(self.keep_thumbnail_var.get())
        hist.set_setting("keep_thumbnail", self._keep_thumbnail)

    def _clear_placeholder(self, event):
        content = self.url_entry.get("0.0", "end").strip()
        if "linkini yapıştır" in content:
            self.url_entry.delete("0.0", "end")

    def _restore_placeholder(self, event):
        content = self.url_entry.get("0.0", "end").strip()
        if not content:
            self.url_entry.insert("0.0",
                "Buraya YouTube, TikTok, Instagram... linkini yapıştır\n"
                "(Birden fazla link için alt alta yaz)")

    def _paste_clipboard(self):
        try:
            clip = self.clipboard_get()
            self.url_entry.delete("0.0", "end")
            self.url_entry.insert("0.0", clip)
            self._schedule_preview()
        except Exception:
            pass

    def _schedule_preview(self, event=None):
        if self._vlc_player:
            self._vlc_player.stop()
            self.preview_player_frame.grid_remove()
        if self._preview_after_id:
            try:
                self.after_cancel(self._preview_after_id)
            except Exception:
                pass
            self._preview_after_id = None

        self._preview_request_id += 1
        request_id = self._preview_request_id
        raw = self.url_entry.get("0.0", "end").strip()
        urls = [line.strip() for line in raw.splitlines()
                if line.strip().startswith(("http://", "https://"))]
        if not urls:
            self._preview_url = ""
            self._preview_data = None
            self._update_preview_play_buttons()
            self.preview_card.grid_remove()
            return

        url = urls[0]
        self._preview_url = url
        self._preview_data = None
        self._update_preview_play_buttons()
        self.preview_card.grid()
        self.preview_title_lbl.configure(text="Önizleme yükleniyor...")
        self.preview_meta_lbl.configure(text="Video bilgileri alınıyor")
        self._clear_preview_image()
        self._preview_after_id = self.after(
            550, lambda: self._fetch_preview_async(url, request_id)
        )

    def _preview_after_paste(self, event=None):
        # Text widgets insert clipboard contents after the <<Paste>> binding.
        self.after_idle(self._schedule_preview)

    def _clear_preview_image(self):
        # Keep a live CTkImage attached; CTkLabel(image=None) leaves Tk's old
        # PhotoImage name behind and it can be garbage-collected on the next paste.
        self.preview_image_label.configure(image=self._preview_placeholder_image, text="▶")
        self._preview_image = self._preview_placeholder_image

    def _open_preview(self, media_type: str):
        if not self._preview_data:
            return
        playback = self._preview_data.get("playback") or {}
        stream = playback.get(media_type)
        if not stream or not stream.get("url"):
            return

        try:
            import vlc
            if self._vlc_instance is None:
                self._vlc_instance = vlc.Instance("--no-video-title-show", "--quiet")
            if self._vlc_player:
                self._vlc_player.stop()
                self._vlc_player.release()

            self.preview_player_frame.grid()
            self.update_idletasks()
            local_path = self._find_downloaded_preview() if media_type == "video" else None
            if local_path:
                # TikTok CDN akışları VLC'de siyah ekran bırakabiliyor. İndirilmiş
                # dosya varsa aynı içeriği doğrudan yerelden oynat.
                media = self._vlc_instance.media_new_path(local_path)
            else:
                media = self._vlc_instance.media_new(stream["url"])
                headers = stream.get("http_headers") or {}
                if headers.get("User-Agent"):
                    media.add_option(f":http-user-agent={headers['User-Agent']}")
                if headers.get("Referer"):
                    media.add_option(f":http-referrer={headers['Referer']}")
            audio_slave = playback.get("audio_slave") if media_type == "video" and not local_path else None
            if audio_slave and audio_slave.get("url"):
                media.add_option(f":input-slave={audio_slave['url']}")

            self._vlc_player = self._vlc_instance.media_player_new()
            self._vlc_player.set_media(media)
            if sys.platform == "win32":
                self._vlc_player.set_hwnd(self.preview_video_host.winfo_id())
            elif sys.platform == "darwin":
                self._vlc_player.set_nsobject(self.preview_video_host.winfo_id())
            else:
                self._vlc_player.set_xwindow(self.preview_video_host.winfo_id())
            self._vlc_player.audio_set_volume(int(self.preview_volume.get()))
            if media_type == "audio":
                self.preview_audio_overlay.place(relx=0.5, rely=0.5, anchor="center")
            else:
                self.preview_audio_overlay.place_forget()
            self._vlc_player.play()
            self.preview_toggle_btn.configure(text="⏸ Duraklat")
        except Exception as exc:
            messagebox.showerror(
                "Önizleme açılamadı",
                f"Uygulama içi oynatıcı başlatılamadı. VLC kurulumunu kontrol et.\n\n{exc}",
            )

    def _find_downloaded_preview(self):
        """Return a completed local file matching the current preview URL, if any."""
        current = self._preview_url.strip().rstrip("/")
        if not current:
            return None
        for card in reversed(self._cards):
            task = card.task
            if (task.url.strip().rstrip("/") == current
                    and task.status == DownloadTask.STATUS_DONE
                    and task.fmt in VIDEO_FORMATS
                    and task.file_path and os.path.isfile(task.file_path)):
                return task.file_path
        for item in hist.get_downloads():
            if (item.get("url", "").strip().rstrip("/") == current
                    and item.get("fmt") in VIDEO_FORMATS
                    and os.path.isfile(item.get("file_path", ""))):
                return item["file_path"]
        return None

    def _toggle_preview_playback(self):
        if not self._vlc_player:
            return
        if self._vlc_player.is_playing():
            self._vlc_player.pause()
            self.preview_toggle_btn.configure(text="▶ Devam et")
        else:
            self._vlc_player.play()
            self.preview_toggle_btn.configure(text="⏸ Duraklat")

    def _stop_preview_playback(self):
        if self._vlc_player:
            self._vlc_player.stop()
        self.preview_toggle_btn.configure(text="⏸ Duraklat")

    def _set_preview_volume(self, value):
        if self._vlc_player:
            self._vlc_player.audio_set_volume(int(float(value)))

    def _close_app(self):
        """Hide to the system tray; the tray menu owns the real exit action."""
        if self._is_exiting:
            return
        if self._tray_icon is None:
            try:
                import pystray
                tray_image = Image.open(_resource_path(os.path.join("assets", "medyamate.ico"))).convert("RGBA")
                menu = pystray.Menu(
                    pystray.MenuItem("MedyaMate'i aç", lambda icon, item: self.after(0, self._restore_from_tray), default=True),
                    pystray.MenuItem("Tamamen çıkış", lambda icon, item: self.after(0, self._exit_app)),
                )
                self._tray_icon = pystray.Icon("medyamate", tray_image, "MedyaMate", menu)
                self._tray_icon.run_detached()
            except Exception as exc:
                messagebox.showerror("Sistem tepsisi açılamadı", f"Uygulama kapatılmadı. Tepsi simgesi başlatılamadı:\n{exc}")
                return
        self.withdraw()

    def _restore_from_tray(self):
        if self._is_exiting:
            return
        self.deiconify()
        self.state("normal")
        self.lift()

    def _exit_app(self):
        if self._is_exiting:
            return
        self._is_exiting = True
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        if self._vlc_player:
            try:
                self._vlc_player.stop()
                self._vlc_player.release()
            except Exception:
                pass
        if self._vlc_instance:
            try:
                self._vlc_instance.release()
            except Exception:
                pass
        self.destroy()

    def _fetch_preview_async(self, url: str, request_id: int):
        self._preview_after_id = None

        def worker():
            try:
                result = fetch_preview(url)
                error = ""
            except Exception as exc:
                result = None
                error = str(exc)
            self._preview_results.put((request_id, result, error))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_preview_results(self):
        try:
            while True:
                request_id, preview, error = self._preview_results.get_nowait()
                self._render_preview(request_id, preview, error)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll_preview_results)

    def _render_preview(self, request_id: int, preview: dict | None, error: str):
        if request_id != self._preview_request_id or not self.winfo_exists():
            return
        if error or not preview:
            self._preview_data = None
            self._update_preview_play_buttons()
            self.preview_title_lbl.configure(text="Önizleme alınamadı")
            error_text = error or "Bağlantı desteklenmiyor"
            if "instagram.com" in self._preview_url.lower():
                error_text = (
                    "Instagram linkine erişilemedi. Herkese açık bir Reel dene; "
                    "bazı içerikler oturum gerektirir. " + error_text
                )
            self.preview_meta_lbl.configure(text=error_text[:180])
            self._clear_preview_image()
            return

        self._preview_data = preview
        self._update_preview_play_buttons()
        self.preview_title_lbl.configure(text=preview["title"])
        details = [part for part in (preview.get("channel"), preview.get("duration")) if part]
        self.preview_meta_lbl.configure(text=" • ".join(details) or "Medya bilgisi alındı")
        image = preview.get("thumbnail")
        if image:
            image = rounded_image(image.resize((120, 68), Image.LANCZOS))
            self._preview_image = ctk.CTkImage(light_image=image, dark_image=image, size=(120, 68))
            self.preview_image_label.configure(image=self._preview_image, text="")
        else:
            self._clear_preview_image()

    def _on_format_change(self, label: str):
        self.fmt_var.set(FORMAT_LABELS[label])
        self._update_quality_menu()

    def _update_preview_play_buttons(self):
        if not self._preview_data:
            self.preview_video_btn.configure(state="disabled")
            self.preview_audio_btn.configure(state="disabled")
            return
        playback = self._preview_data.get("playback") or {}
        video = playback.get("video")
        audio = playback.get("audio")
        self.preview_video_btn.configure(state="normal" if video and video.get("url") else "disabled")
        self.preview_audio_btn.configure(state="normal" if audio and audio.get("url") else "disabled")

    def _update_quality_menu(self):
        fmt = self.fmt_var.get()
        if fmt in {"mp3", "m4a"}:
            vals = [q["label"] for q in MP3_QUALITIES]
        elif fmt in {"wav", "flac"}:
            vals = [q["label"] for q in LOSSLESS_QUALITIES]
        else:
            vals = [q["label"] for q in MP4_QUALITIES]
        self.quality_menu.configure(values=vals)
        self.quality_var.set(vals[-1])

    def _get_quality_value(self) -> str:
        label = self.quality_var.get()
        fmt   = self.fmt_var.get()
        if fmt in {"mp3", "m4a"}:
            opts = MP3_QUALITIES
        elif fmt in {"wav", "flac"}:
            opts = LOSSLESS_QUALITIES
        else:
            opts = MP4_QUALITIES
        for q in opts:
            if q["label"] == label:
                return q["value"]
        return "best"

    def _pick_dir(self):
        path = filedialog.askdirectory(title="İndirme Klasörünü Seç")
        if path:
            self._out_dir = path
            hist.set_setting("out_dir", path)
            self.dir_lbl.configure(text=f"📁  {path}")

    def _toggle_theme(self):
        self._dark = not self._dark
        mode = "dark" if self._dark else "light"
        ctk.set_appearance_mode(mode)
        hist.set_setting("theme", mode)
        self.theme_btn.configure(text="🌙" if self._dark else "☀")

    # ------------------------------------------------------------------
    # İndirme Başlat
    # ------------------------------------------------------------------

    def _start_download(self):
        raw = self.url_entry.get("0.0", "end").strip()
        urls = [u.strip() for u in raw.splitlines() if u.strip().startswith("http")]
        if not urls:
            messagebox.showwarning("Uyarı", "Geçerli bir URL bulunamadı.")
            return

        fmt     = self.fmt_var.get()
        quality = self._get_quality_value()
        t_start = self.trim_start.get().strip()
        t_end   = self.trim_end.get().strip()
        out_dir = self._out_dir

        os.makedirs(out_dir, exist_ok=True)

        # Boş etiketi gizle
        self._empty_lbl.grid_forget()

        for url in urls:
            task = DownloadTask(url, fmt, quality, out_dir,
                                trim_start=t_start, trim_end=t_end,
                                keep_thumbnail=self.keep_thumbnail_var.get())
            card = DownloadCard(self.queue_scroll, task,
                                on_remove=self._remove_card)
            card.grid(row=len(self._cards), column=0,
                      padx=8, pady=4, sticky="ew")
            self._cards.append(card)
            self.downloader.add(task)

            # URL geçmişine kaydet (başlık henüz "url" olacak, sonra güncellenir)
            hist.add_url(url, url)

        # URL kutusunu temizle
        self.url_entry.delete("0.0", "end")

    def _remove_card(self, card: DownloadCard):
        if card in self._cards:
            self._cards.remove(card)
            card.destroy()
        if not self._cards:
            self._empty_lbl.grid(row=0, column=0, pady=40)

    def _clear_done(self):
        done = [c for c in self._cards
                if c.task.status in (DownloadTask.STATUS_DONE,
                                      DownloadTask.STATUS_ERROR,
                                      DownloadTask.STATUS_CANCELLED)]
        for c in done:
            self._remove_card(c)
        self._refresh_history()

    # ------------------------------------------------------------------
    # Geçmiş Panelleri
    # ------------------------------------------------------------------

    def _refresh_history(self):
        for w in self.hist_scroll.winfo_children():
            w.destroy()
        downloads = hist.get_downloads()
        if not downloads:
            ctk.CTkLabel(self.hist_scroll,
                         text="Henüz indirilen dosya yok.",
                         text_color="#505070",
                         font=("Segoe UI", 12)).grid(row=0, column=0, pady=30)
            return
        for i, d in enumerate(downloads):
            row = ctk.CTkFrame(self.hist_scroll, fg_color="#1A1A24",
                               corner_radius=8, border_width=1,
                               border_color="#2A2A45")
            row.grid(row=i, column=0, padx=8, pady=3, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row,
                         text=f"{d['title'][:60]}",
                         font=("Segoe UI", 11, "bold"),
                         anchor="w").grid(row=0, column=0, padx=10, pady=(6,0), sticky="ew")
            ctk.CTkLabel(row,
                         text=f"{d['fmt'].upper()} • {d['quality']} • {d['date']}",
                         font=("Segoe UI", 9), text_color="#9090B0",
                         anchor="w").grid(row=1, column=0, padx=10, pady=(0,6), sticky="ew")
            fp = d["file_path"]
            ctk.CTkButton(row, text="📂", width=32, height=32,
                          corner_radius=6, fg_color="#22223A",
                          hover_color="#2A2A45",
                          command=lambda p=fp: self._open_path(p)).grid(
                              row=0, column=1, rowspan=2, padx=8)

    def _refresh_url_history(self):
        for w in self.url_hist_scroll.winfo_children():
            w.destroy()
        urls = hist.get_url_history()
        if not urls:
            ctk.CTkLabel(self.url_hist_scroll,
                         text="Henüz link geçmişi yok.",
                         text_color="#505070",
                         font=("Segoe UI", 12)).grid(row=0, column=0, pady=30)
            return
        for i, u in enumerate(urls):
            row = ctk.CTkFrame(self.url_hist_scroll, fg_color="#1A1A24",
                               corner_radius=8, border_width=1,
                               border_color="#2A2A45")
            row.grid(row=i, column=0, padx=8, pady=3, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row,
                         text=u.get("title", u["url"])[:70],
                         font=("Segoe UI", 11), anchor="w").grid(
                             row=0, column=0, padx=10, pady=4, sticky="ew")
            ctk.CTkLabel(row, text=u["date"],
                         font=("Segoe UI", 9), text_color="#9090B0",
                         anchor="w").grid(row=1, column=0, padx=10, pady=(0,4), sticky="ew")
            ctk.CTkButton(row, text="Yükle", width=60, height=28,
                          corner_radius=6, fg_color="#7C3AED",
                          hover_color="#6D28D9",
                          font=("Segoe UI", 10),
                          command=lambda url=u["url"]: self._load_url(url)).grid(
                              row=0, column=1, rowspan=2, padx=8)

    def _load_url(self, url: str):
        self.url_entry.delete("0.0", "end")
        self.url_entry.insert("0.0", url)
        self.tabview.set("⬇ İndirme Kuyruğu")

    def _open_path(self, path: str):
        if path and os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{path}"')

    # ------------------------------------------------------------------
    # Ayarlar Penceresi
    # ------------------------------------------------------------------

    def _open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Ayarlar")
        win.geometry("440x380")
        win.grab_set()

        ctk.CTkLabel(win, text="⚙ Ayarlar",
                     font=("Segoe UI", 15, "bold")).pack(pady=(20,10))

        # Eşzamanlı indirme sayısı
        ctk.CTkLabel(win, text="Eş Zamanlı İndirme Sayısı:").pack(pady=(10,0))
        self.concurrent_var = ctk.IntVar(
            value=hist.get_setting("concurrent", 2))
        ctk.CTkSlider(win, from_=1, to=5, number_of_steps=4,
                       variable=self.concurrent_var,
                       command=self._set_concurrent).pack(padx=30, fill="x")

        ctk.CTkLabel(win, text="━" * 50, text_color="#2A2A45").pack(pady=8)

        # yt-dlp güncelleme
        self.ytdlp_lbl = ctk.CTkLabel(win, text="İndirme motorunu güncelle (yt-dlp)",
                                        text_color="#9090B0")
        self.ytdlp_lbl.pack()
        ctk.CTkButton(win, text="🔄 yt-dlp Güncelle", width=200,
                       fg_color="#22223A", hover_color="#2A2A45",
                       command=self._do_ytdlp_update).pack(pady=6)

        ctk.CTkLabel(win, text="━" * 50, text_color="#2A2A45").pack(pady=8)

        # Uygulama güncelleme
        ctk.CTkButton(win, text="🔍 Uygulama Güncellemelerini Kontrol Et",
                       width=250, fg_color="#7C3AED", hover_color="#6D28D9",
                       command=self._do_app_update).pack(pady=6)

        # Geçmiş temizle
        ctk.CTkButton(win, text="🗑 Geçmişi Temizle",
                       width=200, fg_color="#2A2A45",
                       hover_color="#EF4444",
                       command=lambda: (hist.clear_downloads(),
                                        hist.clear_url_history(),
                                        self._refresh_history(),
                                        self._refresh_url_history())).pack(pady=6)

    def _do_ytdlp_update(self):
        self.ytdlp_lbl.configure(text="⏳ Güncelleniyor...", text_color="#F59E0B")
        def cb(ok, msg):
            self.after(0, lambda: self.ytdlp_lbl.configure(
                text="✅ yt-dlp Güncellendi!" if ok else "❌ Güncelleme başarısız",
                text_color="#10B981" if ok else "#EF4444"))
        update_ytdlp(cb)

    def _set_concurrent(self, value):
        count = max(1, int(float(value)))
        hist.set_setting("concurrent", count)
        self.downloader.set_max_concurrent(count)

    def _do_app_update(self):
        def cb(has_upd, ver, url, body):
            def show_result():
                if has_upd and not url:
                    messagebox.showwarning("Güncelleme", "Yeni sürüm bulundu ancak indirilebilir .exe dosyası eklenmemiş.")
                elif has_upd:
                    if not getattr(sys, "frozen", False):
                        if messagebox.askyesno(
                            "Güncelleme Mevcut",
                            f"Yeni sürüm v{ver} bulundu. .exe dosyasını GitHub Releases sayfasından indirmek ister misiniz?",
                        ):
                            import webbrowser
                            webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")
                        return
                    ans = messagebox.askyesno(
                        "Güncelleme Mevcut",
                        f"Yeni sürüm: v{ver}\n\n{body[:300]}\n\nİndirip güncellemek ister misiniz?")
                    if ans:
                        self._start_app_update(url)
                else:
                    messagebox.showinfo("Güncelleme", "Zaten en güncel sürümdesiniz! 🎉")
            self.after(0, show_result)
        check_for_update(cb)

    # ------------------------------------------------------------------
    # Arka Planda Güncelleme Kontrolü (Açılışta)
    # ------------------------------------------------------------------

    def _check_update_bg(self):
        try:
            def cb(has_upd, ver, url, body):
                try:
                    if has_upd:
                        self.after(0, lambda: self._show_update_banner(ver, url, body))
                except Exception:
                    pass
            check_for_update(cb)
        except Exception:
            pass

    def _show_update_banner(self, ver: str, url: str, body: str):
        if not self.winfo_exists():
            return
        if getattr(self, "_update_banner", None):
            try:
                self._update_banner.destroy()
            except Exception:
                pass
        banner = ctk.CTkFrame(self, fg_color="#7C3AED", corner_radius=0, height=36)
        self._update_banner = banner
        banner.grid(row=4, column=0, sticky="ew")
        banner.grid_propagate(False)
        banner.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(banner,
                     text=(f"🎉 Yeni sürüm mevcut: v{ver}" if url else
                           f"Yeni sürüm v{ver} bulundu; GitHub Release'e MedyaMate.exe eklenmemiş."),
                     font=("Segoe UI", 11, "bold"),
                     text_color="white").grid(row=0, column=0, pady=8, sticky="w", padx=12)
        if url and getattr(sys, "frozen", False):
            ctk.CTkButton(banner, text="İndir ve güncelle", width=130, height=28,
                           fg_color="white", text_color="#7C3AED",
                           hover_color="#EDE9FE",
                           command=lambda: self._start_app_update(url)).grid(row=0, column=1, padx=12)

    def _start_app_update(self, url: str):
        """Download the selected release in the background and restart into it."""
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                "Güncelleme",
                "Geliştirici modunda otomatik kurulum kapalı. Yeni MedyaMate.exe dosyasını GitHub Releases'tan indirebilirsiniz.",
            )
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("MedyaMate güncelleniyor")
        dialog.geometry("380x130")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Güncelleme indiriliyor…", font=("Segoe UI", 13, "bold")).pack(pady=(18, 8))
        progress = ctk.CTkProgressBar(dialog, width=330)
        progress.pack(pady=5)
        progress.set(0)
        status = ctk.CTkLabel(dialog, text="Lütfen pencereyi kapatmayın", font=("Segoe UI", 10))
        status.pack(pady=5)

        def on_progress(percent):
            def update_ui():
                if dialog.winfo_exists():
                    progress.set(max(0.0, min(percent / 100.0, 1.0)))
                    status.configure(text=f"İndiriliyor… %{percent:.0f}")
            try:
                self.after(0, update_ui)
            except Exception:
                pass

        def worker():
            try:
                apply_update(url, on_progress)
            except Exception as exc:
                def show_error():
                    if dialog.winfo_exists():
                        dialog.destroy()
                    messagebox.showerror("Güncelleme başarısız", str(exc))
                try:
                    self.after(0, show_error)
                except Exception:
                    pass
            else:
                try:
                    self.after(0, self._exit_app)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()


# ══════════════════════════════════════════════════════════════
#  GİRİŞ
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        import traceback
        with open("hata_log.txt", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        try:
            import tkinter.messagebox as mb
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            mb.showerror("Program Hatası", f"Hata:\n{e}\n\nDetay: hata_log.txt dosyasına bakın.")
            root.destroy()
        except Exception:
            # Tcl/Tk is unavailable: preserve the original error in hata_log.txt
            # without raising a second exception while trying to show a dialog.
            pass
