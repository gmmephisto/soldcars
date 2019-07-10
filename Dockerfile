FROM python:3.6-alpine as requirements

RUN pip install poetry \
    && poetry config settings.virtualenvs.create false

WORKDIR /code
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-dev --no-interaction --no-ansi

FROM requirements

COPY soldcars ./soldcars
RUN pip install . && rm -rf ./*

CMD ["python", "-m", "soldcars"]
