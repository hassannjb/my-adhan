from PyQt6.QtWidgets import QDialog, QVBoxLayout, QDoubleSpinBox, QPushButton, QFormLayout, QComboBox


class SettingsDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setGeometry(200, 200, 300, 250)
        self.setStyleSheet("background-color: #2c3e50; color: white;")

        self.config = current_config
        layout = QVBoxLayout()
        form_layout = QFormLayout()

        # --- NEW: Method Dropdown ---
        self.method_input = QComboBox()
        methods = ["NORTH_AMERICA", "MUSLIM_WORLD_LEAGUE", "ISNA", "UMM_AL_QURA", "EGYPTIAN"]
        self.method_input.addItems(methods)

        # Set current method
        current_method = self.config.get('method', 'NORTH_AMERICA')
        self.method_input.setCurrentText(current_method)
        form_layout.addRow("Method:", self.method_input)
        # ----------------------------

        # Fajr Angle Input
        self.fajr_input = QDoubleSpinBox()
        self.fajr_input.setValue(self.config['fajr_angle'])
        self.fajr_input.setRange(0.0, 30.0)
        self.fajr_input.setSingleStep(0.5)
        form_layout.addRow("Fajr Angle:", self.fajr_input)

        # Isha Angle Input
        self.isha_input = QDoubleSpinBox()
        self.isha_input.setValue(self.config['isha_angle'])
        self.isha_input.setRange(0.0, 30.0)
        self.isha_input.setSingleStep(0.5)
        form_layout.addRow("Isha Angle:", self.isha_input)

        layout.addLayout(form_layout)

        # Save Button
        self.save_button = QPushButton("Save Settings")
        self.save_button.setStyleSheet("background-color: #27ae60; padding: 5px;")
        self.save_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

    def save_settings(self):
        self.config['method'] = self.method_input.currentText()
        self.config['fajr_angle'] = self.fajr_input.value()
        self.config['isha_angle'] = self.isha_input.value()
        self.accept()