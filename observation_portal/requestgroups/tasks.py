import dramatiq
import logging

from observation_portal.common.state_changes import update_request_states_for_window_expiration

logger = logging.getLogger(__name__)


@dramatiq.actor()
def expire_requests():
    logger.info('Expiring requests')
    update_request_states_for_window_expiration()
