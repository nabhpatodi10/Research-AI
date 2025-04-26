import uuid
import asyncio
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from nodes import Nodes
from graph import ResearchGraph
from chatagent import ChatAgent
import structures
from playwright.async_api import async_playwright

# Adjust event loop policy for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Playwright and launch browser
    app.state.playwright = await async_playwright().start()
    app.state.browser = await app.state.playwright.chromium.launch(headless=True)
    yield
    # Shutdown: Close browser and stop Playwright
    await app.state.browser.close()
    await app.state.playwright.stop()

app = FastAPI(title="Research-AI Backend", lifespan=lifespan)

origins = [
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost:3001",
    "https://research-ai-three.vercel.app",
    "https://research-ai-three.vercel.app/",
    "https://research-ai-three.vercel.app/chat"
    # Add other origins as needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows specified origins
    allow_credentials=True,
    allow_methods=["*"],    # Allows all methods
    allow_headers=["*"],    # Allows all headers
)

# Models for Research endpoint
class ResearchRequest(BaseModel):
    session_id: str = None
    topic: str
    output_format: str
    outline: str = None

class ResearchResponse(BaseModel):
    session_id: str
    final_content: str

# Models for Chat endpoint
class ChatRequest(BaseModel):
    session_id: str
    user_input: str

class ChatResponse(BaseModel):
    response: str

@app.get("/")
def read_root():
    return {"message": "Welcome to the Research-AI FastAPI backend. Use /research for research tasks and /chat for conversational queries."}

@app.post("/research", response_model=ResearchResponse)
async def research_endpoint(request: ResearchRequest):
    session_id = request.session_id or str(uuid.uuid4())
    try:
        # Create a new ResearchGraph instance per request
        research_graph = ResearchGraph(session_id, app.state.browser)
        # Prepare the input state; the graph expects at least "topic" and "output_format"
        if request.outline:
            input_state = {
                "topic": request.topic,
                "output_format": request.output_format,
                "user_outline": request.outline
            }
        else:
            input_state = {
                "topic": request.topic,
                "output_format": request.output_format
            }
        # Invoke the state graph asynchronously
        result = await research_graph.graph.ainvoke(input_state)
        final_content = result.get("final_content", [])
        final_document = structures.CompleteDocument(
            title=result["document_outline"].page_title,
            sections=final_content
        )
        return ResearchResponse(session_id=session_id, final_content=final_document.as_str)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    try:
        # Get system messages using updated nodes (returns a list of SystemMessage)
        system_messages = Nodes().chat_agent()
        # Create a HumanMessage for the user's input
        user_message = HumanMessage(content=request.user_input)
        # Build initial state with the user message
        state = {"messages": [user_message]}
        # Instantiate a new ChatAgent per request using the provided system messages
        chat_agent = ChatAgent(session_id, system_messages, app.state.browser)
        # Invoke the agent's state graph asynchronously
        result = await chat_agent.graph.ainvoke(state)
        final_messages = result.get("messages", [])
        if not final_messages:
            raise Exception("No response from chat agent")
        response_text = final_messages[-1].content
        return ChatResponse(response=response_text)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)