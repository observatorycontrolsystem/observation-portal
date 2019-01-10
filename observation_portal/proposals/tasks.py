from __future__ import absolute_import, unicode_literals
from celery import shared_task
import logging

from observation_portal.proposals.models import Semester, TimeAllocation
from observation_portal.proposals.accounting import get_time_totals_from_pond

logger = logging.getLogger(__name__)

# TODO: update this when accounting is updated and switch celery out

@shared_task
def update_time_allocation(time_allocation_id):
    talloc = TimeAllocation.objects.get(pk=time_allocation_id)
    logger.info('Updating timeallocation for %s', talloc.proposal, extra={'tags': {'proposal': talloc.proposal.id}})
    std_total = get_time_totals_from_pond(talloc, talloc.semester.start, talloc.semester.end, too=False)
    rr_total = get_time_totals_from_pond(talloc, talloc.semester.start, talloc.semester.end, too=True)
    talloc.std_time_used = std_total
    talloc.rr_time_used = rr_total
    talloc.save()


@shared_task
def run_accounting(semesters=None):
    if not semesters:
        semesters = Semester.current_semesters()

    for semester in semesters:
        logger.info('Performing accounting for semester: %s', semester)
        for talloc in semester.timeallocation_set.all():
            update_time_allocation.delay(talloc.id)
