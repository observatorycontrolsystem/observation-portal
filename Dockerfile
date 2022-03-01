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
RUN pip install --upgrade pip && pip install poetry

WORKDIR /src

# copy bare minimum needed to install python dependecies with poetry
COPY ./README.md ./pyproject.toml ./poetry.lock ./

# install locked python dependecies using poetry to generate a requirements.txt

# NOTE: pySLALIB's setup.py is messed up as it requires numpy to already be
# installed to install it. https://github.com/scottransom/pyslalib/blob/fcb0650a140a8002cc6c0e8918c3e4c6fe3f8e01/setup.py#L3
# So please excuse the ugly hack.

RUN pip install -r <(poetry export | grep "numpy") && \
  pip install -r <(poetry export)

# copy everything else
COPY ./ ./

# install our app
RUN pip install .

# collect all static assets into one place: /static
RUN mkdir -p static && python manage.py collectstatic --noinput

ENV PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1


# add a multi-stage build target which also has dev (test) dependencies
# usefull for running tests in docker container
# this won't be included in the final image
# e.g. docker build --target dev .
FROM base as dev

RUN pip install -r <(poetry export --dev)

ENTRYPOINT ["bash"]


# final image
FROM base as prod

# add a non-root user to run the app
RUN useradd appuser

# switch to non-root user
USER appuser

CMD ["gunicorn", "observation_portal.wsgi", "--bind=0.0.0.0:8080", "--worker-class=gevent", "--workers=4", "--timeout=300"]

EXPOSE 8080/tcp
