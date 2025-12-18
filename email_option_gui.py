import sys
from config_reader import Language
from PyQt5.QtCore import QDate, Qt
from config_reader import email_used
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QLabel, QPushButton, QDateEdit, QCheckBox,
    QGroupBox, QSpinBox, QDialogButtonBox, QComboBox, QRadioButton, QWidget
)

# --- Constants for Styling ---
BUTTON_STYLE_OK = "background-color: #0000FF; color: white; border-radius: 4px; padding: 6px; min-width: 150px; min-height: 30px;"
BUTTON_STYLE_CANCEL = "background-color: #F44336; color: white; border-radius: 4px; padding: 6px; min-width: 150px; min-height: 20px;"

FONT_SIZE_QSS = "font-size: 16pt;"
FONT_SIZE_QSS_green = "font-size: 16pt; background-color: blue; color: white;"

if Language == "English":
    sc_str = "Search Criteria"
    esp_str="Email Search Parameters"
    gst_str = "General Search Term:"
    fm_str = "Full Match"
    mf_str = "Mailbox Folder:"
    email_str2 = "          Email"
    from_str = "From:"
    dr_str = "Date Range"
    fd_str2 = "From Date:"
    rd_str2 = "To Date:"
    ep_str = "Exact Period:"
    mf2_str = "Miscellaneous Filters"
    mha_str = "Must have attachment"
    msk_str = "Min Size (KB):"
    nt_str = "Newer Than"
    od_str="Older Than"
    ok_text = "Ok"
    cancel_text = "Cancel"
else:
    sc_str = "קריטריון לחיפוש"
    esp_str="פרמטרים לחיפוש באימייל"
    gst_str = "ביטוי כללי לחפוש"
    fm_str = "התאמה מלאה"
    mf_str = "ספריית מייל:"
    email_str2 = "              אימייל"
    from_str = "מאת:"
    dr_str = "טווח תאריכים"
    fd_str2 = "מתאריך:"
    rd_str2 = "עד תאריך:"
    ep_str = "טווח תאריכים:"
    mf2_str = "מסננים שונים"
    mha_str = "כולל קובץ מצורף"
    msk_str = "גודל מינימלי (KB):"
    nt_str = "חדש מ:"
    od_str="ישן מ:"
    ok_text = "אישור"
    cancel_text = "ביטול"







