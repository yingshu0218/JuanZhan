FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG VERSION=dev
ARG REVISION=unknown
ARG SOURCE_DIRTY=true
LABEL org.opencontainers.image.title="JuanZhan native reading renderer" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.revision=$REVISION \
      org.opencontainers.image.source="https://github.com/yingshu0218/JuanZhan" \
      io.juanzhan.source-dirty=$SOURCE_DIRTY
WORKDIR /app
COPY office-preview-tools.lock.json /app/office-preview-tools.lock.json
COPY scripts/setup_office_preview.py /app/scripts/setup_office_preview.py
RUN --mount=type=bind,source=office-packages,target=/app/office-packages,ro python /app/scripts/setup_office_preview.py && apt-get -y --no-install-recommends install /app/office-packages/*.deb && dpkg-query -W > /app/office-system-packages.tsv && rm -f /var/cache/apt/archives/*.deb
COPY requirements.lock /app/requirements.lock
COPY wheelhouse /wheelhouse
RUN pip install --no-cache-dir --no-index --find-links=/wheelhouse --require-hashes -r requirements.lock && rm -rf /wheelhouse
COPY --chmod=755 licenses /app/licenses
COPY --chmod=755 services /app/services
ENV PYTHONPATH=/app/services PYTHONUNBUFFERED=1 JUANZHAN_OFFICE_RENDERER_VERSION=libreoffice-25.2.3-2-deb13u8
RUN useradd --uid 10001 --create-home app
USER app
CMD ["python", "-m", "uvicorn", "juanzhan.office_preview:app", "--host", "0.0.0.0", "--port", "8000"]
