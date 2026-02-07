from dotenv import load_dotenv
load_dotenv()

import uuid_utils, asyncio, sys, uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from nodes import Nodes
from agent import Agent
from database import Database
from custom_search import CustomSearch

# Adjust event loop policy for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Playwright and launch browser
    app.state.playwright = await async_playwright().start()
    app.state.browser = await app.state.playwright.chromium.launch(headless=True)
    # Startup: initialize shared Custom Search HTTP client
    app.state.custom_search = CustomSearch()
    app.state.database = Database()
    app.state.chat_model = ChatGoogleGenerativeAI(
        model = "gemini-3-flash-preview",
        thinking_level="minimal"
    )
    yield
    # Shutdown: Close browser and stop Playwright
    await app.state.browser.close()
    await app.state.playwright.stop()
    await CustomSearch.aclose()
    app.state.database.close_connection()

app = FastAPI(title="Research-AI Backend", lifespan=lifespan)

origins = [
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost:3001",
    "https://research-ai-three.vercel.app"
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
    return {"message": "Welcome to the Research-AI FastAPI backend. Use the /chat endpoint."}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    session_id = request.session_id or str(uuid_utils.uuid7())
    try:
        # Get system messages using updated nodes (returns a list of SystemMessage)
        system_prompt = Nodes().chat_agent()
        # Create a HumanMessage for the user's input
        user_message = HumanMessage(content=request.user_input)
        # Build initial state with the user message
        state = {"messages": [user_message]}
        # Instantiate a new Agent per request using the provided system prompt
        chat_agent = Agent(
            session_id=session_id,
            database=app.state.database,
            model=app.state.chat_model,
            system_prompt=system_prompt,
            browser=app.state.browser,
        )
        # Invoke the agent's state graph asynchronously
        result = await chat_agent.graph.ainvoke(state)
        final_document = result.get("final_document")
        if final_document:
            return ChatResponse(response=str(final_document))
        final_messages = result.get("messages", [])
        if not final_messages:
            raise Exception("No response from chat agent")
        response_text = final_messages[-1].text
        return ChatResponse(response=response_text)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
