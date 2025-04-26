import time

from langchain.schema.runnable import RunnableParallel, RunnableLambda
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from openai import RateLimitError
from playwright.async_api import Browser
import asyncio

from nodes import Nodes
from database import Database
from custom_search import CustomSearch
from scrape import Scrape
from expertagent import ExpertAgent
import structures

class Chains:

    __model: ChatOpenAI
    __node: Nodes
    __database: Database
    __customSearch: CustomSearch
    __scrape: Scrape

    def __init__(self, database: Database, browser: Browser):
        self.__model = ChatOpenAI(model = "gpt-4.1-nano")
        self.__node = Nodes()
        self.__customSearch = CustomSearch()
        self.__scrape = Scrape(browser)
        self.__database = database

    def web_search(self, queries: dict[str, int]) -> dict[str, str]:
        __chains = []
        for i in range(len(queries)):
            __chains.append(RunnableLambda(lambda input, i=i: self.__customSearch.search(input[f"chain{i}"][0], input[f"chain{i}"][1])))

        __final_chain = RunnableParallel({f"chain{i}" : chain for i, chain in enumerate(__chains)})

        try:
            __outputs = __final_chain.invoke({f"chain{i}" : (query, num) for i, (query, num) in enumerate(queries.items())})
            __urls = {}
            for output in __outputs:
                __urls.update(__outputs[output])
                for i in __outputs[output]:
                    print("Searched:", i)
            return __urls                

        except Exception as error:
            raise error
        
    async def web_scrape(self, urls: dict[str, str]) -> list[Document]:
        try:
            scrape_tasks = [self.__scrape.scrape(url, title) for url, title in urls.items()]
            documents = await asyncio.gather(*scrape_tasks)

            finaldocs = [doc for doc in documents if doc is not None]
            self.__database.add_data(finaldocs)
            print(f"\n\nTotal Documents: {len(finaldocs)}\n\n")
            return finaldocs
        except Exception as error:
            raise error

    def get_document_outline(self, documents: list[Document]) -> str:
        batch = []
        for document in documents:
            batch.append(self.__node.get_outline(document))
        
        try:
            __outlines = self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch)
        except RateLimitError:
            time.sleep(20)
            __outlines = self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch[len(batch)//2:])
            time.sleep(20)
            __outlines += self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch[:len(batch)//2])
        except Exception:
            time.sleep(40)
            __outlines = self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch[len(batch)//2:])
            time.sleep(40)
            __outlines += self.__model.with_structured_output(schema=structures.Outline, method="json_schema").batch(batch[:len(batch)//2])

        __stroutlines = ""
        for i in __outlines:
            __stroutlines += i.as_str + "\n\n--------------------------------\n\n"

        return __stroutlines
    
    def generate_perspective_content(self, perspectives: structures.Perspectives, topic: str, output_format: str, outline: str, section: str) -> list[str]:
        __chains = []
        
        def __return_dict(messages) -> dict:
            return {"messages" : messages}

        for i in range(len(perspectives.editors)):
            __agent = ExpertAgent(self.__database.return_tool())
            __chains.append(RunnableLambda(lambda _, i=i : self.__node.perspective_agent(perspectives.editors[i].persona, topic, output_format, outline, section)) | __return_dict | __agent.graph)

        __final_chain = RunnableParallel({f"chain{i}" : chain for i, chain in enumerate(__chains)})

        try:
            __results = __final_chain.invoke({})
        except RateLimitError:
            time.sleep(10)
            __results = __final_chain.invoke({})
            
        __final_result = []
        for i in __results:
            __final_result.append(__results[i]["messages"][-1].content)

        return __final_result