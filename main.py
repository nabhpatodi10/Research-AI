from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq

from tools import tools

tool = tools()
tool_list = [tool.web_search_tool, tool.vector_search_tool]

model = ChatGroq(model = "llama-3.3-70b-versatile")