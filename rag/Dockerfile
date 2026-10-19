FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/chroma /app/documents && chown -R 10001:10001 /app
COPY --chown=10001:10001 assistant.py .
COPY --chown=10001:10001 procedure_crise.md /app/documents/procedure_crise.md
EXPOSE 8002
USER 10001:10001
CMD ["uvicorn", "assistant:app", "--host", "0.0.0.0", "--port", "8002"]
