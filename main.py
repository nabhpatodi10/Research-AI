from dotenv import load_dotenv
load_dotenv()

# from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_core.callbacks import CallbackManager, StreamingStdOutCallbackHandler

from graph import Graph

model = ChatOllama(model = "llama3.2:3b-instruct-fp16",
                   verbose = True, streaming = True,
                   callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
                   num_thread=8,
                   num_batch = 512,
                   num_gpu=1)

# model = ChatGroq(model = "llama-3.3-70b-versatile", verbose = True, streaming = True)

agent = Graph(model)

topic = "Text Extraction and Recognition Algorithms"
output_format = "professional report"
print(agent.graph.invoke({"topic" : topic, "output_format" : output_format, "plan" : [], "index" : 0}, {"recursion_limit" : 100}))
agent.tools.close_tools()