FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir build && python -m build --wheel

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CAPEXGRAPH_RUNS_DIR=/workspace/runs

WORKDIR /workspace
COPY --from=builder /build/dist/*.whl /tmp/
RUN WHEEL="$(find /tmp -name '*.whl' -print -quit)" \
    && python -m pip install --no-cache-dir "${WHEEL}[openai]" \
    && rm -f /tmp/*.whl
RUN useradd --create-home --uid 10001 capexgraph && mkdir -p /workspace/runs && chown -R capexgraph:capexgraph /workspace
USER capexgraph

EXPOSE 8000
CMD ["uvicorn", "capexgraph.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
