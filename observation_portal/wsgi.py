"""
WSGI config for observation_portal project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/howto/deployment/wsgi/
"""

import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from observation_portal.requestgroups.tasks import expire_requests
from observation_portal.accounts.tasks import expire_access_tokens
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'observation_portal.settings')

application = get_wsgi_application()


def on_starting(server):
    scheduler = BlockingScheduler()
    scheduler.add_job(
        expire_requests.send,
        CronTrigger.from_crontab('*/5 * * * *')
    )
    scheduler.add_job(
        expire_access_tokens.send,
        CronTrigger.from_crontab('0 15 * * *')
    )
    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()