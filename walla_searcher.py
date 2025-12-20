import imaplib
import email
from email.header import decode_header
import datetime
from PyQt5.QtCore import QObject, pyqtSignal

# --- Configuration for Walla ---
WALLA_IMAP_SERVER = "imap.gmail.com"
WALLA_IMAP_PORT = 993


class WallaEmailSearcher(QObject):
    search_finished = pyqtSignal(list)

    def __init__(self, email_address, password, parent=None):
        super().__init__(parent)
        self.email_address = email_address
        self.password = password

    def _get_connection(self):
        """Creates an SSL connection to Walla IMAP server."""
        print(f"Connecting to Gmail Gateway for Walla...")
        mail = imaplib.IMAP4_SSL(WALLA_IMAP_SERVER, WALLA_IMAP_PORT)
        # Use the full email address as the username
        mail.login(self.email_address, self.password)
        return mail

    def search_emails_api(self, query=None, sender=None, date_from=None):
        results = []
        try:
            mail = self._get_connection()
            mail.select("INBOX")

            # Construct IMAP search criteria
            # Note: IMAP searching is more limited than Microsoft Graph
            search_criteria = []
            if query:
                search_criteria.append(f'TEXT "{query}"')
            if sender:
                search_criteria.append(f'FROM "{sender}"')

            # Default to ALL if no criteria provided
            criterion = " ".join(search_criteria) if search_criteria else "ALL"

            status, messages = mail.search(None, criterion)

            if status != "OK":
                return ["Error searching mailbox."]

            # Get the list of email IDs and take the last 25 (most recent)
            mail_ids = messages[0].split()
            recent_ids = mail_ids[-25:][::-1]  # Last 25, reversed

            for mail_id in recent_ids:
                res, msg_data = mail.fetch(mail_id, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        # Parse the bytes into an email object
                        msg = email.message_from_bytes(response_part[1])

                        subject = self._decode_mime_words(msg["Subject"])
                        from_ = self._decode_mime_words(msg["From"])
                        date_ = msg["Date"]

                        # Basic attachment check
                        has_attach = " [📎]" if msg.get_content_maintype() == 'multipart' else ""

                        results.append(
                            f"Date: {date_}\nFrom: {from_}\nSubject: {subject}{has_attach}\n---"
                        )

            mail.logout()

        except Exception as e:
            results.append(f"--- ERROR: {e} ---")
        finally:
            self.search_finished.emit(results)
            return results

    def _decode_mime_words(self, s):
        """Helper to decode Hebrew/Encoded headers."""
        if not s: return ""
        decoded_parts = decode_header(s)
        final_str = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                final_str += part.decode(encoding or 'utf-8', errors='replace')
            else:
                final_str += part
        return final_str


# --- Example Usage ---
if __name__ == '__main__':
    # WARNING: Walla may require you to enable "Less Secure Apps"
    # or generate an App Password if they use MFA.
    USER = "your_email@walla.co.il"
    PASS = "your_password"

    searcher = WallaEmailSearcher("orenma70@walla.com", "gjkk-momw-arkr-uhhv")
    results = searcher.search_emails_api(query="Smart")

    for item in results:
        print(item)