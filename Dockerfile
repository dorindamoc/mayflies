FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MAYFLIES_HOME=/app
RUN apt-get update && apt-get install -y --no-install-recommends git fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "httpx>=0.27,<1" "python-dotenv>=1.0,<2" "resvg-py>=0.3,<1"
COPY *.py entrypoint.sh ./
COPY seed ./seed
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
