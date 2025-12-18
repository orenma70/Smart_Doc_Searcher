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

    def search_emails_api(self, query=None, sender=None, has_attachment=False, min_size=None, date_to=None ,date_from=None):
        results = []
        try:
            token = self._get_access_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'ConsistencyLevel': 'eventual'
            }

            # --- API Request ---
            endpoint = "https://graph.microsoft.com/v1.0/me/messages"
            params = {
                '$search': f'"{query}"' if query else None,
                '$select': 'id,subject,from,receivedDateTime,hasAttachments',  # Need 'id' to fetch attachments
                '$top': 25
            }

            response = requests.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            messages = response.json().get('value', [])

            if not messages:
                return [f"No results found for: {query}"]

            for msg in messages:
                msg_id = msg.get('id')
                subject = msg.get('subject') or "No Subject"
                from_dict = msg.get('from', {}).get('emailAddress', {})
                sender_display = f"{from_dict.get('name')} <{from_dict.get('address')}>"
                date_str = msg.get('receivedDateTime', '').replace('Z', '+00:00')

                # --- Attachment Filename Logic ---
                has_attach_bool = msg.get('hasAttachments', False)
                attach_icon = ""

                if has_attach_bool:
                    # Fetch the actual filenames for this specific message
                    attach_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments"
                    att_res = requests.get(attach_url, headers=headers)
                    if att_res.status_code == 200:
                        att_data = att_res.json().get('value', [])
                        fnames = [a.get('name') for a in att_data if a.get('name')]
                        attach_icon = f" [📎 {', '.join(fnames)}]" if fnames else " [📎]"

                # --- Filtering Logic ---
                # 1. Attachment Filter
                if has_attachment and not has_attach_bool:
                    continue

                # 2. Sender Filter
                if sender and sender.lower() not in sender_display.lower():
                    continue

                # 3. Date Filter (Fixing the logic: MUST be BETWEEN from and to)
                dt = datetime.datetime.fromisoformat(date_str)
                unix_ts = int(dt.timestamp())

                # If date_from is set, email must be >= date_from
                if date_from and unix_ts < date_from:
                    continue
                # If date_to is set, email must be <= date_to
                if date_to and unix_ts > date_to:
                    continue

                # 4. Success - Add to results
                results.append(
                    f"Date: {dt.strftime('%Y-%m-%d %H:%M')}\nFrom: {sender_display}\nSubject: {subject}{attach_icon}\n---")

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