class EmailSearchDialog(QDialog):
    """
    A modal dialog for collecting ONLY the essential email search parameters.
    """


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(esp_str)
        self.setMinimumWidth(800)

        self.params = {}  # Dictionary to hold the collected data
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. Search Criteria Group (The main focus)
        criteria_group = QGroupBox(sc_str)
        criteria_layout = QVBoxLayout()
        self.setup_search_inputs(criteria_layout)
        criteria_group.setLayout(criteria_layout)
        main_layout.addWidget(criteria_group)

        # 2. Dialog Buttons (OK and Cancel)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        ok_button.setText(ok_text)
        cancel_button.setText(cancel_text)
        if ok_button:
            ok_button.setStyleSheet(BUTTON_STYLE_OK)
        if cancel_button:
            cancel_button.setStyleSheet(BUTTON_STYLE_CANCEL)

            # 2c. Add the QDialogButtonBox directly to the main layout
            main_layout.addWidget(self.button_box)

            # 2d. Connect Signals (CORRECT SIGNAL USAGE)
            # Connect the box's accepted signal to your custom method
            self.button_box.accepted.connect(self.accept_data)

            # Connect the box's rejected signal to the standard QDialog reject method
            self.button_box.rejected.connect(self.reject)



    def setup_search_inputs(self, main_layout):
        # --- Basic Search (Query, From, To) ---
        basic_search_layout = QGridLayout()

        # --- Row 0: General Search Term ---
        query_label = QLabel(gst_str)
        query_label.setStyleSheet(FONT_SIZE_QSS)


        self.query_input = QLineEdit("SmartSearch")
        self.query_input.setStyleSheet(FONT_SIZE_QSS)
        # The Query input occupies Row 0




        self.full_match_radio = QRadioButton(fm_str)
        self.full_match_radio.setStyleSheet(FONT_SIZE_QSS)



        # --- Row 1: Mailbox Folder (FIXED) ---
        directory_label = QLabel(mf_str)
        directory_label.setStyleSheet(FONT_SIZE_QSS)



        self.directory_input = QComboBox()

        # Add the standard mailboxes as items
        self.directory_input.addItem("INBOX")
        self.directory_input.addItem("SENT")  # Use the uppercase IMAP standard for clarity

        # Set 'INBOX' as the default selection (it's index 0, but good practice to ensure)
        self.directory_input.setCurrentText("INBOX")
        self.directory_input.setStyleSheet(FONT_SIZE_QSS_green)

        email_label = QLabel(email_str2)
        email_label.setStyleSheet(FONT_SIZE_QSS)

        self.email_input = QComboBox()
        #self.email_input.currentTextChanged.connect(self.on_email_changed)
        # Add the standard mailboxes as items
        self.email_input.addItem("Gmail")
        self.email_input.addItem("Outlook")
        self.email_input.addItem("iCloud")
        self.email_input.addItem("Walla")

        # Set 'INBOX' as the default selection (it's index 0, but good practice to ensure)
        self.email_input.setCurrentText(email_used)
        self.email_input.setStyleSheet(FONT_SIZE_QSS_green)

        # The Directory input occupies Row 1



        # --- Row 2: From/To ---
        self.fromto_label = QLabel(from_str)
        self.fromto_label.setStyleSheet(FONT_SIZE_QSS)



        self.fromto_input = QLineEdit()
        self.fromto_input.setStyleSheet(FONT_SIZE_QSS)



        main_layout.addLayout(basic_search_layout)

        # --- Date/Attachment/Size Filter ---
        filter_layout = QHBoxLayout()

        # Date Filters
        date_group = QGroupBox(dr_str)
        date_group.setStyleSheet(FONT_SIZE_QSS)
        date_layout = QGridLayout()

        fromLable=QLabel(fd_str2)
        fromLable.setStyleSheet(FONT_SIZE_QSS)


        self.date_from_input = QDateEdit(QDate.currentDate().addMonths(-12))
        self.date_from_input.setStyleSheet(FONT_SIZE_QSS)
        self.date_from_input.setCalendarPopup(True)

        todatelable=QLabel(rd_str2)
        todatelable.setStyleSheet(FONT_SIZE_QSS)


        self.date_to_input = QDateEdit(QDate.currentDate())
        self.date_to_input.setStyleSheet(FONT_SIZE_QSS)
        self.date_to_input.setCalendarPopup(True)


        self.exact_date_combo = QComboBox()
        self.exact_date_combo.addItem("")

        if Language != "English":
            self.setLayoutDirection(Qt.RightToLeft)

        basic_search_layout.addWidget(query_label, 0, 0)
        basic_search_layout.addWidget(self.query_input, 0, 1)
        basic_search_layout.addWidget(self.full_match_radio, 0, 2)



        basic_search_layout.addWidget(directory_label, 1, 0)  # Now in Row 1
        basic_search_layout.addWidget(self.directory_input, 1, 1)
        basic_search_layout.addWidget(email_label, 1, 2)  # Now in Row 1
        basic_search_layout.addWidget(self.email_input, 1, 3)


        basic_search_layout.addWidget(self.fromto_label, 2, 0)  # Now in Row 2
        basic_search_layout.addWidget(self.fromto_input, 2, 1)  # Now in Row 2
        date_layout.addWidget(fromLable, 0, 0)
        date_layout.addWidget(self.date_from_input, 0, 1)
        date_layout.addWidget(todatelable, 1, 0)
        date_layout.addWidget(self.date_to_input, 1, 1)
        date_layout.addWidget(self.date_from_input, 0, 1)
        date_layout.addWidget(self.date_to_input, 1, 1)
        date_layout.addWidget(QLabel(ep_str), 2, 0)





        if Language == "English":


            for m in range(1, 12):
                if m == 1 :
                    self.exact_date_combo.addItem(f"{m} Month", m)
                else:
                    self.exact_date_combo.addItem(f"{m} Months", m)

            for y in range(1, 11):
                if y == 1:
                    self.exact_date_combo.addItem(f"{y} Year", y)
                else:
                    self.exact_date_combo.addItem(f"{y} Years", y)


        else:


            for y in range(1, 11):
                if y == 1:
                    self.exact_date_combo.addItem(f"שנה")
                elif y == 2:
                    self.exact_date_combo.addItem(f"שנתיים")
                else:
                    self.exact_date_combo.addItem(f" שנים{y}", y)

            for m in range(1, 12):
                    if m == 1:
                        self.exact_date_combo.addItem(f"חודש")
                    elif m == 2:
                        self.exact_date_combo.addItem(f"חודשיים")
                    else:
                        self.exact_date_combo.addItem(f" חודשים {m}", m)



        date_layout.addWidget(self.exact_date_combo, 2, 1)

        # Toggle layout for Newer/Older
        period_toggle_layout = QVBoxLayout()
        self.radio_newer = QRadioButton(nt_str)
        self.radio_older = QRadioButton(od_str)
        self.radio_newer.setChecked(True)  # Default
        period_toggle_layout.addWidget(self.radio_newer)
        period_layout_widget = QWidget()  # Container to help alignment
        period_toggle_layout.addWidget(self.radio_older)
        date_layout.addLayout(period_toggle_layout, 2, 2)

        date_group.setLayout(date_layout)
        filter_layout.addWidget(date_group)

        misc_group = QGroupBox(mf2_str)
        misc_group.setStyleSheet(FONT_SIZE_QSS)
        misc_layout = QVBoxLayout()

        self.has_attachment_check = QCheckBox(mha_str)
        self.has_attachment_check.setStyleSheet(FONT_SIZE_QSS)
        misc_layout.addWidget(self.has_attachment_check)

        size_layout = QHBoxLayout()
        minsizelable = QLabel(msk_str)
        minsizelable.setStyleSheet(FONT_SIZE_QSS)
        size_layout.addWidget(minsizelable)
        self.min_size_input = QSpinBox()
        self.min_size_input.setValue(100)
        self.min_size_input.setRange(0, 10000000)
        size_layout.addWidget(self.min_size_input)
        misc_layout.addLayout(size_layout)

        misc_group.setLayout(misc_layout)
        filter_layout.addWidget(misc_group)

        main_layout.addLayout(filter_layout)
        self.directory_input.currentTextChanged.connect(self.update_fromto_label)

    def on_email_changed(self, new_email):
        self.email_input.setCurrentText(new_email)


    def update_fromto_label(self, selected_directory):

        # We can check for 'INBOX' or 'SENT' (case-insensitive for robustness)
        cleaned_dir = selected_directory.upper()

        if "SENT" in cleaned_dir:
            # For the SENT folder, the user probably wants to see who they sent it TO
            self.fromto_label.setText("To:")
        elif "INBOX" in cleaned_dir or "TRASH" in cleaned_dir:
            # For INBOX/TRASH, the user probably wants to see who it's FROM
            self.fromto_label.setText("From:")
        else:
            self.fromto_label.setText("From:")


    def get_search_parameters(self):
        """Gathers all input values."""
        # Convert QDateTime to Unix timestamps (seconds since epoch)
        from config_reader import read_setup

        date_from_ts = self.date_from_input.dateTime().toSecsSinceEpoch()
        date_to_ts = self.date_to_input.dateTime().toSecsSinceEpoch() + 86400 # end of day
        directory = self.directory_input.currentText()
        query = self.query_input.text()

        attachment_str = f"has:attachment larger:{self.min_size_input.value()}" if self.has_attachment_check.isChecked() else ""
        from_str = f"from:{self.fromto_input.text()}" if self.fromto_input.text() else ""


        val = self.exact_date_combo.currentData()
        provider_key = self.email_input.currentText()

        email=read_setup(provider_key+"_address")


        # 2. Get the display text to check if it's "Months" or "Years"
        text = self.exact_date_combo.currentText()

        if val:
            # Determine suffix: 'm' for months, 'y' for years
            suffix = "m" if "Months" in text else "y"

            # Check your radio buttons for the operator
            operator = "newer_than" if self.radio_newer.isChecked() else "older_than"

            # Result: "newer_than:5m" or "older_than:2y"
            oldernewer_str = f"{operator}:{val}{suffix}"
        else:
            oldernewer_str = ""

        if self.full_match_radio.isChecked():
            gmail_raw_query=f'{from_str} "{query}" {attachment_str} {oldernewer_str}'
        else:
            gmail_raw_query = f'{from_str} {query} {attachment_str} {oldernewer_str}'


        return {
            "query": query,
            "directory": directory,
            "fromto_address": self.fromto_input.text(),
            "has_attachment": self.has_attachment_check.isChecked(),
            "date_from_ts": date_from_ts,
            "date_to_ts": date_to_ts,
            "min_size_kb": self.min_size_input.value(),
            "gmail_raw_query": gmail_raw_query,
            "provider_key": provider_key,
            "email": email,
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