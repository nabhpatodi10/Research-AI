import os
from googleapiclient.discovery import build
from authorisation import authorisation

class CustomSearch:
    def __init__(self):
        self.__auth = authorisation()
        self.__creds = self.__auth.cred_token_auth()
        self.__service = build("customsearch", "v1", credentials=self.__creds)
    
    def search(self, query: str, num: int) -> dict[str, str]:
        try:
            search = self.__service.cse().list(
                cx=os.getenv("SEARCH_ENGINE_ID"),
                lr="lang_en",
                num=num,
                q=query,
                c2coff=1,
                orTerms="Research Paper|Article|Research Article|Research|Latest|News",
                hl="en"
            ).execute()
            items = search["items"]
            urls = {item["link"]: item["title"] for item in items}
            return urls
        
        except Exception as error:
            raise error