from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from observation_portal.requestgroups.tasks import expire_requests
from observation_portal.accounts.tasks import expire_access_tokens

def run():
    scheduler = BlockingScheduler()
    scheduler.add_job(
        expire_requests.send,
        CronTrigger.from_crontab('*/5 * * * *')
    )
    scheduler.add_job(
        expire_access_tokens.send,
        CronTrigger.from_crontab('0 15 * * *')
    )
    scheduler.start()

