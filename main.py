import sys
from PySide6.QtWidgets import QApplication
from app.logging_config import setup_logging
from app.windows import MainWindow

setup_logging()
app = QApplication(sys.argv)
app.setStyle('Fusion')
window = MainWindow()
window.show()
sys.exit(app.exec())
