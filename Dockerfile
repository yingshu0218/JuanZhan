FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock /app/requirements.lock
COPY wheelhouse /wheelhouse
RUN pip install --no-cache-dir --no-index --find-links=/wheelhouse --require-hashes -r requirements.lock && rm -rf /wheelhouse
COPY --chmod=755 services /app/services
ENV PYTHONPATH=/app/services PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home app && mkdir -p /data && chown app:app /data
USER app
CMD ["python", "-m", "uvicorn", "juanzhan.archive:app", "--host", "0.0.0.0", "--port", "8000"]
