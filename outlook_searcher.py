import os, datetime
import requests
from msal import PublicClientApplication, SerializableTokenCache
from PyQt5.QtCore import QObject, pyqtSignal

# --- Configuration (Must match Azure Portal settings) ---
CLIENT_ID = "7d968b8e-8120-4468-bf09-4345def34e12"
TENANT_ID = 'common'
SCOPES = ['https://graph.microsoft.com/Mail.Read']
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
TOKEN_FILE = 'token_outlook.json'


class OutlookAPISearcher(QObject):
    search_finished = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 1. Setup Token Cache (similar to token.json in Gmail)
        self.token_cache = SerializableTokenCache()
        if os.path.exists(TOKEN_FILE):
            self.token_cache.deserialize(open(TOKEN_FILE, 'r').read())

        self.app = PublicClientApplication(
            CLIENT_ID, authority=AUTHORITY, token_cache=self.token_cache
        )

    def test_latest_emails(self):
        token = self._get_access_token()
        headers = {'Authorization': f'Bearer {token}'}

        # No search, no filter - just the raw last 5 items in the Inbox
        url = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$top=5&$select=subject,from,receivedDateTime"

        response = requests.get(url, headers=headers)
        data = response.json()

        for m in data.get('value', []):
            print(f"Subject: {m.get('subject')}")
            print(f"From: {m.get('from')}")

    def _get_access_token(self):
        """Authenticates and returns the Outlook access token."""
        target_email = "orenma70@outlook.com"
        accounts = self.app.get_accounts()
        result = None

        # 1. Look through the cache to find the specific account
        # We look for the one matching your 'username' (email)
        account_to_use = next((acc for acc in accounts if acc.get('username') == target_email), None)

        if account_to_use:
            # 2. Try to get the token silently for THAT specific account
            result = self.app.acquire_token_silent(SCOPES, account=account_to_use)

        if not result:
            # Opens browser for login - same as Gmail's flow
            result = self.app.acquire_token_interactive(
                scopes=SCOPES,
                login_hint="orenma70@outlook.com"  # <--- Set your email here
            )
            if self.token_cache.has_state_changed:
                with open(TOKEN_FILE, 'w') as f:
                    f.write(self.token_cache.serialize())

        return result.get("access_token")

    def search_emails_api(self, query=None, sender=None, has_attachment=False, min_size=None, date_from=None,
                          date_to=None):
        results = []
        try:
            token = self._get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'ConsistencyLevel': 'eventual'  # <--- THIS IS CRITICAL
            }



            final_query = query

            # --- API Request ---
            endpoint = "https://graph.microsoft.com/v1.0/me/messages"
            params = {
                # Remove the { } and use quotes around the string variable
                '$search': f'{final_query}',
                '$select': 'subject,from,receivedDateTime,hasAttachments',
                '$top': 25
            }

            response = requests.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            messages = response.json().get('value', [])

            if not messages:
                return [f"No results found for: {final_query}"]

            for msg in messages:
                subject = msg.get('subject') or "No Subject"
                from_info = msg.get('from', {}).get('emailAddress', {})
                to_info = msg.get('sender', {}).get('emailAddress', {})
                sender_display = f"{from_info.get('name')} <{from_info.get('address')}>"
                date = msg.get('receivedDateTime', '')
                attach = " [📎]" if msg.get('hasAttachments') else ""

                attach_flag = True
                sender_flag = True
                date_flag = True

                if has_attachment:
                   if not attach:
                       attach_flag =False

                if sender:
                    if sender not in sender_display:
                        sender_flag = False

                dt = datetime.datetime.fromisoformat(date)
                unix_timestamp = int(dt.timestamp())

                if unix_timestamp>date_from or unix_timestamp<date_to:
                    date_flag = False






                if sender_flag and attach_flag and date_flag:
                    results.append(f"Date: {date}\nFrom: {sender_display}\nSubject: {subject}{attach}\n---")


        except Exception as e:
            results.append(f"--- ERROR: {e} ---")
        finally:
            self.search_finished.emit(results)
            return results


# --- Example Usage for Outlook ---
if __name__ == '__main__':
    searcher = OutlookAPISearcher()


    results = searcher.search_emails_api('Smart')
    for item in results:
        print(item)