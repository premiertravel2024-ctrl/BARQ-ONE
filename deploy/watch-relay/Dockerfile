FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1' 'websockets>=15,<18'
COPY services/watch_relay.py services/watch_together.py services/watch_web.py ./services/
USER 65534
EXPOSE 8092
CMD ["python", "-m", "uvicorn", "services.watch_relay:app", "--host", "0.0.0.0", "--port", "8092", "--workers", "1", "--no-access-log", "--ws-max-size", "65536"]
