from typing import List, TypedDict
from dotenv import load_dotenv
load_dotenv()

from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from tools import tools
from nodes import Nodes
import structures
from chains import Chains

class graphSchema(TypedDict):
    topic: str
    output_format: str
    related_topics: structures.Related_Topics
    documents: List[Document]
    document_outlines: str
    document_outline: structures.Outline
    perspectives: structures.Perspectives
    perspective_content: List[List[str]]
    final_content: List[structures.ContentSection]

class researchGraph:

    __node: Nodes
    __model_tools: tools
    __chains: Chains
    __model: ChatGroq
    __long_model: ChatOpenAI
    
    def __init__(self):
        self.__node = Nodes()
        self.__model_tools = tools()
        self.__chains = Chains(self.__model_tools)
        self.__model = ChatGroq(model = "llama-3.3-70b-versatile", streaming = True)
        self.__long_model = ChatOpenAI(model = "gpt-4o-mini", streaming = True)
        __graph = StateGraph(graphSchema)
        __graph.add_node("related_topics_generation", self.__related_topics_generation)
        __graph.add_node("web_searching_and_scraping", self.__web_searching_and_scraping)
        __graph.add_node("document_outline_generation", self.__document_outline_generation)
        __graph.add_node("perspectives_generation", self.__perspectives_generation)
        __graph.add_node("perspective_section_generation", self.__perspective_section_generation)
        __graph.add_node("final_section_generation", self.__final_section_generation)
        __graph.add_edge("related_topics_generation", "web_searching_and_scraping")
        __graph.add_edge("web_searching_and_scraping", "document_outline_generation")
        __graph.add_edge("document_outline_generation", "perspectives_generation")
        __graph.add_edge("perspectives_generation", "perspective_section_generation")
        __graph.add_edge("perspective_section_generation", "final_section_generation")
        __graph.add_edge("final_section_generation", END)
        __graph.set_entry_point("related_topics_generation")
        self.graph = __graph.compile()

    def __related_topics_generation(self, state: graphSchema):
        return {"related_topics" : self.__model.with_structured_output(schema=structures.Related_Topics).invoke(self.__node.get_related_topics(state["topic"]))}
    
    def __web_searching_and_scraping(self, state: graphSchema):
        search_dict = {i : 4 for i in state["related_topics"].topics}
        search_dict[state["topic"]] = 10
        return {"documents" : self.__model_tools.web_search_tool(search_dict)}
    
    def __document_outline_generation(self, state: graphSchema):
        __outlines = self.__chains.get_document_outline(state["documents"])
        return {"document_outline" : self.__long_model.with_structured_output(schema=structures.Outline).invoke(self.__node.generate_outline(state["topic"], state["output_format"], __outlines)), "document_outlines" : __outlines}

    def __perspectives_generation(self, state: graphSchema):
        return {"perspectives" : self.__long_model.with_structured_output(schema=structures.Perspectives).invoke(self.__node.generate_perspectives(state["topic"], state["document_outlines"]))}

    def __perspective_section_generation(self, state: graphSchema):
        __perspective_section_content = []
        for section in state["document_outline"].sections:
            __perspective_section_content.append(self.__chains.generate_perspective_content(state["perspectives"], state["topic"], state["output_format"], state["document_outline"].as_str, section.as_str))
        return {"perspective_content" : __perspective_section_content}
    
    def __final_section_generation(self, state: graphSchema):
        __final_section_content = []
        for i in range(len(state["document_outline"].sections)):
            __content = self.__long_model.with_structured_output(schema=structures.ContentSection).invoke(self.__node.generate_combined_section(state["perspective_content"][i], state["topic"], state["document_outline"].as_str, state["document_outline"].sections[i].as_str))
            __final_section_content.append(__content)
            with open("output.md", "a", encoding="utf-8") as file:
                file.write(__content.as_str + "\n\n")
        return {"final_content" : __final_section_content}

graph = researchGraph()
result = graph.graph.invoke({"topic" : "Wearable Devices for IOT", "output_format" : "professional report"})