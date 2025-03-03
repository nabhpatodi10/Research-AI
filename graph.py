from dotenv import load_dotenv
load_dotenv()

from langchain_core.tools import tool

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from tools import tools
from nodes import Nodes
import structures
from agent import Agent

node = Nodes()
model_tool = tools()

@tool
def vector_search_tool(query: str) -> list:
    """Vector Store Search tool to access documents from the vector store based on the given search query"""
    return model_tool.vector_search_tool(query)

model = ChatGroq(model = "llama-3.3-70b-versatile")
long_model = ChatOpenAI(model = "gpt-4o-mini")

topic = "Text Extraction and Recognition Algorithms"

output_format = "professional report"

print("Starting the process\n\n----------------------------------\n\n")

related_topics = model.with_structured_output(structures.Related_Topics).invoke(node.get_related_topics(topic))

print(related_topics.topics, "\n\n----------------------------------\n\nsearch start")

search_dict = {i : 4 for i in related_topics.topics}
search_dict[topic] = 10

documents = model_tool.web_search_tool(search_dict)
print("search done\n\n----------------------------------\n\n")

outlines = ""
for doc in documents:
    outline = long_model.with_structured_output(schema=structures.Outline, method="json_schema").invoke(node.get_outline(doc.page_content))
    if outline:
        outlines += outline.as_str + "\n\n"

document_outline = long_model.with_structured_output(schema=structures.Outline, method="json_schema").invoke(node.generate_outline(topic, output_format, outlines))

print(document_outline.as_str, "\n\n----------------------------------\n\n")

perspectives = long_model.with_structured_output(structures.Perspectives).invoke(node.generate_perspectives(topic, outlines))

agents = []
for editor in perspectives.editors:
    agents.append({"Agent" : Agent([vector_search_tool]), "Persona" : editor.persona})
    print(editor.persona, "\n")
print("\n----------------------------------\n\n")

perspective_section_content = []
for section in document_outline.sections:
    content = ""
    for agent in agents:
        result = agent["Agent"].graph.invoke({"messages" : node.perspective_agent(agent["Persona"], topic, output_format, document_outline.as_str, section.as_str)})
        content += result["messages"][-1].content + "\n\n"
        print(result["messages"][-1].content, "\n")

    perspective_section_content.append(content)

print("\n----------------------------------\n\n")

final_section_content = []
for i in range(len(document_outline.sections)):
    content = long_model.with_structured_output(structures.ContentSection).invoke(node.generate_combined_section(perspective_section_content[i], topic, document_outline.as_str, document_outline.sections[i].as_str))
    final_section_content.append(content.as_str)
    print(content.as_str, "\n")

print("\n----------------------------------\n\nEND!")

model_tool.close_tools()
del model_tool