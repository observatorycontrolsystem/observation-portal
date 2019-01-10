from celery import shared_task
from django.utils import timezone
from oauth2_provider.models import AccessToken
import logging

logger = logging.getLogger(__name__)


@shared_task
def expire_access_tokens():
    logger.info('Expiring AccessTokens')
    AccessToken.objects.filter(expires__lt=timezone.now()).delete()
