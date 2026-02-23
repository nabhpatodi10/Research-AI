import asyncio
from typing import Any

from langchain_core.tools import tool, BaseTool
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI

from custom_search import CustomSearch
from scrape import Scrape
from database import Database
from nodes import Nodes
from pdf_processing import PdfProcessingService
from settings import build_langsmith_thread_config, get_settings

class Tools:

    def __init__(
        self,
        session_id: str,
        database: Database,
        browser: Any,
        research_depth: str = "high",
    ):
        settings = get_settings()
        self.__search = CustomSearch()
        self.__database = database
        self.__session_id = session_id
        self.__thread_config = build_langsmith_thread_config(session_id)
        self.__model = ChatGoogleGenerativeAI(model = "models/gemini-flash-lite-latest")
        self.__nodes = Nodes()
        self.__pdf_processor = PdfProcessingService(
            session_id=session_id,
            database=database,
        )
        self.__scrape = Scrape(browser, pdf_processor=self.__pdf_processor)
        self.__web_search_total_timeout_seconds = settings.web_search_total_timeout_seconds
        self.__scrape_timeout_seconds = settings.web_search_scrape_timeout_seconds
        if research_depth == "low":
            self.__min_web_documents_before_stop = settings.min_web_documents_low
        elif research_depth == "medium":
            self.__min_web_documents_before_stop = settings.min_web_documents_medium
        else:
            self.__min_web_documents_before_stop = settings.min_web_documents_high

    async def __queue_pdf_fallback_if_needed(
        self,
        url: str,
        title: str | None,
        reason: str,
    ) -> None:
        try:
            if not await self.__pdf_processor.is_pdf_url(url):
                return
            await self.__pdf_processor.enqueue_background_job(
                url=url,
                title=title,
                reason=reason,
                partial_text_available=False,
            )
        except Exception as error:
            print(f"[pdf] Failed to queue background fallback for {url}: {error}")

    async def __scrape_with_timeout(
        self,
        url: str,
        title: str | None,
        timeout_seconds: float,
    ) -> Document | None:
        try:
            return await asyncio.wait_for(
                self.__scrape.scrape(url, title),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            print(f"Skipping {url}: scrape exceeded {timeout_seconds:.0f}s.")
            await self.__queue_pdf_fallback_if_needed(
                url=url,
                title=title,
                reason="scrape_timeout",
            )
            return None
        except asyncio.CancelledError:
            raise
        except Exception as error:
            print(f"Skipping {url}: {error}")
            return None

    async def __get_doc_summary(self, document: Document) -> str | None:
        if len(document.page_content.split()) < 3000:
            return document.page_content
        try:
            summary = await self.__model.ainvoke(
                self.__nodes.generate_rolling_summary(document.page_content),
                config=self.__thread_config,
            )
        except Exception:
            return None
        text = getattr(summary, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        content = getattr(summary, "content", "")
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif (
                    isinstance(item, dict)
                    and item.get("type") == "text"
                    and isinstance(item.get("text"), str)
                ):
                    parts.append(item["text"])
            return "\n".join(parts).strip()

        return str(content).strip()

    @staticmethod
    def __doc_metadata(document: Document) -> dict:
        metadata = document.metadata if isinstance(document.metadata, dict) else {}
        nested_metadata = metadata.get("metadata")
        if not isinstance(nested_metadata, dict):
            return metadata

        flattened = dict(nested_metadata)
        for key, value in metadata.items():
            if key == "metadata":
                continue
            flattened[key] = value
        return flattened

    def __doc_meta_value(self, document: Document, key: str, default: str = "None") -> str:
        metadata = self.__doc_metadata(document)
        value = metadata.get(key)
        if value is None:
            return default
        value_str = str(value).strip()
        return value_str if value_str else default

    async def __render_web_documents(self, documents: list[Document], summarize: bool = True) -> str:
        if not documents:
            return "Search results were found, but no scrapeable page content was extracted."

        if summarize:
            summaries = await asyncio.gather(*[self.__get_doc_summary(doc) for doc in documents])
        else:
            summaries = [doc.page_content for doc in documents]

        rendered_rows = []
        for index, doc in enumerate(documents):
            summary_text = summaries[index]
            if summary_text is None:
                summary_text = doc.page_content
            summary_text = str(summary_text or "").strip()
            if not summary_text:
                continue
            rendered_rows.append(
                f"Title: {self.__doc_meta_value(doc, 'title')}\n"
                f"Content:{summary_text}\n"
                f"Source: {self.__doc_meta_value(doc, 'source')}"
            )

        if not rendered_rows:
            return "Search results were found, but no scrapeable page content was extracted."
        return "\n----------------\n".join(rendered_rows)

    async def __web_search_impl(
        self,
        query: str,
        partial_documents: list[Document] | None = None,
        runtime_state: dict[str, bool] | None = None,
    ) -> str:
        __urls = await self.__search.search(query, 5)
        if not __urls:
            return "No search results found."

        per_url_timeout_seconds = self.__scrape_timeout_seconds
        overall_scrape_timeout_seconds = self.__scrape_timeout_seconds
        min_documents_before_stop = self.__min_web_documents_before_stop
        max_documents = 5

        scrape_tasks = {
            asyncio.create_task(
                self.__scrape_with_timeout(url, title, per_url_timeout_seconds)
            ): url
            for url, title in __urls.items()
        }

        documents: list[Document] = []
        seen_sources: set[str] = set()
        pending = set(scrape_tasks.keys())
        loop = asyncio.get_running_loop()
        deadline = loop.time() + overall_scrape_timeout_seconds

        try:
            while pending and len(documents) < max_documents:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break

                done, pending = await asyncio.wait(
                    pending,
                    timeout=remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    break

                for done_task in done:
                    try:
                        doc = done_task.result()
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        continue

                    if (
                        doc is None
                        or doc.page_content is None
                        or not doc.page_content.strip()
                    ):
                        continue

                    source = str(doc.metadata.get("source", "") or "")
                    if source in seen_sources:
                        continue
                    seen_sources.add(source)
                    documents.append(doc)
                    if partial_documents is not None:
                        partial_documents.append(doc)

                    if len(documents) >= max_documents:
                        break

                if len(documents) >= min_documents_before_stop:
                    break
        finally:
            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        if not documents:
            return "Search results were found, but no scrapeable page content was extracted."

        await self.__database.add_data(self.__session_id, documents)
        if runtime_state is not None:
            runtime_state["persisted"] = True
        return await self.__render_web_documents(documents, summarize=True)

    async def web_search_tool(self, query: str) -> str:
        """Web Search tool to access documents from the web based on the given search query"""
        partial_documents: list[Document] = []
        runtime_state = {"persisted": False}
        try:
            return await asyncio.wait_for(
                self.__web_search_impl(
                    query,
                    partial_documents=partial_documents,
                    runtime_state=runtime_state,
                ),
                timeout=self.__web_search_total_timeout_seconds,
            )
        except asyncio.TimeoutError:
            print(f"Web search tool exceeded total timeout of {self.__web_search_total_timeout_seconds:.0f}s.")
            if partial_documents:
                if not runtime_state.get("persisted", False):
                    try:
                        await self.__database.add_data(self.__session_id, partial_documents)
                    except Exception:
                        pass

                partial_output = await self.__render_web_documents(partial_documents, summarize=False)
                return (
                    f"{partial_output}\n\n"
                    "[Note: web search timed out before full completion. Returning partial results.]"
                )
            return "An error occured: web search tool timed out, you can try again with a different query."
        except Exception as e:
            return f"An error occured: {str(e)}"
    
    async def url_search_tool(self, url: str) -> str:
        """URL Search tool to access documents from the web based on the given URL"""
        try:
            document = await asyncio.wait_for(
                self.__scrape.scrape(url),
                timeout=self.__scrape_timeout_seconds,
            )
            if document is not None and document.page_content is not None and document.page_content.strip() != "":
                await self.__database.add_data(self.__session_id, [document])
                return (
                    f"Title: {self.__doc_meta_value(document, 'title')}\n"
                    f"Content:{document.page_content}\n"
                    f"Source: {self.__doc_meta_value(document, 'source')}"
                )
            else:
                return "No content found at the provided URL."
        except asyncio.TimeoutError:
            await self.__queue_pdf_fallback_if_needed(
                url=url,
                title=None,
                reason="url_tool_timeout",
            )
            return "No content found at the provided URL."
        except Exception as e:
            return f"An error occured: {str(e)}"
    
    async def vector_search_tool(self, query: str) -> str:
        """Vector Store Search tool to access documents from the vector store based on the given search query"""
        try:
            documents = await self.__database.vector_search(session_id=self.__session_id, query=query)
            if not documents:
                return "No relevant documents found in the vector store."

            return "\n----------------\n".join(
                [
                    f"Title: {self.__doc_meta_value(doc, 'title')}\nContent:{doc.page_content}\nSource: {self.__doc_meta_value(doc, 'source')}"
                    for doc in documents
                ]
            )
        except Exception as e:
            return f"An error occured: {str(e)}"
    
    def return_tools(self) -> list[BaseTool]:
        return [tool(self.vector_search_tool), tool(self.web_search_tool), tool(self.url_search_tool)]
