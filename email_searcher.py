from PyQt5.QtCore import QObject, pyqtSignal
import imaplib, ssl, sys, re
import email
import email.header
import socket  # Added for connection timeout handling
from PyQt5.QtWidgets import QApplication
from PyQt5 import QtCore
import configparser
import smtplib


EMAIL_PROVIDERS = {
    "Gmail": {
        "server": "imap.gmail.com",
        "port": 993
    },
    "Outlook": {
        "server": "outlook.office365.com",
        "port": 993
    },
    "Walla": {
        "server": "imap.walla.co.il",
        "port": 993
    },
    "iCloud": {
        "server": "imap.mail.me.com",
        "port": 993
    },
    # Add other providers here...
}


class EmailSearchWorker(QObject):
    # Signal to send results back to the GUI (list of strings)
    search_finished = pyqtSignal(list)

    def __init__(self, query, folder, email_user, email_password, imap_server, imap_port, gmail_raw_query, provider_key, parent=None):
        super().__init__(parent)
        self.query = query
        self.folder = folder
        self.user = email_user
        self.password = email_password
        self.server = imap_server
        self.port = imap_port
        self.gmail_raw_query = gmail_raw_query
        self.provider_key = provider_key

    def search_emails_api(self):
        results = []
        mail = None  # Initialize mail to None for finally block check

        try:
            # Set a general timeout to prevent infinite blocking on connection
            socket.setdefaulttimeout(10)

            # 1. Connect and Login

            mail = imaplib.IMAP4_SSL(self.server, self.port)
            mail._encoding = 'utf-8'
            mail.login(self.user, self.password)


            # 2. Select Mailbox (Folder)
            # The folder name is often case-sensitive (e.g., 'INBOX', not 'inbox')

            mail_dir =self.folder

            mail_dir_lower = mail_dir.lower()

            if self.provider_key == "Gmail" and "sent" in mail_dir_lower:
                status, data = mail.select('"[Gmail]/Sent Mail"', readonly=True)

            elif self.provider_key == "iCloud" and "sent" in mail_dir_lower:
                # iCloud usually uses "Sent Messages"
                status, data = mail.select('"Sent Messages"', readonly=True)

            else:
                # Default for Inbox or custom folders
                status, data = mail.select(self.folder, readonly=True)




            if status != 'OK':
                raise ValueError(f"Could not select mailbox '{self.folder}'. Check folder name.")

            # 3. Search the Mailbox


            encoded_query_bytes = self.query.encode('utf-8')

            # The standard IMAP command arguments for a BODY search:
            # Note: All these strings are ASCII, so they won't cause the crash.
            search_args = [
                'CHARSET',
                'UTF-8',
                'BODY',
                encoded_query_bytes  # <-- This is the bytes literal we prepared
            ]

            # --- 3b. Add Attachment/Size Criteria (Optional) ---
            params = self.gmail_raw_query
            has_attach = str(params.get("has_attachment", False))

            if has_attach == "True":
                min_size_kb = str(1024 * (params.get("min_size_kb", 0) + 122))
                search_args.append('LARGER')
                search_args.append(min_size_kb)  # min_size_kb is also an ASCII safe string

            # --- 3c. Execute the Search ---
            # mail.search accepts the arguments as an unpacked list (*search_args)
            print(f"Executing IMAP search with args: {search_args}")  # DEBUG: See the command being built
            #status, data = mail.search(None, *search_args)

            params = self.gmail_raw_query
            min_size_kb=str(1024*(params["min_size_kb"]+122)) # add 122k for minimal text
            has_attach = str(params["has_attachment"])
            if has_attach == "True":
                status, data = mail.search("UTF-8", 'BODY', f'"{self.query}"','LARGER',min_size_kb)
            else:
                status, data = mail.search(None, *search_args)

            #status, data = mail.search("UTF-8",  gmail_raw_query) # 'X-GM-RAW',





            if status == 'OK':
                # Data contains a space-separated list of email IDs (e.g., b'1 2 3')
                email_ids = data[0].split()

                # 4. Fetch the data for each email (Limit to 50 for performance)
                for mail_id in email_ids[:50]:
                    # Fetch only the ENVELOPE (Subject, From, Date)
                    status, msg_data = mail.fetch(mail_id, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])')

                    if status == 'OK' and msg_data[0] is not None:
                        raw_msg = msg_data[0][1]
                        msg = email.message_from_bytes(raw_msg)

                        # Decode the subject line safely (handles various encodings)
                        subject_header = email.header.decode_header(msg['Subject'])[0]
                        subject = subject_header[0]
                        encoding = subject_header[1]

                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or 'utf-8', errors='ignore')

                        sender = msg['From']
                        date = msg['Date']

                        # 5. Compile the result string
                        result_str = f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n---"
                        results.append(result_str)

            if not results:
                results.append(f"No emails found matching '{self.query}' in folder '{self.folder}'.")

        except imaplib.IMAP4.error as e:
            # Authentication, select mailbox errors
            error_message = f"IMAP Error: Check username/password/folder: {e}"
            results.append(f"--- ERROR: {error_message} ---")

        except ValueError as e:
            # Mailbox selection error
            error_message = f"Configuration Error: {e}"
            results.append(f"--- ERROR: {error_message} ---")

        except Exception as e:
            # General connection or unexpected error
            error_message = f"General Email Search Error: {e}"
            results.append(f"--- ERROR: {error_message} ---")


        finally:
            # 6. Logout and Cleanup
            if mail:
                try:
                    mail.close()
                    mail.logout()
                except:
                    pass

            # 7. Emit Results (Always happens, even on error)
            self.search_finished.emit(results)


