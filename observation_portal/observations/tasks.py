import dramatiq
import logging
from datetime import timedelta
from django.utils import timezone

from observation_portal.observations.models import Observation

logger = logging.getLogger(__name__)


@dramatiq.actor()
def delete_old_observations():
    cutoff = timezone.now() - timedelta(days=14)
    logger.info(f'Deleting CANCELED observations before cutoff date {cutoff}')
    Observation.delete_old_observations(cutoff)
