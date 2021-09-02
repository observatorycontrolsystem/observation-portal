import dramatiq
import logging
from datetime import datetime, timedelta
from django.utils.timezone import make_aware

from observation_portal.observations.models import Observation

logger = logging.getLogger(__name__)


@dramatiq.actor()
def delete_old_observations():
    cutoff = make_aware(datetime.utcnow() - timedelta(days=14))
    logger.info(f'Deleting CANCELED observations before cutoff date {cutoff}')
    Observation.delete_old_observations(cutoff)
