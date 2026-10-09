# Matinee's server image. One uvicorn worker: the DoesTheDogDie pacing and the
# per-device lookup cap live in the process, so a second worker would double both.
# The state directory (the film table, the profile store and the TMDB cache) is
# mounted at /state; settings and keys arrive as environment.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/state

WORKDIR /app
# The published image redistributes Matinee and its MovieLens-derived files, so the
# licence and the README's credits travel with them.
COPY LICENSE README.md ./
COPY pyproject.toml ./
COPY src ./src
COPY data ./data
COPY tools ./tools
# Editable, so the package finds its data/ beside src/ as it does in a checkout.
RUN pip install --no-cache-dir -e . \
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin matinee

USER matinee
EXPOSE 8000
CMD ["uvicorn", "--factory", "matinee.web.main:build", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header", "--no-access-log"]
