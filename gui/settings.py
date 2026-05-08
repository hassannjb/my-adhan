from PyQt5.QtWidgets import QDialog, QVBoxLayout, QDoubleSpinBox, QPushButton, QFormLayout, QComboBox

from adhan.models import Config

_METHODS = ["NORTH_AMERICA", "MUSLIM_WORLD_LEAGUE", "ISNA", "UMM_AL_QURA", "EGYPTIAN"]


class SettingsDialog(QDialog):
    """
    Modal settings editor.  Accepts a Config on open, exposes an updated
    Config via .config after the user saves.
    """

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setGeometry(200, 200, 300, 250)
        self.setStyleSheet("background-color: #2c3e50; color: white;")
        self.config = config

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.method_input = QComboBox()
        self.method_input.addItems(_METHODS)
        self.method_input.setCurrentText(config.method)
        form_layout.addRow("Method:", self.method_input)

        self.fajr_input = QDoubleSpinBox()
        self.fajr_input.setValue(config.fajr_angle)
        self.fajr_input.setRange(0.0, 30.0)
        self.fajr_input.setSingleStep(0.5)
        form_layout.addRow("Fajr Angle:", self.fajr_input)

        self.isha_input = QDoubleSpinBox()
        self.isha_input.setValue(config.isha_angle)
        self.isha_input.setRange(0.0, 30.0)
        self.isha_input.setSingleStep(0.5)
        form_layout.addRow("Isha Angle:", self.isha_input)

        layout.addLayout(form_layout)

        save_button = QPushButton("Save Settings")
        save_button.setStyleSheet("background-color: #27ae60; padding: 5px;")
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def _save(self) -> None:
        self.config.method = self.method_input.currentText()
        self.config.fajr_angle = self.fajr_input.value()
        self.config.isha_angle = self.isha_input.value()
        self.accept()
