FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir .

ENTRYPOINT ["repo-downloader"]
CMD ["--help"]
