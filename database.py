import os
from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from uuid import uuid4
from langchain_core.documents import Document

class database:

    __client: MongoClient
    __embeddingModel: GoogleGenerativeAIEmbeddings
    __splitter: RecursiveCharacterTextSplitter
    __vectorSearch: MongoDBAtlasVectorSearch

    def __init__(self):
        self.__client = MongoClient(os.getenv("MONGODB_URI"))
        self.__collection = self.__client["LangChain"]["vectors"]
        self.__embeddingModel = GoogleGenerativeAIEmbeddings(model = "models/text-embedding-004", google_api_key = os.getenv("GEMINI_API_KEY"))
        self.__splitter = RecursiveCharacterTextSplitter(chunk_size = 600, chunk_overlap = 100)
        self.__vectorSearch = MongoDBAtlasVectorSearch(collection = self.__collection, embedding = self.__embeddingModel)
        self.__retriever = self.__vectorSearch.as_retriever(search_type = "mmr", search_kwargs = {"k" : 10})

    def add_data(self, documents: list) -> None:
        try:
            self.__splittedDocs = self.__splitter.split_documents(documents)
            uuids = [str(uuid4()) for _ in range(len(self.__splittedDocs))]
            self.__vectorSearch.add_documents(self.__splittedDocs, ids = uuids)
        except Exception as error:
            raise error

    def search_data(self, query: str) -> list[Document]:
        try:
            return self.__retriever.invoke(query)
        except Exception as error:
            raise error
        
    def close_connection(self) -> None:
        self.__client.close()