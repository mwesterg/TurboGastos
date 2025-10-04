import os
import base64
import json
import time
import redis
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# --- Configuration ---
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_PATH = 'token.json'
CREDENTIALS_PATH = 'credentials.json'
REDIS_URL = os.getenv("REDIS_URL")
REDIS_STREAM_NAME = "gastos:msgs"

def get_gmail_service():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail labels.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # IMPORTANT: The user needs to place their credentials.json file
            # from the Google Cloud Console in the same directory as this script.
            if not os.path.exists(CREDENTIALS_PATH):
                print("Error: credentials.json not found.")
                print("Please download your credentials from the Google Cloud Console and place it in the same directory as this script.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service

def search_emails(service, query):
    """Search for emails matching the query."""
    result = service.users().messages().list(userId='me', q=query).execute()
    messages = []
    if 'messages' in result:
        messages.extend(result['messages'])
    while 'nextPageToken' in result:
        page_token = result['nextPageToken']
        result = service.users().messages().list(userId='me', q=query, pageToken=page_token).execute()
        if 'messages' in result:
            messages.extend(result['messages'])
    return messages

def get_email_content(service, msg_id):
    """Get the content of a specific email."""
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg['payload']
    headers = payload['headers']
    subject = ''
    for header in headers:
        if header['name'] == 'Subject':
            subject = header['value']
            break

    if 'parts' in payload:
        parts = payload['parts']
        data = parts[0]['body']['data']
    else:
        data = payload['body']['data']

    data = data.replace("-", "+").replace("_", "/")
    decoded_data = base64.b64decode(data)
    return subject, decoded_data.decode('utf-8')

def publish_to_redis(r, message):
    """Publish a message to the Redis stream."""
    r.xadd(REDIS_STREAM_NAME, message)

def main():
    """
    This script connects to the Gmail API, searches for emails from
    "Banco de Chile" with the subject "Compra con Tarjeta de Crédito",
    extracts the email content, and publishes it to a Redis stream.
    """
    print("Starting Gmail reader...")
    gmail_service = get_gmail_service()
    if not gmail_service:
        return

    r = redis.from_url(REDIS_URL, decode_responses=True)

    while True:
        print("Searching for new emails...")
        # Search for unread emails from "Banco de Chile" with the specified subject
        query = 'from:"Banco de Chile" subject:"Compra con Tarjeta de Crédito" is:unread'
        messages = search_emails(gmail_service, query)

        for msg in messages:
            msg_id = msg['id']
            subject, body = get_email_content(gmail_service, msg_id)
            print(f"Processing email: {subject}")

            # Create a message payload similar to the WhatsApp ingestor
            message = {
                "wid": f"gmail-{msg_id}",
                "chat_id": "gmail",
                "chat_name": "Gmail",
                "sender_id": "banco.de.chile@gmail.com",
                "sender_name": "Banco de Chile",
                "timestamp": int(time.time()),
                "type": "email",
                "body": body,
            }

            publish_to_redis(r, message)

            # Mark the email as read
            gmail_service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()

        print("Waiting for new emails...")
        time.sleep(60) # Check for new emails every 60 seconds

if __name__ == '__main__':
    main()
