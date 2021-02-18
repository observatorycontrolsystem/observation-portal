FROM python:3.7-slim

EXPOSE 80
WORKDIR /observation-portal
CMD gunicorn observation_portal.wsgi --bind=0.0.0.0:8080 --worker-class=gevent --workers=4 --timeout=300

RUN apt-get update \
  && apt-get install -y gfortran \
  && pip install 'numpy>=1.16,<1.17'

COPY . .
RUN pip install -r requirements.txt

RUN mkdir static && python manage.py collectstatic --noinput
