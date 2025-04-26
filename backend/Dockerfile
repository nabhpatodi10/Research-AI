FROM python:3.12.7-slim

# set workdir
WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=./ms-playwright
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://playwright.azureedge.net

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install

# copy source
COPY . .

# expose port and run
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0",  "--port", "8080"]