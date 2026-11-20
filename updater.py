"""
GitHub üzerinden otomatik güncelleme kontrolü ve uygulama.
"""
import os
import sys
import threading
import subprocess
import shutil
import tempfile
import requests
from packaging.version import Version
from config import APP_VERSION, GITHUB_API


def check_for_update(callback):
    """
    Arka planda GitHub'ı kontrol eder.
    callback(has_update: bool, latest_version: str, download_url: str, body: str)
    """
    def _check():
        try:
            resp = requests.get(GITHUB_API, timeout=10)
            if resp.status_code != 200:
                callback(False, APP_VERSION, "", "")
                return
            data         = resp.json()
            latest       = str(data.get("tag_name", "v0.0.0")).lstrip("v")
            current      = APP_VERSION.lstrip("v")
            has_update   = Version(latest) > Version(current)
            # Yalnızca paketlenmiş uygulamanın eşleşen exe'sini sun.
            download_url = ""
            for asset in data.get("assets", []):
                if asset.get("name", "").lower() == "medyamate.exe":
                    download_url = asset.get("browser_download_url", "")
                    break
            body = data.get("body", "")
            callback(has_update, latest, download_url, body)
        except Exception:
            callback(False, APP_VERSION, "", "")

    threading.Thread(target=_check, daemon=True).start()


def apply_update(download_url: str, progress_callback=None):
    """
    Yeni .exe'yi indirip doğrular, sonra kapandıktan sonra kendini güncelleyecek
    küçük bir Windows betiği başlatır.
    progress_callback(percent: float)
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Uygulama güncellemesi yalnızca paketlenmiş .exe sürümünde kullanılabilir.")
    if sys.platform != "win32":
        raise RuntimeError("Otomatik uygulama güncellemesi şu anda Windows'ta destekleniyor.")
    if not download_url or not download_url.lower().startswith("https://github.com/"):
        raise ValueError("Geçerli güncelleme indirme adresi bulunamadı.")
    curr_exe = os.path.abspath(sys.executable)
    staged_exe = curr_exe + ".update"
    try:
        with open(staged_exe, "wb"):
            pass
        os.remove(staged_exe)
    except OSError as exc:
        raise PermissionError(
            "MedyaMate bu klasöre yazamıyor. Uygulamayı Belgeler veya Masaüstü gibi "
            "yazılabilir bir klasöre taşıyıp tekrar deneyin."
        ) from exc

    tmp_dir  = tempfile.mkdtemp(prefix="MedyaMate-update-")
    new_exe  = os.path.join(tmp_dir, "update.exe")
    try:
        # Yeni sürümü indir ve temel dosya imzasını doğrula.
        with requests.get(download_url, stream=True, timeout=(15, 90)) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with open(new_exe, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if progress_callback and total:
                        progress_callback(done / total * 100)
            if total and done != total:
                raise IOError("Güncelleme dosyası eksik indirildi. Tekrar deneyin.")

        with open(new_exe, "rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("İndirilen güncelleme geçerli bir Windows .exe dosyası değil.")

        # Uygulama kapandıktan sonra aynı klasördeki dosyayı değiştirip yeniden aç.
        shutil.copy2(new_exe, staged_exe)
        bat = os.path.join(tmp_dir, "updater.bat")
        bat_content = f'''@echo off
setlocal
for /L %%i in (1,1,30) do (
  move /Y "{staged_exe}" "{curr_exe}" >nul 2>&1
  if not errorlevel 1 goto launch
  timeout /t 1 /nobreak >nul
)
echo MedyaMate guncellenemedi. Dosya izinlerini kontrol edin.
goto cleanup
:launch
start "" "{curr_exe}"
:cleanup
timeout /t 2 /nobreak >nul
del "%~f0" >nul 2>&1
rmdir /s /q "{tmp_dir}" >nul 2>&1
'''
        with open(bat, "w", encoding="mbcs") as f:
            f.write(bat_content)

        subprocess.Popen(["cmd.exe", "/c", bat], shell=False,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        for path in (new_exe, staged_exe):
            try:
                os.remove(path)
            except OSError:
                pass
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def update_ytdlp(callback=None):
    """yt-dlp'yi en güncel sürüme yükseltir."""
    def _upd():
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True, text=True
            )
            if callback:
                callback(result.returncode == 0, result.stdout + result.stderr)
        except Exception as e:
            if callback:
                callback(False, str(e))

    threading.Thread(target=_upd, daemon=True).start()
