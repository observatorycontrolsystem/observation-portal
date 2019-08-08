from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from observation_portal.requestgroups.tasks import expire_requests
from observation_portal.observations.tasks import delete_old_observations
from observation_portal.accounts.tasks import expire_access_tokens
from observation_portal.proposals.tasks import time_allocation_reminder


def run():
    scheduler = BlockingScheduler()
    scheduler.add_job(
        expire_requests.send,
        CronTrigger.from_crontab('*/5 * * * *')
    )
    scheduler.add_job(
        delete_old_observations.send,
        CronTrigger.from_crontab('0 * * * *')
    )
    scheduler.add_job(
        expire_access_tokens.send,
        CronTrigger.from_crontab('0 15 * * *')
    )
    scheduler.add_job(
        time_allocation_reminder.send,
        CronTrigger.from_crontab('0 0 1 * *')  # monthly
    )
    scheduler.start()
