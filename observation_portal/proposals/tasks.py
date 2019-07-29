import dramatiq
import logging

from observation_portal.proposals.models import Proposal

logger = logging.getLogger(__name__)


@dramatiq.actor()
def time_allocation_reminder():
    for proposal in Proposal.current_proposals().filter(active=True):
        if proposal.pi:
            logger.info('Sending time allocation reminder for {}'.format(proposal))
            proposal.send_time_allocation_reminder()
        else:
            logger.warn('Proposal {} does not have a PI!'.format(proposal))
