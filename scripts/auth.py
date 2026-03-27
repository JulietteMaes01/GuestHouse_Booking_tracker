"""
Google OAuth helpers.
On the first run this opens a browser window for authentication.
The resulting token is cached in token.pickle so subsequent runs are silent.
"""
import os
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import gspread

from config import CREDENTIALS_FILE, TOKEN_FILE, SCOPES, SPREADSHEET_ID, WORKSHEET_GID


def get_credentials():
    """Return valid Google OAuth credentials, refreshing or re-authenticating as needed."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as fh:
            creds = pickle.load(fh)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"'{CREDENTIALS_FILE}' not found.\n"
                    "Run  python setup.py  for step-by-step instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as fh:
            pickle.dump(creds, fh)

    return creds


def get_gmail_service():
    """Return an authenticated Gmail API service."""
    return build("gmail", "v1", credentials=get_credentials())


def get_sheets_client():
    """Return an authenticated gspread client."""
    return gspread.authorize(get_credentials())


def get_worksheet():
    """Return the booking worksheet."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return spreadsheet.get_worksheet_by_id(WORKSHEET_GID)
