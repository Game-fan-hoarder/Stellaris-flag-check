"""
Visual part of the project.
"""
import sys
import random
import tempfile

from sqlite3 import Connection
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QMainWindow
)

from .back import get_flag_dict

class MainWindow(QMainWindow):
    """The main display windows for the appplication."""

    connection: Connection
    def __init__(self):
        super().__init__()

        self.temp_dir = tempfile.TemporaryDirectory()


        QApplication.instance().aboutToQuit.connect(self.cleanup)

    def _init_database(self):
        """Generate the database for searching.
        Note: no cache...
        """
        self.connection = get_flag_dict(self.temp_dir)


    def cleanup(self):
        """Clean the folder where the temporary database was created."""
        self.temp_dir.cleanup()
        self.connection.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
