from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

# --- Configuration ---
# Define the scopes (permissions) needed. Read-only is usually sufficient for searching.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
USER_ID = 'me'  # Represents the authenticated user


class GmailAPISearcher:

    def __init__(self, credentials_path='credentials.json'):
        self.credentials_path = credentials_path
        self.service = self._get_gmail_service()

    def _get_gmail_service(self):
        """Authenticates and returns the Gmail service object."""
        creds = None

        # Load existing token if available (handles the OAuth flow refresh)
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        # If no (valid) credentials exist, authorize the user
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                # Note: This will open a browser window for initial authentication
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        return build('gmail', 'v1', credentials=creds)

    def search_emails_api(self, query_string):
        """
        Searches Gmail using a standard Gmail query string (q parameter).

        Example query_string: 'in:inbox חנוכה larger:500k'
        """
        results = []
        try:
            # 1. Search for Message IDs matching the query
            response = self.service.users().messages().list(
                userId=USER_ID,
                q=query_string,
                maxResults=50  # API is limited to 50 results per call by default
            ).execute()

            messages = response.get('messages', [])
            if not messages:
                results.append("No emails found matching the query via Gmail API.")
                return results

            # 2. Fetch Headers for Display
            for message in messages:
                # Use the 'metadata' format to fetch only the required headers efficiently
                msg_data = self.service.users().messages().get(
                    userId=USER_ID,
                    id=message['id'],
                    format='metadata',
                    metadataHeaders=['Subject', 'From', 'Date']
                ).execute()

                headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}

                # 3. Compile the result string
                result_str = (
                    f"Date: {headers.get('Date', 'N/A')}\n"
                    f"From: {headers.get('From', 'N/A')}\n"
                    f"Subject: {headers.get('Subject', 'N/A')}\n---"
                )
                results.append(result_str)

        except Exception as e:
            results.append(f"--- ERROR: Gmail API Search Error: {e} ---")

        return results


# --- Example Usage (Assuming credentials.json is set up) ---
if __name__ == '__main__':
    # Your Hebrew query string, exactly as you would type it in Gmail's search bar
    HEBREW_QUERY = 'חנוכה'

    # You would pass your full constructed query here, e.g., 'חנוכה larger:10k'
    api_searcher = GmailAPISearcher()
    api_results = api_searcher.search_emails_api(HEBREW_QUERY)

    print("\n--- Gmail API Search Results ---")
    for item in api_results:
        print(item)
    print("------------------------------\n")