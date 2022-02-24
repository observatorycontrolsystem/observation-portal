from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.module_loading import import_string
from urllib.parse import urljoin
import requests
import json

import sys
import logging

logger = logging.getLogger()


class Command(BaseCommand):
    help = 'Sync user accounts between client applications.'

    def add_arguments(self, parser):
        parser.add_argument('-u', '--client-url', dest='client_url', type=str,
                            help='client url to call the /addupdateuser on for each user')

    def handle(self, *args, **options):
        logger.info(f"Updating client user details for {options['client_url']}")
        url = urljoin(options['client_url'], '/authprofile/addupdateuser/')
        header = {'Authorization': f"Server {settings.OAUTH_SERVER_KEY}"}
        users = User.objects.all()
        for user in users:
            try:
                data = import_string(settings.SERIALIZERS['accounts']['User'])(user).data
                response = requests.post(url, data=json.dumps(data), headers=header)
                response.raise_for_status()
            except Exception:
                logger.error("Failed to update client user details, please run this command again", exc_info=1)
                sys.exit(1)

        logger.info("Finished updating client user details.")
