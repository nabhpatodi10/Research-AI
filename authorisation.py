import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

class authorisation():
    __SCOPES = ["https://www.googleapis.com/auth/cse"]
    
    def cred_token_auth(self):
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", self.__SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif creds and (creds.expired or not creds.valid):
                os.remove("token.json")
            else:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", self.__SCOPES)
                creds = flow.run_local_server()
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        return creds