from dotenv import load_dotenv
load_dotenv()
import os
from google.cloud.firestore import Client
from langchain_google_firestore import FirestoreVectorStore, FirestoreChatMessageHistory
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from uuid import uuid4
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, AnyMessage
from langchain_core.tools import tool, BaseTool
import copy

class Database:

    def __init__(self, session_id: str):
        self.__firestore_client = Client(project=os.getenv("GOOGLE_PROJECT_ID"))
        self.__firestore_chat_history = FirestoreChatMessageHistory(session_id=session_id, collection="chats", client=self.__firestore_client, encode_message=False)
        self.__embeddingModel = GoogleGenerativeAIEmbeddings(model = "models/text-embedding-004", google_api_key = os.getenv("GEMINI_API_KEY"))
        self.__splitter = RecursiveCharacterTextSplitter(chunk_size = 600, chunk_overlap = 100)
        self.__firestore_vectorSearch = FirestoreVectorStore(collection = "vector", embedding_service=self.__embeddingModel, client = self.__firestore_client)
        self.__firestore_retriever = self.__firestore_vectorSearch.as_retriever(search_type = "mmr", search_kwargs = {"k" : 10})

    def add_data(self, documents: list[Document]) -> None:
        try:
            self.__splittedDocs = self.__splitter.split_documents(documents)
            uuids = [str(uuid4()) for _ in range(len(self.__splittedDocs))]
            test = self.__firestore_vectorSearch.add_documents(self.__splittedDocs, ids = uuids)
        except Exception as error:
            raise error

    def vector_search_tool(self, query: str) -> list[Document]:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        try:
            __documents = self.__firestore_retriever.invoke(query)
            return __documents
        except Exception as error:
            raise error
        
    def add_human_message(self, message: str | HumanMessage) -> None:
        try:
            self.__firestore_chat_history.add_user_message(message)
        except Exception as error:
            raise error
        
    def add_ai_message(self, message: str | AIMessage) -> None:
        try:
            self.__firestore_chat_history.add_ai_message(message)
        except Exception as error:
            raise error
        
    def add_message(self, message) -> None:
        try:
            self.__firestore_chat_history.add_message(message)
        except Exception as error:
            raise error
        
    def get_messages(self) -> list[AnyMessage]:
        try:
            return copy.deepcopy(self.__firestore_chat_history.messages)
        except Exception as error:
            raise error
        
    def clear_chat(self) -> None:
        try:
            self.__firestore_chat_history.clear()
        except Exception as error:
            raise error
        
    def return_tool(self) -> list[BaseTool]:
        return [tool(self.vector_search_tool)]
        
    def close_connection(self) -> None:
        self.__firestore_client.close()