# =========================================================================
# === STANDALONE TESTING CODE ===
# =========================================================================

class TestRunner(QObject):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.worker = None
        self.thread = None

    def handle_results(self, results):
        """Prints the results received from the worker and quits the application."""
        print("\n--- Search Results Received ---")
        for item in results:
            print(item)
        print("-----------------------------\n")

        # Stop the thread and quit the application gracefully
        if self.thread:
            self.thread.quit()
        self.app.quit()

    def start_test(self):
        """Sets up and starts the worker thread with dummy/test data."""

        print("Starting Email Search Worker Test...")
        params = launch_search_dialog()


        TEST_QUERY = params["query"]
        TEST_FOLDER = params["directory"]
        gmail_raw_query = params

        # --- ASSUME THESE ARE READ FROM NEW GUI INPUTS OR A CONFIG FILE ---
        TEST_EMAIL = params["email"]  # self.email_user_input.text()  # e.g., user@walla.co.il

        # Use re.findall() to extract all matches (the text within the capturing group)
        provider_key = params["provider_key"]
        TEST_PROVIDER_KEY = provider_key
        # --- DEFINE TEST PARAMETERS HERE ---

        provider_info = EMAIL_PROVIDERS[TEST_PROVIDER_KEY]
        if TEST_PROVIDER_KEY == "Gmail":
            TEST_PASSWORD = "netj diso xxfv syqi"
        elif TEST_PROVIDER_KEY == "iCloud":
            TEST_PASSWORD = "Lael0404"
        else:
            TEST_PASSWORD = "Jmjmjm2004"

        # Mock parameters for the gmail_raw_query argument
        TEST_GMAIL_PARAMS = params

        # --- Worker Setup ---
        self.worker = EmailSearchWorker(
            query=TEST_QUERY,
            folder=TEST_FOLDER,
            email_user=TEST_EMAIL,
            email_password=TEST_PASSWORD,
            imap_server=provider_info["server"],
            imap_port=provider_info["port"],
            gmail_raw_query=TEST_GMAIL_PARAMS,
            provider_key=TEST_PROVIDER_KEY
        )

        # --- Thread Setup ---
        self.thread = QtCore.QThread()
        self.worker.moveToThread(self.thread)

        # Connections
        self.thread.started.connect(self.worker.search_emails_api)
        self.worker.search_finished.connect(self.handle_results)

        # Start the thread
        self.thread.start()


if __name__ == '__main__':
    from email_option_gui import launch_search_dialog

    # 1. Create QApplication instance
    app = QApplication(sys.argv)

    # 2. Create the TestRunner
    runner = TestRunner(app)

    # 3. Start the test execution
    runner.start_test()

    # 4. Start the PyQt event loop (required for QThread/Signals to work)
    sys.exit(app.exec_())