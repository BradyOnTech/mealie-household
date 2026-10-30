###############################################
# Frontend Build
###############################################
FROM node:24@sha256:64af3819f9275802414d7cdc38c27e9d82bd564dec4d4da87d008255d36c63b4 \
    AS frontend-builder

RUN npm install --global pnpm@11

WORKDIR /frontend

COPY frontend .

RUN pnpm install --frozen-lockfile

RUN pnpm generate

###############################################
# Base Image - Python
###############################################
FROM python:3.14-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2 \
    AS python-base

ENV MEALIE_HOME="/app"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    VENV_PATH="/opt/mealie"

# prepend venv to path
ENV PATH="$VENV_PATH/bin:$PATH"

# create user account
RUN useradd -u 911 -U -d $MEALIE_HOME -s /bin/bash abc \
    && usermod -G users abc \
    && mkdir $MEALIE_HOME

###############################################
# Backend Package Build
###############################################
FROM python-base AS backend-builder
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Install from the committed lockfile; never re-resolve. The rolling
# `exclude-newer` cooling window (pyproject [tool.uv]) would otherwise make
# `uv export` below re-resolve and fail on in-window pins.
ENV UV_FROZEN=1

WORKDIR /mealie

# copy project files here to ensure they will be cached.
COPY uv.lock pyproject.toml ./
COPY mealie ./mealie
COPY . /source
RUN uv run --no-project python /source/dev/household/build_source_archive.py /source /mealie/mealie/household-source.zip

# Copy frontend to package it into the wheel
COPY --from=frontend-builder /frontend/.output/public ./mealie/frontend

# Build the source and binary package
RUN uv build --out-dir dist

# dependencies.txt changes only when uv.lock does, so the venv build can cache
# the install. requirements.txt adds the wheel that was just built, so an
# install from it gets that exact one.
RUN uv export --no-editable --no-emit-project --extra pgsql --format requirements-txt --output-file dist/dependencies.txt \
    && cp dist/dependencies.txt dist/requirements.txt \
    && MEALIE_VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])") \
    && echo "mealie[pgsql]==${MEALIE_VERSION} \\" >> dist/requirements.txt \
    && pip hash dist/mealie-${MEALIE_VERSION}-py3-none-any.whl | tail -n1 | tr -d '\n' >> dist/requirements.txt \
    && echo " \\" >> dist/requirements.txt \
    && pip hash dist/mealie-${MEALIE_VERSION}.tar.gz | tail -n1 >> dist/requirements.txt

###############################################
# Package Container
# Only role is to hold the packages, or be overriden by a --build-context flag.
###############################################
FROM scratch AS packages
COPY --from=backend-builder /mealie/dist /

###############################################
# Python Virtual Environment Build
###############################################
# Install packages required to build the venv, in parallel to building the wheel
FROM python-base AS venv-builder-base
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    libwebp-dev \
    ffmpeg \
    # LDAP Dependencies
    libsasl2-dev libldap2-dev libssl-dev \
    gnupg gnupg2 gnupg1 \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --upgrade-deps $VENV_PATH

# Install the wheel and all dependencies into the venv
FROM venv-builder-base AS venv-builder

# Cache key is dependencies.txt, so a mealie-only commit reuses this layer.
COPY --from=packages dependencies.txt /dist/dependencies.txt
RUN . $VENV_PATH/bin/activate \
    && pip install --require-hashes -r /dist/dependencies.txt

# Copy built package (wheel) and its dependency requirements
COPY --from=packages * /dist/

# The dependencies are already in place, so pip only installs mealie itself.
RUN . $VENV_PATH/bin/activate \
    && pip install --require-hashes -r /dist/requirements.txt --find-links /dist

###############################################
# Production Image
###############################################
FROM python-base AS production
ENV PRODUCTION=true
ENV TESTING=false

ARG COMMIT
ENV GIT_COMMIT_HASH=$COMMIT

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    curl \
    ffmpeg \
    gosu \
    iproute2 \
    libldap-common \
    libldap2 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Codex CLI, which ChatGPT subscription AI providers run their requests through. Its app-server
