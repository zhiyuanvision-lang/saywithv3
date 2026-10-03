FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY backend ./backend
COPY modules ./modules
COPY research/long-term-map-model-review-2026-10-02 ./research/long-term-map-model-review-2026-10-02
COPY research/long-term-map-release-2026-10-02 ./research/long-term-map-release-2026-10-02
COPY research/long-term-map-gse-clb-2026-10-02 ./research/long-term-map-gse-clb-2026-10-02
COPY research/system-dataflow-2026-10-02/contracts.examples.json ./research/system-dataflow-2026-10-02/contracts.examples.json
RUN useradd --create-home saywith && mkdir -p /app/var/media && chown -R saywith:saywith /app/var
USER saywith
EXPOSE 8083
CMD ["python", "-m", "backend", "serve", "--host", "0.0.0.0", "--port", "8083"]
