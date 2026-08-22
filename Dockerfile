FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/eduardbar/RAGfence" \
      org.opencontainers.image.title="RAGFence" \
      org.opencontainers.image.description="Security testing and authorization-aware retrieval for production RAG systems." \
      org.opencontainers.image.licenses="Apache-2.0"

RUN pip install --no-cache-dir "ragfence>=0.1,<2" \
    && adduser --disabled-password --gecos "" ragfence

USER ragfence

ENTRYPOINT ["ragfence"]
CMD ["--help"]
