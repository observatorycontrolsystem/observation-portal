import dramatiq
from django.utils import timezone
from django.core.mail import send_mail as django_send_mail
from django.core.mail import send_mass_mail as django_send_mass_mail
from oauth2_provider.models import AccessToken
import logging

logger = logging.getLogger(__name__)


@dramatiq.actor()
def expire_access_tokens():
    logger.info('Expiring AccessTokens')
    AccessToken.objects.filter(expires__lt=timezone.now()).delete()


@dramatiq.actor()
def send_mail(*args, **kwargs):
    django_send_mail(*args, **kwargs)


@dramatiq.actor()
def send_mass_mail(emails):
    django_send_mass_mail(emails)
