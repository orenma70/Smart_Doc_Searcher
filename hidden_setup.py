import json
from PyQt5 import QtWidgets, QtCore

CONFIG_FILE = "config_settings.json"


class SetupDialog(QtWidgets.QDialog):
    def __init__(self, parent_app):
        super().__init__(parent_app)
        self.parent_app = parent_app
        self.setWindowTitle("System Configuration")
        self.setMinimumWidth(350)
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()

        # --- Create Fields ---
        # Language Selection
        self.lang_cb = QtWidgets.QComboBox()
        self.lang_cb.addItems(["English", "Hebrew"])
        current_lang = getattr(self.parent_app, 'Language', 'Hebrew')
        self.lang_cb.setCurrentText("Hebrew" if current_lang == "Hebrew" else "English")

        # isLTR Toggle
        self.ltr_check = QtWidgets.QCheckBox("Enable LTR Mode")
        self.ltr_check.setChecked(not current_lang == "Hebrew")

        # Cloud Auto Toggle
        self.cloud_check = QtWidgets.QCheckBox("Auto-Sync Cloud (GCS)")
        self.cloud_check.setChecked(getattr(self.parent_app, 'hd_cloud_auto_toggle', True))

        # Voice Mode Selection
        self.voice_cb = QtWidgets.QComboBox()
        self.voice_cb.addItems(["auto", "manual"])
        self.voice_cb.setCurrentText(getattr(self.parent_app, 'Voice_recognition_mode', 'manual'))

        # --- Add to Form ---
        form_layout.addRow("Language:", self.lang_cb)
        form_layout.addRow("Layout Direction:", self.ltr_check)
        form_layout.addRow("Cloud Sync:", self.cloud_check)
        form_layout.addRow("Voice Mode:", self.voice_cb)
        layout.addLayout(form_layout)

        # --- Buttons (OK / Cancel) ---
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_results(self):
        """Returns a dictionary of the UI state."""
        return {
            "Language": "he-IL" if self.lang_cb.currentText() == "Hebrew" else "en-US",
            "isLTR": self.ltr_check.isChecked(),
            "hd_cloud_auto_toggle": self.cloud_check.isChecked(),
            "Voice_recognition_mode": self.voice_cb.currentText()
        }


def handle_setup_dialog(parent_app):
    """Call this from your main window button."""
    # 1. Password Protection
    text, ok = QtWidgets.QInputDialog.getText(
        parent_app, 'Security', 'Enter Password:', QtWidgets.QLineEdit.Password
    )

    if ok and text == "0901":
        # 2. Launch Dialog
        dialog = SetupDialog(parent_app)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # 3. Get data and update parent_app variables
            results = dialog.get_results()

            parent_app.Language = results["Language"]
            parent_app.isLTR = results["isLTR"]
            parent_app.hd_cloud_auto_toggle = results["hd_cloud_auto_toggle"]
            parent_app.Voice_recognition_mode = results["Voice_recognition_mode"]

            # 4. Immediate UI Update (Direction)
            direction = QtCore.Qt.LeftToRight if parent_app.isLTR else QtCore.Qt.RightToLeft
            parent_app.setLayoutDirection(direction)

            # 5. Persistent Save
            try:
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(results, f)
                QtWidgets.QMessageBox.information(parent_app, "Success", "Settings updated and saved.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(parent_app, "Error", f"Could not save config: {e}")
    elif ok:
        QtWidgets.QMessageBox.warning(parent_app, "Denied", "Incorrect Password")