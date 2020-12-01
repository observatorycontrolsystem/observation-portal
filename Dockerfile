FROM python:3.7-slim

EXPOSE 80
WORKDIR /observation-portal
CMD gunicorn observation_portal.wsgi -c observation_portal/config.py

COPY requirements.txt .
RUN apt-get update \
  && apt-get install -y gfortran \
  && pip install 'numpy>=1.16,<1.17' \
  && pip install -r requirements.txt

COPY observation_portal observation_portal/
COPY templates templates/
COPY manage.py test_settings.py ./
RUN mkdir static && python manage.py collectstatic --noinput
