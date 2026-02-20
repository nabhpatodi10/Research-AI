import asyncio
import json
from typing import Any

from google.cloud.firestore import FieldFilter
from langchain_core.documents import Document
from uuid_utils import uuid7


class DatabaseVectorMixin:
    def _clear_vector_store_sync(self, session_id: str, batch_size: int = 5000) -> int | None:
        collection_ref = self._firestore_client.collection("vector")
        session_filter = FieldFilter("metadata.session_id", "==", session_id)

        deleted = 0

        while True:
            docs = list(collection_ref.where(filter=session_filter).limit(batch_size).stream())
            if not docs:
                break
            batch = self._firestore_client.batch()
            for doc in docs:
                batch.delete(doc.reference)
                deleted += 1
            batch.commit()

        return deleted

    async def clear_vector_store(self, session_id: str, batch_size: int = 5000) -> int | None:
        return await asyncio.to_thread(self._clear_vector_store_sync, session_id, batch_size)

    def _delete_vector_source_sync(
        self,
        session_id: str,
        source_url: str,
        batch_size: int = 500,
    ) -> int:
        if not source_url:
            return 0

        collection_ref = self._firestore_client.collection("vector")
        session_filter = FieldFilter("metadata.session_id", "==", session_id)
        base_query = (
            collection_ref.where(filter=session_filter)
            .order_by("__name__")
            .limit(batch_size)
        )

        deleted = 0
        last_doc = None
        while True:
            query = base_query if last_doc is None else base_query.start_after(last_doc)
            docs = list(query.stream())
            if not docs:
                break

            batch = self._firestore_client.batch()
            batch_count = 0
            for doc in docs:
                payload = doc.to_dict() or {}
                metadata = payload.get("metadata")
                source = ""
                if isinstance(metadata, dict):
                    source = str(metadata.get("source") or "")
                if source != source_url:
                    continue
                batch.delete(doc.reference)
                batch_count += 1

            if batch_count > 0:
                batch.commit()
                deleted += batch_count

            last_doc = docs[-1]

        return deleted

    async def replace_source_data(
        self,
        session_id: str,
        source_url: str,
        documents: list[Document],
    ) -> None:
        await asyncio.to_thread(
            self._delete_vector_source_sync,
            session_id,
            source_url,
        )
        await self.add_data(session_id, documents)

    async def add_data(self, session_id: str, documents: list[Document]) -> None:
        if not documents:
            print(f"No documents to add for session {session_id}.")
            return

        vector_store = await self.vector_store()
        split_docs = self._splitter.split_documents(documents)
        if not split_docs:
            print(f"Splitter returned no chunks for session {session_id}.")
            return

        for split_doc in split_docs:
            metadata = dict(split_doc.metadata or {})
            metadata["session_id"] = session_id
            split_doc.metadata = metadata

        ids = [str(uuid7()) for _ in range(len(split_docs))]
        try:
            added = await vector_store.aadd_documents(split_docs, ids=ids)
            if isinstance(added, list) and len(added) == 0:
                print(f"Vector store add returned no ids for session {session_id}.")
            else:
                added_count = len(added) if isinstance(added, list) else len(split_docs)
                print(f"Added {added_count}/{len(split_docs)} vector chunks for session {session_id}.")
            return
        except Exception as bulk_error:
            added_count = 0
            for doc, doc_id in zip(split_docs, ids):
                try:
                    await vector_store.aadd_documents([doc], ids=[doc_id])
                    added_count += 1
                except Exception:
                    continue

            if added_count == 0:
                raise bulk_error

            print(
                f"Partially added {added_count}/{len(split_docs)} vector chunks for session {session_id}."
            )

    @staticmethod
    def _normalize_vector_metadata(metadata: Any) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        if not isinstance(metadata, dict):
            return normalized

        nested_metadata = metadata.get("metadata")
        if isinstance(nested_metadata, dict):
            normalized.update(nested_metadata)

        for field_name in ("source", "title", "session_id"):
            field_value = metadata.get(field_name)
            if field_value is not None:
                normalized[field_name] = field_value

        reference = metadata.get("reference")
        if isinstance(reference, dict):
            reference_path = reference.get("path")
            if isinstance(reference_path, str) and reference_path.strip():
                normalized["reference_path"] = reference_path

        if not normalized:
            return dict(metadata)
        return normalized

    @staticmethod
    def _extract_vector_page_content(
        page_content: Any,
        metadata: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(page_content, str):
            stripped = page_content.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    return page_content, metadata

                if isinstance(payload, dict):
                    payload_metadata = payload.get("metadata")
                    if isinstance(payload_metadata, dict):
                        merged_metadata = dict(payload_metadata)
                        merged_metadata.update(metadata)
                        metadata = merged_metadata

                    payload_content = payload.get("content")
                    if isinstance(payload_content, str):
                        return payload_content, metadata

            return page_content, metadata

        return str(page_content or ""), metadata

    def _normalize_vector_documents(
        self,
        session_id: str,
        documents: list[Document],
    ) -> list[Document]:
        normalized_documents: list[Document] = []
        for document in documents:
            metadata = self._normalize_vector_metadata(getattr(document, "metadata", {}))
            page_content, metadata = self._extract_vector_page_content(
                getattr(document, "page_content", ""),
                metadata,
            )

            cleaned_content = str(page_content or "").strip()
            if not cleaned_content:
                continue

            if not metadata.get("session_id"):
                metadata["session_id"] = session_id

            normalized_documents.append(
                Document(page_content=cleaned_content, metadata=metadata)
            )

        return normalized_documents

    async def vector_search(self, session_id: str, query: str) -> list[Document]:
        vector_store = await self.vector_store()
        session_filter = FieldFilter("metadata.session_id", "==", session_id)
        documents = await vector_store.amax_marginal_relevance_search(
            query=query,
            k=5,
            fetch_k=50,
            filters=session_filter,
        )
        return self._normalize_vector_documents(session_id=session_id, documents=documents)
