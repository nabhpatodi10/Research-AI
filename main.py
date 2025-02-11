from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from tools import web_search_tool, vector_search_tool, write_in_file_tool
from agents import SearchAgent

tools = [web_search_tool, vector_search_tool, write_in_file_tool]

model = ChatGroq(model = "llama-3.3-70b-versatile")

prompt = """You are a Ph.D graduate researcher and your job is to research on the given topics. \
You have to perform multiple tasks to copmplete the research, first plan the headings or the subtopics which would be included in the final document, \
then generate search queries for the main topic along with these sub topics, then search using these search queries and then based on the information \
received from these searches, edit the headings or the subtopics if required and generate search queries for the new subtopics and search about them.
Be in this loop until you have all the information you wanted. This information will automatically be stored in a vector store, so then start generating \
content under each heading or subtopic and append the content to the text file sub topic or heading wise, do not push the entire content together.
You are allowed to make multiple calls (either together or in sequence) to the given set of tools. If you need to look up some information before asking \
a follow up question, you are allowed to do that! You have to rely on the information provided to you by the tool call, you do not have to use any \
knowledge of your own.
The following are your tool names: web_search_tool, vector_search_tool, write_in_file_tool"""

agent = SearchAgent(model, tools, prompt)

messages = [HumanMessage(content = "Perform an extensive research about the new budget of India for 2025 and give me a proper report on it")]
result = agent.graph.invoke({"messages" : messages})
print(result)