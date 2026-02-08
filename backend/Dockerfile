FROM python:3.13-slim-bookworm

# set workdir
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV PLAYWRIGHT_BROWSERS_PATH=./ms-playwright
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://playwright.azureedge.net

RUN python3 -m pip install --upgrade pip
RUN apt-get update && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir langchain-google-firestore
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --only-shell --with-deps

# copy source
COPY . .

# expose port and run
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0",  "--port", "8080"]