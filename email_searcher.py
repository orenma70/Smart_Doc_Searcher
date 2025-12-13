from PyQt5.QtCore import QObject, pyqtSignal
import imaplib
import email
import email.header
import socket  # Added for connection timeout handling



EMAIL_PROVIDERS = {
    "gmail": {
        "server": "imap.gmail.com",
        "port": 993
    },
    "outlook": {
        "server": "outlook.office365.com",
        "port": 993
    },
    "walla": {
        "server": "imap.walla.co.il",
        "port": 993
    },
    # Add other providers here...
}


class EmailSearchWorker(QObject):
    # Signal to send results back to the GUI (list of strings)
    search_finished = pyqtSignal(list)

    def __init__(self, query, folder, email_user, email_password, imap_server, imap_port, parent=None):
        super().__init__(parent)
        self.query = query
        self.folder = folder
        self.user = email_user
        self.password = email_password
        self.server = imap_server
        self.port = imap_port

    def run(self):
        results = []
        mail = None  # Initialize mail to None for finally block check

        try:
            # Set a general timeout to prevent infinite blocking on connection
            socket.setdefaulttimeout(10)

            # 1. Connect and Login
            mail = imaplib.IMAP4_SSL(self.server, self.port)
            mail.login(self.user, self.password)

            # 2. Select Mailbox (Folder)
            # The folder name is often case-sensitive (e.g., 'INBOX', not 'inbox')
            status, data = mail.select(self.folder, readonly=True)

            if status != 'OK':
                raise ValueError(f"Could not select mailbox '{self.folder}'. Check folder name.")

            # 3. Search the Mailbox
            # Search criteria: Find emails where the query is in the BODY (content).
            # Using BODY is generally safer and returns relevant results.
                # The search value is the string inside the quotes:


            imap_search_prefix = 'BODY'

            # 2. Add the query, enclosed in double quotes as required by IMAP.
            #    The IMAP command structure will be 'SEARCH CHARSET UTF-8 BODY "Don’t get rusty"'
            #    We use 'BODY' as the search key.

            # We must manually escape backslashes and double quotes in the query
            # for IMAP literal safety, though for the curly apostrophe it's often fine.

            # Full search criteria string, ready to be encoded:
            search_criteria = f'{imap_search_prefix} "{self.query}"'
            quoted_query = f'"{self.query}"'
            search_criteria = f'CHARSET utf-8 {imap_search_prefix} {quoted_query}'
            #search_criteria = f'{imap_search_prefix} "{self.query}"'
            encoded_criteria = search_criteria.encode('utf-8')

            # 3. Execute the search command. The first argument is the CHARSET,
            #    and the second is the fully constructed command string (as bytes).
            #    This method forces imaplib to handle the complex encoding correctly.
            search_criteria_args = (
                'CHARSET',  # Argument 1: The key for encoding
                'UTF-8',  # Argument 2: The encoding value
                imap_search_prefix,  # Argument 3: The IMAP search key (e.g., 'BODY')
                self.query.encode('utf-8')  # Argument 4: The query value (as a byte literal)
            )
            # Encode the command *after* adding the quotes


             # The search call uses 'UTF-8' as the charset argument, and the encoded criteria
            #status, data = mail.search('UTF-8', encoded_criteria)
            #status, data = mail.search(*search_criteria_args)
            status, data = mail.search("UTF-8", f'(BODY {quoted_query})')





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

        #self.dir_edit.setText(folder_tmp)
        #self.search_input.setText(query_tmp)
        #self.g31_container.setStyleSheet(Container_STYLE_QSSgray)

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