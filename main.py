from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from graph import Graph

model = ChatGroq(model = "llama-3.2-3b-preview", verbose = True, streaming = True)

agent = Graph(model)

topic = "Perform an extensive research about the new budget of India for 2025 and give me a proper report on it"
output_format = "professional report"
result = agent.graph.invoke({"topic" : topic, "output_format" : output_format})
print(result)