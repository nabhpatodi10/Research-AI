from dotenv import load_dotenv
load_dotenv()

from typing import List, TypedDict
import time

from langchain_core.documents import Document
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from openai import RateLimitError

from tools import tools
from nodes import Nodes
import structures
from chains import Chains

class graphSchema(TypedDict):
    topic: str
    output_format: str
    related_topics: structures.Related_Topics
    urls: dict[str, str]
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
    
    def __init__(self, session_id: str):
        self.__node = Nodes()
        self.__model_tools = tools(session_id)
        self.__chains = Chains(self.__model_tools)
        self.__model = ChatGroq(model = "llama-3.3-70b-versatile", streaming = True)
        self.__long_model = ChatOpenAI(model = "gpt-4o-mini", streaming = True)
        __graph = StateGraph(graphSchema)
        __graph.add_node("related_topics_generation", self.__related_topics_generation)
        __graph.add_node("web_searching", self.__web_searching)
        __graph.add_node("web_scraping", self.__web_scraping)
        __graph.add_node("document_outline_generation", self.__document_outline_generation)
        __graph.add_node("perspectives_generation", self.__perspectives_generation)
        __graph.add_node("perspective_section_generation", self.__perspective_section_generation)
        __graph.add_node("final_section_generation", self.__final_section_generation)
        __graph.add_edge("related_topics_generation", "web_searching")
        __graph.add_edge("web_searching", "web_scraping")
        __graph.add_edge("web_scraping", "document_outline_generation")
        __graph.add_edge("document_outline_generation", "perspectives_generation")
        __graph.add_edge("perspectives_generation", "perspective_section_generation")
        __graph.add_edge("perspective_section_generation", "final_section_generation")
        __graph.add_edge("final_section_generation", END)
        __graph.set_entry_point("related_topics_generation")
        self.graph = __graph.compile()

    def __related_topics_generation(self, state: graphSchema):
        self.__model_tools.add_human_message(f"Topic: {state["topic"]}\nOutput Format: {state["output_format"]}")
        try:
            result = self.__model.with_structured_output(schema=structures.Related_Topics).invoke(self.__node.get_related_topics(state["topic"]))
            self.__model_tools.add_ai_message("Related Topics: " + result.as_str)
            return {"related_topics" : result}
        except RateLimitError:
            time.sleep(10)
            result = self.__model.with_structured_output(schema=structures.Related_Topics).invoke(self.__node.get_related_topics(state["topic"]))
            self.__model_tools.add_ai_message("Related Topics: " + result.as_str)
            return {"related_topics" : result}
        except Exception:
            result = self.__model.with_structured_output(schema=structures.Related_Topics).invoke(self.__node.get_related_topics(state["topic"]))
            self.__model_tools.add_ai_message("Related Topics: " + result.as_str)
            return {"related_topics" : result}
    
    def __web_searching(self, state: graphSchema):
        __search_dict = {i : 5 for i in state["related_topics"].topics}
        __search_dict[state["topic"]] = 10
        try:
            __urls = self.__chains.web_search(__search_dict)
            self.__model_tools.add_ai_message("Search URLs: " + ", ".join([url for url in __urls]).strip())
            return {"urls" : __urls}
        except Exception as error:
            raise error
        
    def __web_scraping(self, state: graphSchema):
        try:
            __documents = self.__chains.web_scrape(state["urls"])
            return {"documents" : __documents}
        except Exception as error:
            raise error
    
    def __document_outline_generation(self, state: graphSchema):
        __outlines = self.__chains.get_document_outline(state["documents"])
        try:
            document_outline = self.__long_model.with_structured_output(schema=structures.Outline).invoke(self.__node.generate_outline(state["topic"], state["output_format"], __outlines))
            self.__model_tools.add_ai_message(f"Document Outline:\n{document_outline.as_str}")
            return {"document_outline" : document_outline, "document_outlines" : __outlines}
        except RateLimitError:
            time.sleep(10)
            document_outline = self.__long_model.with_structured_output(schema=structures.Outline).invoke(self.__node.generate_outline(state["topic"], state["output_format"], __outlines))
            self.__model_tools.add_ai_message(f"Document Outline:\n{document_outline.as_str}")
            return {"document_outline" : document_outline, "document_outlines" : __outlines}
        except Exception:
            document_outline = self.__long_model.with_structured_output(schema=structures.Outline).invoke(self.__node.generate_outline(state["topic"], state["output_format"], __outlines))
            self.__model_tools.add_ai_message(f"Document Outline:\n{document_outline.as_str}")
            return {"document_outline" : document_outline, "document_outlines" : __outlines}

    def __perspectives_generation(self, state: graphSchema):
        try:
            perspectives = self.__long_model.with_structured_output(schema=structures.Perspectives).invoke(self.__node.generate_perspectives(state["topic"], state["document_outlines"]))
            self.__model_tools.add_ai_message(f"Perspectives:\n" + "\n\n".join([editor.persona for editor in perspectives.editors]).strip())
            return {"perspectives" : perspectives}
        except RateLimitError:
            time.sleep(10)
            perspectives = self.__long_model.with_structured_output(schema=structures.Perspectives).invoke(self.__node.generate_perspectives(state["topic"], state["document_outlines"]))
            self.__model_tools.add_ai_message(f"Perspectives:\n" + "\n\n".join([editor.persona for editor in perspectives.editors]).strip())
            return {"perspectives" : perspectives}            
        except Exception:
            perspectives = self.__long_model.with_structured_output(schema=structures.Perspectives).invoke(self.__node.generate_perspectives(state["topic"], state["document_outlines"]))
            self.__model_tools.add_ai_message(f"Perspectives:\n" + "\n\n".join([editor.persona for editor in perspectives.editors]).strip())
            return {"perspectives" : perspectives}

    def __perspective_section_generation(self, state: graphSchema):
        __perspective_section_content = []
        for section in state["document_outline"].sections:
            try:
                content_list = self.__chains.generate_perspective_content(state["perspectives"], state["topic"], state["output_format"], state["document_outline"].as_str, section.as_str)
                self.__model_tools.add_ai_message(f"{section.section_title} Content:\n" + "\n\n".join(content_list).strip())
                __perspective_section_content.append(content_list)
            except RateLimitError:
                time.sleep(10)
                content_list = self.__chains.generate_perspective_content(state["perspectives"], state["topic"], state["output_format"], state["document_outline"].as_str, section.as_str)
                self.__model_tools.add_ai_message(f"{section.section_title} Content:\n" + "\n\n".join(content_list).strip())
                __perspective_section_content.append(content_list)
            except Exception:
                content_list = self.__chains.generate_perspective_content(state["perspectives"], state["topic"], state["output_format"], state["document_outline"].as_str, section.as_str)
                self.__model_tools.add_ai_message(f"{section.section_title} Content:\n" + "\n\n".join(content_list).strip())
                __perspective_section_content.append(content_list)

        return {"perspective_content" : __perspective_section_content}
    
    def __final_section_generation(self, state: graphSchema):
        with open("output.md", "a", encoding="utf-8") as file:
            file.write("# " + state["document_outline"].page_title + "\n\n")
        __final_section_content = []
        for i in range(len(state["document_outline"].sections)):
            try:
                __content = self.__long_model.with_structured_output(schema=structures.ContentSection).invoke(self.__node.generate_combined_section(state["perspective_content"][i], state["topic"], state["document_outline"].as_str, state["document_outline"].sections[i].as_str))
            except RateLimitError:
                time.sleep(10)
                __content = self.__long_model.with_structured_output(schema=structures.ContentSection).invoke(self.__node.generate_combined_section(state["perspective_content"][i], state["topic"], state["document_outline"].as_str, state["document_outline"].sections[i].as_str))
            except Exception:
                __content = self.__long_model.with_structured_output(schema=structures.ContentSection).invoke(self.__node.generate_combined_section(state["perspective_content"][i], state["topic"], state["document_outline"].as_str, state["document_outline"].sections[i].as_str))

            __final_section_content.append(__content)
            with open("output.md", "a", encoding="utf-8") as file:
                file.write(__content.as_str + "\n\n")

        self.__model_tools.add_ai_message(f"Final Content:\n\n# {state["document_outline"].page_title}\n\n" + "\n\n".join([content.as_str for content in __final_section_content]))
        self.__model_tools.close_tools()

        return {"final_content" : __final_section_content}

graph = researchGraph("001")
result = graph.graph.invoke({"topic" : "Ethics, Governance, and Policy Frameworks for AI and SDGs", "output_format" : "Research Book Chapter"})