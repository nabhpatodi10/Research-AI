from dotenv import load_dotenv
load_dotenv()
import os
# from pymongo import MongoClient
from google.cloud.firestore import Client
# from langchain_mongodb import MongoDBAtlasVectorSearch, MongoDBChatMessageHistory
from langchain_google_firestore import FirestoreVectorStore, FirestoreChatMessageHistory
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from uuid import uuid4
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, AnyMessage
from langchain_core.tools import tool, BaseTool

class Database:

    # __client: MongoClient
    __embeddingModel: GoogleGenerativeAIEmbeddings
    __splitter: RecursiveCharacterTextSplitter
    # __vectorSearch: MongoDBAtlasVectorSearch

    def __init__(self, session_id: str):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account-key.json"
        # self.__client = MongoClient(os.getenv("MONGODB_URI"))
        # self.__vector_collection = self.__client["LangChain"]["vectors"]
        self.__firestore_client = Client(project=os.getenv("GOOGLE_PROJECT_ID"))
        # self.__chat_history = MongoDBChatMessageHistory(connection_string=os.getenv("MONGODB_URI"), database_name="LangChain", collection_name="chats", session_id=session_id)
        self.__firestore_chat_history = FirestoreChatMessageHistory(session_id=session_id, collection="chats", client=self.__firestore_client, encode_message=False)
        self.__embeddingModel = GoogleGenerativeAIEmbeddings(model = "models/text-embedding-004", google_api_key = os.getenv("GEMINI_API_KEY"))
        self.__splitter = RecursiveCharacterTextSplitter(chunk_size = 600, chunk_overlap = 100)
        # self.__vectorSearch = MongoDBAtlasVectorSearch(collection = self.__vector_collection, embedding = self.__embeddingModel)
        self.__firestore_vectorSearch = FirestoreVectorStore(collection = "vector", embedding_service=self.__embeddingModel, client = self.__firestore_client)
        # self.__retriever = self.__vectorSearch.as_retriever(search_type = "mmr", search_kwargs = {"k" : 10})
        self.__firestore_retriever = self.__firestore_vectorSearch.as_retriever(search_type = "mmr", search_kwargs = {"k" : 10})

    def add_data(self, documents: list[Document]) -> None:
        try:
            self.__splittedDocs = self.__splitter.split_documents(documents)
            uuids = [str(uuid4()) for _ in range(len(self.__splittedDocs))]
            test = self.__firestore_vectorSearch.add_documents(self.__splittedDocs, ids = uuids)
            # self.__vectorSearch.add_documents(self.__splittedDocs, ids = uuids)
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
            # self.__chat_history.add_user_message(message)
            self.__firestore_chat_history.add_user_message(message)
        except Exception as error:
            raise error
        
    def add_ai_message(self, message: str | AIMessage) -> None:
        try:
            # self.__chat_history.add_ai_message(message)
            self.__firestore_chat_history.add_ai_message(message)
        except Exception as error:
            raise error
        
    def add_message(self, message) -> None:
        try:
            # self.__chat_history.add_message(message)
            self.__firestore_chat_history.add_message(message)
        except Exception as error:
            raise error
        
    def get_messages(self) -> list[AnyMessage]:
        try:
            return self.__firestore_chat_history.messages
        except Exception as error:
            raise error
        
    def clear_chat(self) -> None:
        try:
            # self.__chat_history.clear()
            self.__firestore_chat_history.clear()
        except Exception as error:
            raise error
        
    def return_tool(self) -> list[BaseTool]:
        return [tool(self.vector_search_tool)]
        
    def close_connection(self) -> None:
        # self.__client.close()
        self.__firestore_client.close()
        # del self.__chat_history
        # del self.__client

# obj = Database("test")
# docs = obj.vector_search_tool("STORM Graph benefits features")
# import json
# d = json.loads(docs[0].page_content)
# print(d)
# print(d["content"])
# print(d["metadata"]["source"])