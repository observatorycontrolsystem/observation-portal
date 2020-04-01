from django.utils import timezone
import dramatiq
import logging

from observation_portal.proposals.models import Proposal

logger = logging.getLogger(__name__)


@dramatiq.actor()
def time_allocation_reminder():
    for proposal in Proposal.current_proposals().filter(active=True).distinct():
        # Only send an email if we are within 3 months of the end of the semester
        # and the proposal has at least one allocation.
        if (
                len(proposal.current_allocation) > 0
                and (proposal.current_semester.end - timezone.now()).days <= 93
        ):
            logger.info('Sending time allocation reminder for {}'.format(proposal))
            proposal.send_time_allocation_reminder()
