FROM python:3.6-stretch
MAINTAINER Austin Riba <ariba@lco.global>

EXPOSE 80
ENV NODE_ENV production
WORKDIR /observation-portal
CMD gunicorn observation_portal.wsgi -w 4 -k gevent -b 0.0.0.0:80 --timeout=300

RUN curl -sL https://deb.nodesource.com/setup_10.x | bash -
RUN apt-get install -y gfortran nodejs

COPY requirements.txt .
RUN pip install 'numpy<1.16' && pip install -r requirements.txt

COPY package.json package-lock.json ./
RUN npm install && npm install --only=dev

COPY . /observation-portal
RUN npm run build

RUN python manage.py collectstatic --noinput
