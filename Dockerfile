FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get upgrade -y && apt-get clean
RUN pip install --no-cache-dir -r requirements.txt

COPY pyrestmutex.py .
COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "pyrestmutex:app", "--host", "0.0.0.0", "--port", "8000"]