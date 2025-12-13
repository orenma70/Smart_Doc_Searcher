import sys
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QLabel, QPushButton, QDateTimeEdit, QCheckBox,
    QGroupBox, QSpinBox, QDialogButtonBox,
)
from PyQt5.QtCore import QDateTime, Qt, QObject, pyqtSignal

# --- Constants for Styling ---
BUTTON_STYLE_OK = "background-color: #4CAF50; color: white; border-radius: 4px; padding: 6px;"
BUTTON_STYLE_CANCEL = "background-color: #F44336; color: white; border-radius: 4px; padding: 6px;"

FONT_SIZE_QSS = "font-size: 14pt;"

class EmailSearchDialog(QDialog):
    """
    A modal dialog for collecting ONLY the essential email search parameters.
    """


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Email Search Parameters")
        self.setGeometry(100, 100, 700, 450)

        self.params = {}  # Dictionary to hold the collected data
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. Search Criteria Group (The main focus)
        criteria_group = QGroupBox("Search Criteria")
        criteria_layout = QVBoxLayout()
        self.setup_search_inputs(criteria_layout)
        criteria_group.setLayout(criteria_layout)
        main_layout.addWidget(criteria_group)

        # 2. Dialog Buttons (OK and Cancel)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        main_layout.addWidget(self.button_box)

        # Connect Signals
        self.button_box.accepted.connect(self.accept_data)
        self.button_box.rejected.connect(self.reject)



    def setup_search_inputs(self, main_layout):
        # --- Basic Search (Query, From, To) ---
        basic_search_layout = QGridLayout()

        # --- Row 0: General Search Term ---
        query_label = QLabel("General Search Term:")
        query_label.setStyleSheet(FONT_SIZE_QSS)
        basic_search_layout.addWidget(query_label, 0, 0)

        self.query_input = QLineEdit()
        self.query_input.setStyleSheet(FONT_SIZE_QSS)
        # The Query input occupies Row 0
        basic_search_layout.addWidget(self.query_input, 0, 1, 1, 3)

        # --- Row 1: Mailbox Folder (FIXED) ---
        directory_label = QLabel("Mailbox Folder:")
        directory_label.setStyleSheet(FONT_SIZE_QSS)
        basic_search_layout.addWidget(directory_label, 1, 0)  # Now in Row 1

        self.directory_input = QLineEdit("INBOX")
        self.directory_input.setStyleSheet(FONT_SIZE_QSS)
        # The Directory input occupies Row 1
        basic_search_layout.addWidget(self.directory_input, 1, 1, 1, 3)

        # --- Row 2: From/To ---
        from_label = QLabel("From:")
        from_label.setStyleSheet(FONT_SIZE_QSS)
        basic_search_layout.addWidget(from_label, 2, 0)  # Now in Row 2

        self.from_input = QLineEdit()
        self.from_input.setStyleSheet(FONT_SIZE_QSS)
        basic_search_layout.addWidget(self.from_input, 2, 1)  # Now in Row 2

        to_label = QLabel("To:")
        to_label.setStyleSheet(FONT_SIZE_QSS)
        basic_search_layout.addWidget(to_label, 2, 2)  # Now in Row 2

        self.to_input = QLineEdit()
        self.to_input.setStyleSheet(FONT_SIZE_QSS)
        basic_search_layout.addWidget(self.to_input, 2, 3)  # Now in Row 2

        main_layout.addLayout(basic_search_layout)

        # --- Date/Attachment/Size Filter ---
        filter_layout = QHBoxLayout()

        # Date Filters
        date_group = QGroupBox("Date Range")
        date_layout = QGridLayout()

        date_layout.addWidget(QLabel("From Date:"), 0, 0)
        self.date_from_input = QDateTimeEdit(QDateTime.currentDateTime().addMonths(-1))
        self.date_from_input.setCalendarPopup(True)
        date_layout.addWidget(self.date_from_input, 0, 1)

        date_layout.addWidget(QLabel("To Date:"), 1, 0)
        self.date_to_input = QDateTimeEdit(QDateTime.currentDateTime())
        self.date_to_input.setCalendarPopup(True)
        date_layout.addWidget(self.date_to_input, 1, 1)

        date_group.setLayout(date_layout)
        filter_layout.addWidget(date_group)

        # Attachment/Size Filters
        misc_group = QGroupBox("Miscellaneous Filters")
        misc_layout = QVBoxLayout()

        self.has_attachment_check = QCheckBox("Must have attachment")
        misc_layout.addWidget(self.has_attachment_check)

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Min Size (KB):"))
        self.min_size_input = QSpinBox()
        self.min_size_input.setRange(0, 100000)
        size_layout.addWidget(self.min_size_input)
        misc_layout.addLayout(size_layout)

        misc_group.setLayout(misc_layout)
        filter_layout.addWidget(misc_group)

        main_layout.addLayout(filter_layout)

    def get_search_parameters(self):
        """Gathers all input values."""
        # Convert QDateTime to Unix timestamps (seconds since epoch)
        date_from_ts = self.date_from_input.dateTime().toSecsSinceEpoch()
        date_to_ts = self.date_to_input.dateTime().toSecsSinceEpoch()

        return {
            "query": self.query_input.text(),
            "directory": self.directory_input.text(),
            "from_address": self.from_input.text(),
            "to_address": self.to_input.text(),
            "has_attachment": self.has_attachment_check.isChecked(),
            "date_from_ts": date_from_ts,
            "date_to_ts": date_to_ts,
            "min_size_kb": self.min_size_input.value()
        }

    def accept_data(self):
        """Called when the user clicks the OK button. Stores params and closes."""
        self.params = self.get_search_parameters()
        self.accept()

    # ----------------------------------------------------------------------


# FUNCTION TO LAUNCH AND GET DATA
# ----------------------------------------------------------------------

# FUNCTION TO LAUNCH AND GET DATA
# ----------------------------------------------------------------------

def launch_search_dialog():
    """
    Launches the dialog modally, waits for the user to click OK/Cancel,
    and returns the collected parameters if accepted.
    """
    # 1. Ensure QApplication is running (safe way)
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # 2. Instantiate the dialog
    dialog = EmailSearchDialog()

    # 3. exec_() is called: Script pauses, dialog is displayed.
    #
    result = dialog.exec_()

    # 4. If the user clicked OK (result is QDialog.Accepted), return the stored parameters
    if result == QDialog.Accepted:
        return dialog.params

    # 5. If the user clicked Cancel, return None
    return None

if __name__ == '__main__':
    # --- How to call it and get the result ---

    print("Launching search parameter dialog. Execution will pause until you click OK/Cancel.")

    parameters = launch_search_dialog()

    if parameters:
        print("\n✅ Dialog closed and Parameters returned:")
        for key, value in parameters.items():
            print(f"  {key:<15}: {value}")

    else:
        print("\n❌ User clicked Cancel or closed the dialog.")