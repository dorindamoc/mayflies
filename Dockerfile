FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MAYFLIES_HOME=/app
RUN pip install --no-cache-dir "httpx>=0.27,<1" "python-dotenv>=1.0,<2"
COPY *.py entrypoint.sh ./
COPY seed ./seed
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
