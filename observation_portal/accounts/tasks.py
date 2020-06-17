import dramatiq
from django.utils import timezone
from django.core.mail import send_mail as django_send_mail
from django.core.mail import send_mass_mail as django_send_mass_mail
from django.contrib.auth.models import User
from oauth2_provider.models import AccessToken
import logging

logger = logging.getLogger(__name__)


@dramatiq.actor()
def expire_access_tokens():
    logger.info('Expiring AccessTokens')
    AccessToken.objects.filter(expires__lt=timezone.now()).delete()


@dramatiq.actor()
def send_mail(*args, **kwargs):
    # Add logging for emails - args[0] is subject and args[3] is recipients
    usernames = set()
    for email_address in args[3]:
        usernames = usernames.union(
            set(User.objects.filter(email=email_address).values_list('username', flat=True))
        )
    logger.info(f"Sending email to {','.join(usernames)} with subject {args[0]}")
    django_send_mail(*args, **kwargs)


@dramatiq.actor()
def send_mass_mail(emails):
    # Add logging for emails sent out
    for email_tuple in emails:
        usernames = set()
        for email_address in email_tuple[3]:
            usernames = usernames.union(
                set(User.objects.filter(email=email_address).values_list('username', flat=True))
            )
        logger.info(f"Sending email to {','.join(usernames)} with subject {email_tuple[0]}")
    django_send_mass_mail(emails)
