from dotenv import load_dotenv
load_dotenv()

import asyncio, os
from uuid_utils import uuid7
from google.cloud.firestore import Client
from langchain_google_firestore import FirestoreVectorStore, FirestoreChatMessageHistory
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

class Database:

    def __init__(self):
        self.__firestore_client = Client(project=os.getenv("GOOGLE_PROJECT_ID"))
        self.__embeddingModel = GoogleGenerativeAIEmbeddings(model_name="text-embedding-005", vertexai=True)
        self.__splitter = RecursiveCharacterTextSplitter(chunk_size=6500, chunk_overlap=200)

    async def chat(self, session_id: str) -> FirestoreChatMessageHistory:
        return FirestoreChatMessageHistory(session_id=session_id, collection="chats", client=self.__firestore_client, encode_message=False)
    
    async def vector_store(self, session_id: str) -> tuple[FirestoreVectorStore, VectorStoreRetriever]:
        vectorStore = FirestoreVectorStore(collection=session_id, embedding_service=self.__embeddingModel, client=self.__firestore_client)
        return (
            vectorStore,
            vectorStore.as_retriever(search_type="mmr", search_kwargs={"k": 10, "fetch_k": 50})
        )
    
    def _clear_vector_store_sync(self, session_id: str, batch_size: int = 5000) -> int | None:
        collection_ref = self.__firestore_client.collection(session_id)

        recursive_delete = getattr(self.__firestore_client, "recursive_delete", None)
        if callable(recursive_delete):
            return recursive_delete(collection_ref)

        deleted = 0

        while True:
            docs = list(collection_ref.limit(batch_size).stream())
            if not docs:
                break
            batch = self.__firestore_client.batch()
            for doc in docs:
                batch.delete(doc.reference)
                deleted += 1
            batch.commit()

        return deleted

    async def clear_vector_store(self, session_id: str, batch_size: int = 5000) -> int | None:
        return await asyncio.to_thread(self._clear_vector_store_sync, session_id, batch_size)

    async def add_data(self, session_id: str, documents: list[Document]) -> None:
        try:
            vector_store, _ = await self.vector_store(session_id)
            __splittedDocs = self.__splitter.split_documents(documents)
            uuids = [str(uuid7()) for _ in range(len(__splittedDocs))]
            test = await vector_store.aadd_documents(__splittedDocs, ids=uuids)
            if len(test) == 0:
                print("No document added")
        except Exception:
            try:
                vector_store, _ = await self.vector_store(session_id)
                __splittedDocs = self.__splitter.split_documents(documents)
                uuids = [str(uuid7()) for _ in range(len(__splittedDocs))]
                for i in range(len(__splittedDocs)):
                    try:
                        if isinstance(__splittedDocs[i], tuple):
                            __splittedDocs[i] = Document(__splittedDocs[i][0])
                        test = await vector_store.aadd_documents(__splittedDocs[i], ids=uuids[i])
                        if len(test) == 0:
                            print("No document added")
                    except Exception as error:
                        continue
            except Exception as error:
                raise error

    async def vector_search(self, session_id: str, query: str) -> list[Document]:
        try:
            _, retriever = await self.vector_store(session_id)
            __documents = await retriever.ainvoke(query)
            return __documents
        except Exception as error:
            raise error
        
    async def add_messages(self, session_id: str, message: BaseMessage | list[BaseMessage]) -> None:
        try:
            chat = await self.chat(session_id=session_id)
            if isinstance(message, list):
                return await chat.aadd_messages(message)
            return await chat.aadd_messages([message])
        except Exception as error:
            raise error
        
    async def get_messages(self, session_id: str) -> list[BaseMessage]:
        try:
            chat = await self.chat(session_id=session_id)
            return await chat.aget_messages()
        except Exception as error:
            raise error
        
    async def clear_chat(self, session_id: str) -> None:
        try:
            chat = await self.chat(session_id=session_id)
            await chat.aclear()
            await self.clear_vector_store(session_id=session_id)
        except Exception as error:
            raise error
        
    def close_connection(self) -> None:
        self.__firestore_client.close()