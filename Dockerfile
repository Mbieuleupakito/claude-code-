# Assistant RE2020 — image pour un serveur interne DEEP-WATT (phase « entreprise »).
# docker compose up -d   puis   http://<serveur>:8000  (mot de passe : variable RE2020_MOT_DE_PASSE)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY data/catalogues ./data/catalogues
COPY data/references/charleville_calage.json data/references/resultats_references.json ./data/references/
RUN pip install --no-cache-dir -e ".[api,rapport]"
ENV RE2020_DONNEES=/donnees
VOLUME /donnees
EXPOSE 8000
CMD ["python", "-m", "re2020.api", "--reseau", "--sans-navigateur"]
