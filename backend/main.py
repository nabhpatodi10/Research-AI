from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from graph import ResearchGraph
from chatagent import ChatAgent
from nodes import Nodes

app = FastAPI()

# Serve static files from the "static" directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index():
    return {"message": "Hello World"}

@app.get("/signup", response_class=HTMLResponse)
async def signup():
    # Optionally redirect to signup page:
    with open("static/signup.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
async def login():
    # Optionally redirect to login page:
    with open("static/login.html", "r", encoding="utf-8") as f:
        return f.read()
    
@app.get("/feedback", response_class=HTMLResponse)
async def feedback():
    # Optionally redirect to feedback page:
    with open("static/feedback.html", "r", encoding="utf-8") as f:
        return f.read()
    
@app.post("/research")
async def research(
    email: str,
    session_id: str,
    topic: str,
    output_format: str
):
    __research_graph = ResearchGraph(session_id)
    __response = __research_graph.graph.invoke({"topic": topic, "output_format": output_format})
    return __response["final_content"].as_str

@app.post("/chat")
async def chat(
    email: str,
    session_id: str,
    message: str
):
    __chat_agent = ChatAgent(session_id)
    __messages = Nodes().chat_agent(message)
    __response = __chat_agent.graph.invoke({"messages": __messages})
    return __response["messages"][-1].content
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=True)