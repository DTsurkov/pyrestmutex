# First time:
docker compose up --build

# Manual:
docker build -t pyrestmutex .
docker run -p 8000:8000 pyrestmutex