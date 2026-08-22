FROM python:3.12-slim

# Pin the exact release at build time; the publish workflow passes
# ragfence==<release tag> so the image can never resolve a stale PyPI version.
ARG RAGFENCE_SPEC="ragfence>=0.1,<3"

LABEL org.opencontainers.image.source="https://github.com/eduardbar/RAGfence" \
      org.opencontainers.image.title="RAGFence" \
      org.opencontainers.image.description="Security testing and authorization-aware retrieval for production RAG systems." \
      org.opencontainers.image.licenses="Apache-2.0"

RUN pip install --no-cache-dir "${RAGFENCE_SPEC}" \
    && adduser --disabled-password --gecos "" ragfence

USER ragfence

ENTRYPOINT ["ragfence"]
CMD ["--help"]
