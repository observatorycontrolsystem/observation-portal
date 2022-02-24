import dramatiq
from django.utils import timezone
from django.core.mail import send_mail as django_send_mail
from django.core.mail import send_mass_mail as django_send_mass_mail
from django.contrib.auth.models import User
from django.conf import settings
from oauth2_provider.models import AccessToken
from urllib.parse import urljoin
import logging
import requests


logger = logging.getLogger(__name__)


@dramatiq.actor()
def update_or_create_client_applications_user(user_json):
    """
    This call creates or updates the user account and profile information for each of the Oauth
    Client applications specified in settings
    """
    for base_url in settings.OAUTH_CLIENT_APPS_BASE_URLS:
        url = urljoin(base_url, '/authprofile/addupdateuser/')
        logger.info(f"Updating user details at {url}")
        header = {'Authorization': f"Server {settings.OAUTH_SERVER_KEY}"}
        response = requests.post(url, data=user_json, headers=header)
        response.raise_for_status()


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
