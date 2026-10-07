import sys
import os
import ctypes
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning, message="Several features with id.*")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pyogrio.*")

# Chromium GPU donanım hızlandırma ve konsol log susturma bayrakları
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --enable-gpu-rasterization --enable-zero-copy --ignore-gpu-blocklist"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, qInstallMessageHandler
from ui.main_window import MainWindow
from core.theme import ThemeManager

def _qt_message_filter(msg_type, context, message):
    if "Compositor returned null texture" in message or "null texture" in message:
        return
    if message:
        sys.stderr.write(f"{message}\n")

qInstallMessageHandler(_qt_message_filter)

def main():
    if os.name == 'nt':
        myappid = 'chiseleditor.app.1.0' 
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)

    # Kalıcı harita karosu (tile) önbelleği - 500 MB disk önbelleği
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "chisel_editor", "tiles")
        os.makedirs(cache_dir, exist_ok=True)
        profile.setCachePath(cache_dir)
        profile.setPersistentStoragePath(cache_dir)
        profile.setHttpCacheMaximumSize(500 * 1024 * 1024)
    except Exception:
        pass
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "resources", "img/chisel.ico")
    
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        print(f"Uyarı: İkon dosyası bulunamadı -> {icon_path}")
        
    ThemeManager.apply_theme(app, "light")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()