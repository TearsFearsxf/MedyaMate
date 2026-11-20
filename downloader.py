"""
İndirme motoru: yt-dlp tabanlı, thread-safe, ilerleme bildirimiyle.
"""
import os
import threading
import yt_dlp
import requests
from html.parser import HTMLParser
from io import BytesIO
from PIL import Image
from urllib.parse import urlparse
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, ID3NoHeaderError
from config import MAX_CONCURRENT_DOWNLOADS

AUDIO_FORMATS = {"mp3", "m4a", "wav", "flac"}
VIDEO_FORMATS = {"mp4", "mkv"}
DEFAULT_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
}


def _metadata_ydl_options() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "http_headers": DEFAULT_HTTP_HEADERS,
        "socket_timeout": 20,
        "retries": 3,
        "extractor_retries": 3,
        "fragment_retries": 3,
    }


class DownloadTask:
    """Tek bir indirme görevini temsil eder."""

    STATUS_QUEUED      = "queued"
    STATUS_FETCHING    = "fetching"
    STATUS_DOWNLOADING = "downloading"
    STATUS_CONVERTING  = "converting"
    STATUS_DONE        = "done"
    STATUS_ERROR       = "error"
    STATUS_CANCELLED   = "cancelled"

    def __init__(self, url: str, fmt: str, quality: str, out_dir: str,
                 trim_start: str = "", trim_end: str = "", keep_thumbnail: bool = False):
        self.url         = url
        self.fmt         = fmt           # mp3/m4a/wav/flac veya mp4/mkv
        self.quality     = quality       # "320", "1080" vb.
        self.out_dir     = out_dir
        self.trim_start  = trim_start    # "01:15" formatında, boşsa kırpma yok
        self.trim_end    = trim_end
        self.keep_thumbnail = bool(keep_thumbnail)

        # Meta
        self.title       = url           # başlangıçta URL, sonra gerçek başlık
        self.thumbnail   = None          # PIL Image
        self.duration    = ""
        self.duration_seconds = 0
        self.channel     = ""
        self.file_path   = ""

        # İlerleme
        self.status      = self.STATUS_QUEUED
        self.percent     = 0.0
        self.speed       = ""
        self.eta         = ""
        self.downloaded  = ""
        self.total_size  = ""
        self.error_msg   = ""

        # Callback (UI tarafından set edilecek)
        self.on_progress = None          # fn(task) çağrılır
        self.on_done     = None          # fn(task)
        self.on_error    = None          # fn(task)

        self._cancel_flag = threading.Event()

    def cancel(self):
        self._cancel_flag.set()

    @property
    def is_cancelled(self):
        return self._cancel_flag.is_set()


