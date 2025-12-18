import imaplib
import email, re
import datetime
from email.utils import parsedate_to_datetime
from PyQt5.QtCore import QObject, pyqtSignal


class ICloudAPISearcher(QObject):
    search_finished = pyqtSignal(list)

    def __init__(self, email_user, email_password, server, parent=None):
        super().__init__(parent)
        self.username = email_user
        self.password = email_password  # NOT your Apple ID password
        self.server = server

    def search_emails_api(self, query=None, sender=None, has_attachment=False, min_size=None, date_to=None, date_from=None):
        results = []
        mail = None
        try:
            mail = imaplib.IMAP4_SSL(self.server)
            mail.login(self.username, self.password)
            mail.select("INBOX", readonly=True)

            search_criteria = f'TEXT "{query}"' if query else 'ALL'
            status, data = mail.search(None, search_criteria)
            email_ids = data[0].split()

            for mail_id in reversed(email_ids):
                if not mail_id: continue  # Skip empty results
                try:
                    # Fetch header only
                    #status, msg_data = mail.fetch(mail_id, '(BODY.PEEK[HEADER])')
                    status, msg_data = mail.fetch(mail_id, '(BODY.PEEK[HEADER] BODYSTRUCTURE)')

                    if status != 'OK' or not msg_data[0]: continue

                    msg = email.message_from_bytes(msg_data[0][1])
                    structure = str(msg_data[1])

                    # Decode Subject safely
                    raw_subject = msg.get('Subject', 'No Subject')
                    subj_parts = email.header.decode_header(raw_subject)
                    subject = "".join([
                        p[0].decode(p[1] or 'utf-8', errors='replace') if isinstance(p[0], bytes) else p[0]
                        for p in subj_parts
                    ])

                    sender_display = msg.get('From', 'Unknown')


                    date_str = msg.get("Date")

                    dt = parsedate_to_datetime(date_str)
                    unix_ts = int(dt.timestamp())
                    display_date = dt.strftime('%Y-%m-%d %H:%M')

                    # 4. Attachment Check (Looking at the BODYSTRUCTURE response)
                    content_type = msg.get('Content-Type', '')
                    has_attach = 'multipart/mixed' in content_type.lower()
                    if has_attach:
                        filenames = re.findall(r'\"FILENAME\" \"(.*?)\"', structure)
                        fname_str = filenames[0]
                        if len(filenames) > 1:
                            fname_str += " " + filenames[1]
                        if len(filenames) > 2:
                            fname_str += " " + filenames[2]
                        if len(filenames) > 3:
                            fname_str += f".. more  {len(filenames)-3} files"
                    else:
                        fname_str=""


                    attach_icon = " [📎]" if has_attach else ""
                    att_str = "has attachment" if has_attach else ""


                    # 5. Filtering logic using the Unix TS and Sender strings
                    date_flag = True
                    if date_from and unix_ts < date_from: date_flag = False
                    if date_to and unix_ts > date_to: date_flag = False

                    # Sender filter (Python side)
                    sender_flag = True
                    if sender and sender.lower() not in sender_display.lower():
                        sender_flag = False

                    if date_flag and sender_flag:
                        results.append(f"Subject: {subject}\nFrom: {sender_display}\nDate: {display_date}\n:{att_str} {attach_icon} {fname_str}\n---")


                except Exception as e:
                    print(f"Error on msg {mail_id}: {e}")
                    continue

        except Exception as e:
            results.append(f"--- ERROR: {e} ---")
        finally:
            if mail:
                try:
                    mail.logout()
                except:
                    pass
            self.search_finished.emit(results)
            return results