# protocol is still experimental, so it's pinned to the version Mealie was tested against.
# Build with --build-arg CODEX_VERSION= to leave it out.
ARG TARGETARCH
ARG CODEX_VERSION=0.166.0
ARG CODEX_SHA256_AMD64=a0bf572d2f93f056c6712a6da348e96078dc84f3885fd7be67807ef389cb3978
ARG CODEX_SHA256_ARM64=94eb707605ec2646b2e05b7edf7c4e7b3ccf02b16237c34ae9beb8cfb7f810a9
RUN if [ -n "$CODEX_VERSION" ]; then \
        case "$TARGETARCH" in \
            amd64) arch=x86_64; sha256=$CODEX_SHA256_AMD64 ;; \
            arm64) arch=aarch64; sha256=$CODEX_SHA256_ARM64 ;; \
            *) echo "No Codex build for $TARGETARCH" >&2; exit 1 ;; \
        esac \
        && curl -fsSL -o /tmp/codex.tar.gz \
            "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-${arch}-unknown-linux-musl.tar.gz" \
        && echo "$sha256  /tmp/codex.tar.gz" | sha256sum -c - \
        && tar -xzf /tmp/codex.tar.gz -C /tmp \
        && install -m 0755 "/tmp/codex-${arch}-unknown-linux-musl" /usr/local/bin/codex \
        && rm -f /tmp/codex.tar.gz "/tmp/codex-${arch}-unknown-linux-musl"; \
    fi

# Deno, which yt-dlp runs YouTube's player code in to read its videos. Without a JavaScript
# runtime, yt-dlp's YouTube support is deprecated and degrading.
# Build with --build-arg DENO_VERSION= to leave it out.
ARG DENO_VERSION=2.9.8
ARG DENO_SHA256_AMD64=e890975bc2549807bbcc0b584ffafda72cc7c93349dd99c80483dd784f6c4609
ARG DENO_SHA256_ARM64=d49596c20b9788cf8f5d8ddf644103d4bde56ed239753f0bdb92ba9361d51905
RUN if [ -n "$DENO_VERSION" ]; then \
        case "$TARGETARCH" in \
            amd64) arch=x86_64; sha256=$DENO_SHA256_AMD64 ;; \
            arm64) arch=aarch64; sha256=$DENO_SHA256_ARM64 ;; \
            *) echo "No Deno build for $TARGETARCH" >&2; exit 1 ;; \
        esac \
        && curl -fsSL -o /tmp/deno.zip \
            "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${arch}-unknown-linux-gnu.zip" \
        && echo "$sha256  /tmp/deno.zip" | sha256sum -c - \
        && unzip -q /tmp/deno.zip -d /tmp/deno \
        && install -m 0755 /tmp/deno/deno /usr/local/bin/deno \
        && rm -rf /tmp/deno.zip /tmp/deno; \
    fi

# create directory used for Docker Secrets
RUN mkdir -p /run/secrets

# Copy venv into image. It contains a fully-installed mealie backend and frontend.
COPY --from=venv-builder $VENV_PATH $VENV_PATH

# install nltk data for the ingredient parser
ENV NLTK_DATA="/nltk_data/"
COPY ./docker/setup_nltk_data.sh $MEALIE_HOME/setup_nltk_data.sh
RUN chmod +x $MEALIE_HOME/setup_nltk_data.sh && $MEALIE_HOME/setup_nltk_data.sh

VOLUME [ "$MEALIE_HOME/data/" ]
ENV APP_PORT=9000

EXPOSE ${APP_PORT}

COPY ./docker/healthcheck.sh $MEALIE_HOME/healthcheck.sh
RUN chmod +x $MEALIE_HOME/healthcheck.sh
HEALTHCHECK CMD $MEALIE_HOME/healthcheck.sh

ENV HOST=0.0.0.0

EXPOSE ${APP_PORT}
COPY ./docker/entry.sh $MEALIE_HOME/run.sh

RUN chmod +x $MEALIE_HOME/run.sh
ENTRYPOINT ["/app/run.sh"]
