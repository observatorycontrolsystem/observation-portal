FROM debian:9.8 as builder

ENV NODE_ENV production

RUN apt-get update \
  && apt-get install -y curl \
  && curl -sL https://deb.nodesource.com/setup_10.x | bash - \
  && apt-get update \
  && apt-get install -y nodejs \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json vue.config.js /
COPY static /static
RUN npm install \
  && npm install --only=dev \
  && npm run build


FROM python:3.7-slim

EXPOSE 80
WORKDIR /observation-portal
CMD gunicorn observation_portal.wsgi -c observation_portal/config.py

COPY requirements.txt .
RUN apt-get update \
  && apt-get install -y gfortran libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
  && pip install 'numpy>=1.16,<1.17' \
  && pip install -r requirements.txt

COPY observation_portal observation_portal/
COPY templates templates/
COPY manage.py test_settings.py ./
COPY --from=builder /static static
RUN python manage.py collectstatic --noinput
