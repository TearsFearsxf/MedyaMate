# PyInstaller .spec dosyası — tek .exe üretir.
# ffmpeg.exe varsa pakete eklenir; yoksa çalışma anında sistem PATH'i kullanılır.
import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[(name, '.') for name in ('ffmpeg.exe', 'ffprobe.exe') if os.path.isfile(name)],
    datas=[
        ('config.py',     '.'),
        ('history.py',    '.'),
        ('downloader.py', '.'),
        ('updater.py',    '.'),
        ('assets/medyamate.ico', 'assets'),
    ],
    hiddenimports=[
        'yt_dlp',
        'customtkinter',
        'PIL',
        'mutagen',
        'requests',
        'packaging',
        'vlc',
        'pystray',
        'pystray._win32',
        'darkdetect',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MedyaMate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Konsol penceresi çıkmasın
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/medyamate.ico',
)
