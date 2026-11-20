# MedyaMate

**Windows için müzik ve video indirme aracı.** Desteklenen bağlantılardan içerikleri MP3, M4A, WAV, FLAC, MP4 veya MKV olarak kaydedin; bağlantıyı yapıştırınca medya bilgisini görün ve önizlemeyi uygulama içinde açın.

**A lightweight Windows media downloader.** Save supported media links as MP3, M4A, WAV, FLAC, MP4, or MKV, preview media inside the app, and receive in-app update notifications.

---

## Özellikler

- YouTube ve Shorts, TikTok, Instagram, X/Twitter ve yt-dlp tarafından desteklenen diğer bağlantılar
- MP3, M4A, WAV, FLAC, MP4 ve MKV çıktı seçenekleri
- Kalite seçimi, birden fazla bağlantıyı sıraya alma ve indirme ilerlemesi
- Uygulama içinde ses/video önizlemesi ve kapak görseli
- İndirme geçmişi, URL geçmişi, koyu/açık tema ve sistem tepsisi
- GitHub Releases üzerinden sürüm kontrolü ve kullanıcı onayıyla uygulama güncellemesi
- Sürüm etiketi gönderildiğinde Windows `.exe` dosyasını otomatik derleyip GitHub Release'e yükleyen GitHub Actions iş akışı

## Features

- YouTube and Shorts, TikTok, Instagram, X/Twitter, and other sites supported by yt-dlp
- MP3, M4A, WAV, FLAC, MP4, and MKV output formats
- Quality selection, download queue, and progress reporting
- In-app audio/video preview and cover artwork
- Download and URL history, light/dark themes, and system tray support
- Version checks and user-approved app updates through GitHub Releases
- GitHub Actions builds and publishes a Windows `.exe` when a version tag is pushed

## Kurulum ve kullanım · Installation and usage

1. [Releases](../../releases/latest) sayfasından `MedyaMate.exe` dosyasını indirin.
2. `.exe` dosyasını çalıştırın. **Python kurmanız gerekmez.** FFmpeg, yayınlanan Windows dosyasına eklenir.
3. Uygulama içi medya önizlemesi için bilgisayarda VLC Media Player kurulu olmalıdır. İndirme ve dönüştürme özellikleri önizleme oynatıcısından bağımsızdır.
4. Bir bağlantıyı yapıştırın, biçim ve kaliteyi seçin, ardından **İndir**'e basın.

> Yalnızca erişim izniniz olan ve indirilmesi uygun içerikleri kaydedin. Bazı platformlar özel, yaş kısıtlamalı veya oturum gerektiren içeriklere erişimi engelleyebilir.

1. Download `MedyaMate.exe` from the [latest release](../../releases/latest).
2. Run the `.exe`; **Python is not required**. FFmpeg is bundled with the published Windows build.
3. VLC Media Player must be installed for in-app playback previews. Downloading and conversion do not depend on the preview player.
4. Paste a link, choose an output format and quality, then select **Download**.

> Only save content you are authorized to access and download. Some platforms restrict private, age-gated, or login-required media.

## Güncellemeler · Updates

Uygulama her açılışta GitHub Releases'taki en son sürümü arka planda kontrol eder. Yeni sürüm bulunduğunda uygulama içinde **İndir ve güncelle** seçeneği görünür. Kullanıcı bu seçeneğe basınca `.exe` indirilir; uygulama yeniden başlatılarak güncelleme tamamlanır.

The app checks GitHub Releases in the background each time it starts. When a newer release is available, an **İndir ve güncelle (Download and update)** button appears in the app. The update is downloaded only after the user selects it, then the app restarts into the new version.

### Yeni sürüm yayınlama · Publishing a release

1. Değişiklikleri GitHub deposuna gönderin.
2. Yeni sürüm etiketi oluşturup gönderin; örneğin `v1.0.1`:

   ```bash
   git tag v1.0.1
   git push origin v1.0.1
   ```

3. GitHub Actions sürüm numarasını ve depo adresini uygulamaya ekler, Python 3.11 ile tek dosyalı Windows uygulamasını derler ve `MedyaMate.exe` dosyasını yeni Release'e ekler.
4. Kullanıcılar uygulamayı bir sonraki açışlarında güncelleme bildirimini görür.

Push your changes to GitHub, then push a version tag such as `v1.0.1`. GitHub Actions embeds the tag and repository, builds the standalone Windows app, and attaches `MedyaMate.exe` to that release. Users are notified the next time they start the app.

## Geliştirme · Development

Windows geliştirme ortamı için Python 3.11 ve Tcl/Tk gerekir:

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
python -m pip install -r requirements.txt pyinstaller
python main.py
```

Python 3.11 with Tcl/Tk is required only to run from source. To build locally, place `ffmpeg.exe` and `ffprobe.exe` in the project root, then run:

```powershell
pyinstaller --noconfirm --clean build.spec
```

The standalone output is `dist/MedyaMate.exe`. Release builds are produced by `.github/workflows/release.yml`.

## Data and updates · Veri ve güncelleme bilgisi

- Uygulama geçmişi ve tercihleri Windows'ta `%APPDATA%\MedyaMate\history.json` içinde saklanır.
- Automatic replacement requires write access to the folder containing `MedyaMate.exe`. Keep the app in a user-writable folder such as Downloads or a folder under your profile.
- Source runs use the repository at `config.py`'s `GITHUB_REPO` setting. Release builds automatically embed their GitHub repository address.

