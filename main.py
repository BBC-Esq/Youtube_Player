import sys
from PySide6.QtWidgets import QApplication
from app.child_processes import hide_console_windows
from app.core.app_settings import migrate_registry_settings
from app.logging_config import setup_logging
from app.windows import MainWindow

setup_logging()
hide_console_windows()
migrate_registry_settings()
app = QApplication(sys.argv)
app.setStyle('Fusion')
window = MainWindow()
window.show()
sys.exit(app.exec())
