FROM python:3.10-slim as base

# these commands are organized to minimize docker build cache invalidation
# (barring any other logical constraints)

# use bash
SHELL ["/bin/bash", "-c"]

# install any security updates
RUN apt-get update && apt-get -y upgrade

# install system dependencies
RUN apt-get install -y gfortran

# upgrade pip and install poetry
RUN pip install --upgrade pip && pip install "poetry>=1.4.2"

WORKDIR /src

# copy bare minimum needed to install python dependecies with poetry
COPY ./README.md ./pyproject.toml ./poetry.lock ./

ENV POETRY_VIRTUALENVS_CREATE=true POETRY_VIRTUALENVS_IN_PROJECT=true

# install python dependencies
RUN poetry install --only main --no-root --no-cache

# copy everything else
COPY ./ ./

# install app
RUN poetry install --only-root

# activate venv
ENV PATH="/src/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1

# add a multi-stage build target which also has dev (test) dependencies
# usefull for running tests in docker container
# this won't be included in the final image
# e.g. docker build --target dev .
FROM base as dev

RUN poetry install --only dev

ENTRYPOINT ["bash"]


# final image
FROM base as prod

# add a non-root user to run the app
RUN useradd appuser

# switch to non-root user
USER appuser

CMD ["gunicorn", "observation_portal.wsgi", "--bind=0.0.0.0:8080", "--worker-class=gevent", "--workers=4", "--timeout=300"]

EXPOSE 8080/tcp
