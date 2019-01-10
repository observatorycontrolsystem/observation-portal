from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from django.core.mail import send_mail as django_send_mail
from django.core.mail import send_mass_mail as django_send_mass_mail

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'valhalla.settings')

app = Celery('valhalla')

# Using a string here means the worker don't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task()
def send_mail(*args, **kwargs):
    django_send_mail(*args, **kwargs)


@app.task()
def send_mass_mail(emails):
    django_send_mass_mail(emails)
