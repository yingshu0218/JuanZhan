FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock /app/requirements.lock
COPY wheelhouse /wheelhouse
RUN pip install --no-cache-dir --no-index --find-links=/wheelhouse --require-hashes -r requirements.lock && rm -rf /wheelhouse
COPY --chmod=755 licenses /app/licenses
COPY --chmod=644 ocr-models.lock.json /app/ocr-models.lock.json
COPY --chmod=755 ocr-models /app/ocr-models
COPY scripts/setup_ocr_models.py /app/scripts/setup_ocr_models.py
RUN python /app/scripts/setup_ocr_models.py --verify
COPY --chmod=755 services /app/services
COPY --chmod=755 web/dist /app/web/dist
ENV PYTHONPATH=/app/services PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1
RUN useradd --uid 10001 --create-home app && mkdir -p /data && chown app:app /data
USER app
CMD ["python", "-m", "uvicorn", "juanzhan.archive:app", "--host", "0.0.0.0", "--port", "8000"]
