from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Serve static files from the "static" directory
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    # Optionally redirect to login page:
    with open("static/login.html", "r", encoding="utf-8") as f:
        return f.read()
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app)