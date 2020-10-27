from django.core.management.base import BaseCommand
from oauth2_provider.models import Application
from django.contrib.auth.models import User

import sys
import logging

logger = logging.getLogger()


class Command(BaseCommand):
    help = 'Creates an oauth2 application with id and secret key'

    def add_arguments(self, parser):
        parser.add_argument('-u', '--user', type=str, default='test_user',
                            help='Username of User to associate with the Application')
        parser.add_argument('-n', '--name', type=str,
                            help='Name of the Application')
        parser.add_argument('--client-id', dest='client_id', type=str,
                            help='Client_id to use with the Application')
        parser.add_argument('--client-secret', dest='client_secret', type=str,
                            help='Client_secret to use with the Application')
        parser.add_argument('--redirect-uris', dest='redirect_uris', type=str,
                            help='Comma separated list of Redirect URIs for the Application')

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options['user'])
        except Exception:
            logging.warning(f"user {options['user']} does not exist")
            sys.exit(1)

        _, created = Application.objects.get_or_create(
            name=options['name'],
            defaults={
                'user': user,
                'client_type': Application.CLIENT_PUBLIC,
                'redirect_uris': options['redirect_uris'],
                'authorization_grant_type': Application.GRANT_PASSWORD,
                'client_id': options['client_id'],
                'client_secret': options['client_secret']
            }
        )
        if created:
            logging.info(f"Created Application for {options['name']}")
        else:
            logging.info(f"Application for {options['name']} already exists")
