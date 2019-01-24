# Observation Portal

_An Astronomical Observation Web Portal and Backend_

The portal manages observation requests and observations in the context of a larger system. Other parts of this system include:
- an information store containing the configuration of resources in the system
- an information store containing resource availability information
- an information store containing periods of maintenance or other downtimes for resources in the system
- a scheduler responsible for scheduling observations on resources and a mechanism by which to report back observation states

## Prerequisites
The portal can be run as a standalone application with reduced functionality. The basic requirements are:

* Python >= 3.6
* PostgreSQL 11

## Set up a virtual environment
From the base of this project:

```
python -m venv ~/observation_portal_env
source ~/observation_portal_env/bin/activate
pip install numpy && pip install -r requirements.txt
```

## Set up the database
This example uses Docker to create a database with the default database settings in `observation_portal/settings.py`.

```
docker run --name observation-portal-postgres -e POSTGRES_PASSWORD=postgres -v/var/lib/postgresql/data -p5432:5432 -d postgres:11.1
docker exec -it observation-portal-postgres /bin/bash
createdb -U postgres -W observation_portal
exit
```

After creating the database, the migrations must be run to set up the tables.

```
python manage.py migrate
```

## Run the portal

```
python manage.py runserver
```

The observation portal is now accessible from [http://127.0.0.1:8000](http://127.0.0.1:8000)!
