FROM python:3.12.7-slim

# set workdir
WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=./ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install

# copy source
COPY . .

# expose port and run
EXPOSE 8000
CMD ["uvicorn", "main:app", "--port", "8000"]