class Downloader:
    """İndirme kuyruğunu yöneten sınıf."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", max_concurrent: int = MAX_CONCURRENT_DOWNLOADS):
        self.ffmpeg_path  = ffmpeg_path
        self._queue       = []
        self._active      = []
        self._lock        = threading.Lock()
        self._max_concurrent = max(1, int(max_concurrent))
        self._condition  = threading.Condition(self._lock)
        self._history     = []           # Tamamlanan görevler

    # ------------------------------------------------------------------
    # Kuyruk Yönetimi
    # ------------------------------------------------------------------

    def add(self, task: DownloadTask):
        with self._lock:
            self._queue.append(task)
        threading.Thread(target=self._worker, args=(task,), daemon=True).start()

    def add_many(self, tasks: list):
        for t in tasks:
            self.add(t)

    def pause_all(self):
        with self._condition:
            for t in self._queue + self._active:
                t.cancel()
            self._condition.notify_all()

    def set_max_concurrent(self, value: int):
        with self._condition:
            self._max_concurrent = max(1, int(value))
            self._condition.notify_all()

    def cancel_task(self, task: DownloadTask):
        task.cancel()

    # ------------------------------------------------------------------
    # Ana İndirme İş Parçacığı
    # ------------------------------------------------------------------

    def _worker(self, task: DownloadTask):
        with self._condition:
            while len(self._active) >= self._max_concurrent and not task.is_cancelled:
                self._condition.wait()
            if task in self._queue:
                self._queue.remove(task)
            if task.is_cancelled:
                task.status = DownloadTask.STATUS_CANCELLED
                self._condition.notify_all()
                if task.on_progress:
                    task.on_progress(task)
                return
            self._active.append(task)
        try:
            if task.is_cancelled:
                task.status = DownloadTask.STATUS_CANCELLED
                return
            self._fetch_info(task)
            if task.is_cancelled:
                task.status = DownloadTask.STATUS_CANCELLED
                return
            self._download(task)
        except Exception as e:
            if task.is_cancelled:
                task.status = DownloadTask.STATUS_CANCELLED
                if task.on_progress:
                    task.on_progress(task)
            else:
                task.status    = DownloadTask.STATUS_ERROR
                task.error_msg = str(e)
                if "instagram.com" in task.url.lower() and any(
                    token in task.error_msg.lower()
                    for token in ("unable to download webpage", "403", "login", "checkpoint", "httpsconnection")
                ):
                    task.error_msg = (
                        "Instagram bağlantısına erişilemedi. Reel herkese açık olmalı; "
                        "bazı içerikler Instagram oturumu gerektirir. " + task.error_msg
                    )
                if task.on_error:
                    task.on_error(task)
        finally:
            with self._condition:
                if task in self._active:
                    self._active.remove(task)
                if task.status == DownloadTask.STATUS_DONE:
                    self._history.append(task)
                self._condition.notify_all()

    # ------------------------------------------------------------------
    # Video Bilgisi Çekme
    # ------------------------------------------------------------------

    def _fetch_info(self, task: DownloadTask):
        task.status = DownloadTask.STATUS_FETCHING
        if task.on_progress:
            task.on_progress(task)

        ydl_opts = _metadata_ydl_options()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(task.url, download=False)

        task.title    = info.get("title", task.url)
        task.channel  = info.get("uploader", "")
        task.duration_seconds = int(info.get("duration") or 0)
        task.duration = self._fmt_duration(task.duration_seconds)

        # Thumbnail indir (PIL Image olarak sakla)
        thumb_url = info.get("thumbnail", "")
        if thumb_url:
            try:
                resp = requests.get(thumb_url, headers=DEFAULT_HTTP_HEADERS, timeout=10)
                task.thumbnail = Image.open(BytesIO(resp.content)).convert("RGB")
            except Exception:
                pass

        if task.on_progress:
            task.on_progress(task)

    # ------------------------------------------------------------------
    # İndirme
    # ------------------------------------------------------------------

    def _download(self, task: DownloadTask):
        os.makedirs(task.out_dir, exist_ok=True)

        postprocessors = []
        if task.fmt in AUDIO_FORMATS:
            format_str    = "bestaudio/best"
            out_tmpl      = os.path.join(task.out_dir, "%(title)s.%(ext)s")
            audio_pp = {
                "key":            "FFmpegExtractAudio",
                "preferredcodec": task.fmt,
            }
            if task.fmt in {"mp3", "m4a"}:
                audio_pp["preferredquality"] = task.quality
            postprocessors.append(audio_pp)
            postprocessors.append({"key": "FFmpegMetadata"})
            if task.fmt in {"mp3", "m4a", "flac"}:
                postprocessors.append({
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": task.keep_thumbnail,
                })
        else:
            height_filter = "" if task.quality == "best" else f"[height<={task.quality}]"
            if task.fmt == "mp4":
                fallback = f"/bestvideo{height_filter}+bestaudio/best[height<={task.quality}]/best" if height_filter else "/bestvideo+bestaudio/best"
                format_str = f"bestvideo{height_filter}[ext=mp4]+bestaudio[ext=m4a]{fallback}"
            else:
                fallback = f"/best[height<={task.quality}]/best" if height_filter else "/best"
                format_str = f"bestvideo{height_filter}+bestaudio{fallback}"
            out_tmpl = os.path.join(task.out_dir, "%(title)s.%(ext)s")
            postprocessors.append({"key": "FFmpegVideoConvertor", "preferedformat": task.fmt})

        # yt-dlp section download performs an actual trim. FFmpeg postprocessor
        # arguments do not reliably select the requested media section.
        download_ranges = None
        if task.trim_start or task.trim_end:
            start = self._parse_time(task.trim_start) if task.trim_start else 0
            end = self._parse_time(task.trim_end) if task.trim_end else task.duration_seconds
            if end <= start:
                raise ValueError("Bitiş zamanı başlangıçtan sonra olmalı.")
            download_ranges = yt_dlp.utils.download_range_func(None, [(start, end)])

        def progress_hook(d):
            if task.is_cancelled:
                raise yt_dlp.utils.DownloadError("İptal edildi")

            if d["status"] == "downloading":
                task.status    = DownloadTask.STATUS_DOWNLOADING
                task.percent   = float(
                    d.get("downloaded_bytes", 0) /
                    max(d.get("total_bytes") or d.get("total_bytes_estimate") or 1, 1) * 100
                )
                task.speed     = self._fmt_bytes(d.get("speed") or 0) + "/s"
                task.eta       = self._fmt_eta(d.get("eta") or 0)
                task.downloaded = self._fmt_bytes(d.get("downloaded_bytes") or 0)
                task.total_size = self._fmt_bytes(
                    d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                )
                if task.on_progress:
                    task.on_progress(task)

            elif d["status"] == "finished":
                task.status   = DownloadTask.STATUS_CONVERTING
                task.percent  = 100.0
                if task.on_progress:
                    task.on_progress(task)

        def postprocessor_hook(d):
            info = d.get("info_dict") or {}
            if info.get("filepath"):
                task.file_path = info["filepath"]

        ydl_opts = {
            "format":           format_str,
            "outtmpl":          out_tmpl,
            "ffmpeg_location":  self.ffmpeg_path,
            "http_headers":     DEFAULT_HTTP_HEADERS,
            "socket_timeout":   20,
            "retries":          3,
            "fragment_retries": 3,
            "writethumbnail":   task.fmt in AUDIO_FORMATS or task.keep_thumbnail,
            "postprocessors":   postprocessors,
            "progress_hooks":   [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "quiet":            True,
            "no_warnings":      True,
            "merge_output_format": task.fmt if task.fmt in VIDEO_FORMATS else None,
        }

        if download_ranges:
            ydl_opts["download_ranges"] = download_ranges
            ydl_opts["force_keyframes_at_cuts"] = True

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task.url, download=True)
                if isinstance(info, dict):
                    task.file_path = info.get("filepath") or task.file_path
        finally:
            if not task.keep_thumbnail:
                self._cleanup_thumbnail_sidecars(task)

        # MP3 ise kapak + ID3 tag gömme (mutagen ile ek güvence)
        if task.fmt == "mp3":
            self._embed_id3(task)

        task.status  = DownloadTask.STATUS_DONE
        task.percent = 100.0
        if task.on_done:
            task.on_done(task)
        if task.on_progress:
            task.on_progress(task)

    # ------------------------------------------------------------------
    # ID3 Tag Gömme (MP3 kapak resmi + başlık + sanatçı)
    # ------------------------------------------------------------------

    def _embed_id3(self, task: DownloadTask):
        if not task.file_path or not os.path.exists(task.file_path) or not task.file_path.lower().endswith(".mp3"):
            task.file_path = ""
            safe_title = yt_dlp.utils.sanitize_filename(task.title)
            candidates = [os.path.join(task.out_dir, name) for name in os.listdir(task.out_dir)
                          if name.lower().endswith(".mp3") and name.startswith(safe_title)]
            if candidates:
                task.file_path = max(candidates, key=os.path.getmtime)
        if not task.file_path or not os.path.exists(task.file_path):
            return

        try:
            audio = ID3(task.file_path)
        except ID3NoHeaderError:
            audio = ID3()

        audio["TIT2"] = TIT2(encoding=3, text=task.title)
        audio["TPE1"] = TPE1(encoding=3, text=task.channel)
        audio["TALB"] = TALB(encoding=3, text=task.channel)

        if task.thumbnail:
            buf = BytesIO()
            task.thumbnail.save(buf, format="JPEG", quality=90)
            audio["APIC"] = APIC(
                encoding=0,
                mime="image/jpeg",
                type=3,
                desc="Cover",
                data=buf.getvalue(),
            )
        audio.save(task.file_path)

    @staticmethod
    def _cleanup_thumbnail_sidecars(task: DownloadTask):
        """Remove thumbnail files left behind after a failed/finished conversion."""
        try:
            safe_title = yt_dlp.utils.sanitize_filename(task.title).casefold()
            image_exts = (".webp", ".jpg", ".jpeg", ".png", ".avif")
            for name in os.listdir(task.out_dir):
                lowered = name.casefold()
                if lowered.startswith(safe_title) and lowered.endswith(image_exts):
                    try:
                        os.remove(os.path.join(task.out_dir, name))
                    except OSError:
                        pass
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Yardımcı Fonksiyonlar
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_bytes(b) -> str:
        if not b:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    @staticmethod
    def _fmt_eta(secs: int) -> str:
        if not secs:
            return "--:--"
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    @staticmethod
    def _fmt_duration(secs: int) -> str:
        if not secs:
            return ""
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02}:{s:02}"
        return f"{m}:{s:02}"

    @staticmethod
    def _parse_time(value: str) -> int:
        try:
            parts = [int(part) for part in value.strip().split(":")]
        except (TypeError, ValueError):
            raise ValueError("Zamanı SS, DD:SS veya SS:DD:SS biçiminde girin.")
        if not 1 <= len(parts) <= 3 or any(part < 0 for part in parts):
            raise ValueError("Zamanı SS, DD:SS veya SS:DD:SS biçiminde girin.")
        total = 0
        for part in parts:
            total = total * 60 + part
        return total


class _PreviewHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title_parts = []
        self._inside_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            content = attrs.get("content")
            if key and content:
                self.meta[key] = content
        elif tag.lower() == "title":
            self._inside_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data):
        if self._inside_title and data.strip():
            self.title_parts.append(data.strip())


def _thumbnail_from_url(thumbnail_url):
    if not thumbnail_url:
        return None
    try:
        response = requests.get(thumbnail_url, headers=DEFAULT_HTTP_HEADERS, timeout=10)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGB")
    except Exception:
        return None


def _open_graph_preview(url: str, original_error: Exception) -> dict:
    """Fallback metadata for pages whose extractor can no longer parse the site."""
    response = requests.get(url, headers=DEFAULT_HTTP_HEADERS, timeout=15)
    response.raise_for_status()
    parser = _PreviewHTMLParser()
    parser.feed(response.text)
    meta = parser.meta
    title = meta.get("og:title") or meta.get("twitter:title") or " ".join(parser.title_parts)
    thumbnail_url = meta.get("og:image") or meta.get("twitter:image")
    media_url = meta.get("og:video:secure_url") or meta.get("og:video") or meta.get("twitter:player:stream")
    suffix = urlparse(media_url).path.lower() if media_url else ""
    direct_video = media_url if suffix.endswith((".mp4", ".m3u8", ".mpd", ".webm")) else None
    if not title and not thumbnail_url and not direct_video:
        raise original_error
    return {
        "title": title or url,
        "channel": "",
        "duration": "",
        "thumbnail": _thumbnail_from_url(thumbnail_url),
        "playback": {
            "audio": None,
            "video": {"url": direct_video, "http_headers": DEFAULT_HTTP_HEADERS} if direct_video else None,
            "audio_slave": None,
        },
    }


def fetch_preview(url: str) -> dict:
    """Read media metadata and a thumbnail without downloading the media."""
    options = _metadata_ydl_options()
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        return _open_graph_preview(url, exc)

    if not isinstance(info, dict):
        raise ValueError("Bu bağlantıdan medya bilgisi alınamadı.")
    if info.get("entries"):
        info = next((entry for entry in (info.get("entries") or []) if isinstance(entry, dict)), None)
    if not info:
        raise ValueError("Bu bağlantıda önizlenecek video bulunamadı.")

    thumbnail = None
    thumbnail_url = info.get("thumbnail")
    if not thumbnail_url:
        thumbnails = info.get("thumbnails") or []
        thumbnail_url = next((item.get("url") for item in reversed(thumbnails)
                              if isinstance(item, dict) and item.get("url")), None)
    if thumbnail_url:
        try:
            thumbnail = _thumbnail_from_url(thumbnail_url)
        except Exception:
            thumbnail = None

    formats = [
        item for item in (info.get("formats") or [])
        if isinstance(item, dict) and isinstance(item.get("url"), str)
        and item["url"].startswith(("http://", "https://"))
    ]

    def has_video(item):
        codec = item.get("vcodec")
        if codec is not None:
            return codec != "none"
        return bool(item.get("height") or item.get("ext") in {"mp4", "mkv", "webm", "mov", "m3u8"})

    def has_audio(item):
        codec = item.get("acodec")
        if codec is not None:
            return codec != "none"
        if item.get("ext") in {"m4a", "mp3", "aac", "wav", "flac", "opus"}:
            return True
        # Some extractors provide a direct progressive URL without codec fields.
        return bool(item.get("url") and item.get("ext") in {"mp4", "mkv", "webm", "mov"})

    def numeric(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def rank(item):
        return (numeric(item.get("height")), numeric(item.get("tbr") or item.get("abr")))

    audio_format = max((item for item in formats if has_audio(item) and not has_video(item)), key=rank, default=None)
    progressive_video = max((item for item in formats if has_video(item) and has_audio(item)), key=rank, default=None)
    video_only = max((item for item in formats if has_video(item) and not has_audio(item)), key=rank, default=None)
    if (not audio_format and isinstance(info.get("url"), str)
            and info.get("ext") in {"m4a", "mp3", "aac", "wav", "flac", "opus"}):
        audio_format = info
    if not progressive_video and has_video(info) and has_audio(info) and isinstance(info.get("url"), str):
        progressive_video = info
    video_format = progressive_video or (video_only if audio_format else None)

    def stream_data(item):
        if not item:
            return None
        stream_url = item.get("url")
        if not isinstance(stream_url, str) or not stream_url.startswith(("http://", "https://")):
            return None
        headers = dict(DEFAULT_HTTP_HEADERS)
        headers.update(item.get("http_headers") or info.get("http_headers") or {})
        return {"url": stream_url, "http_headers": headers}

    return {
        "title": info.get("title") or url,
        "channel": info.get("uploader") or info.get("channel") or "",
        "duration": Downloader._fmt_duration(info.get("duration") or 0),
        "thumbnail": thumbnail,
        "playback": {
            "audio": stream_data(audio_format),
            "video": stream_data(video_format),
            "audio_slave": stream_data(audio_format) if video_only and not progressive_video else None,
        },
    }
