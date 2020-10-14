from django.core.management.base import BaseCommand
from django.db.utils import IntegrityError
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from observation_portal.accounts.models import Profile

import logging

logger = logging.getLogger()


class Command(BaseCommand):
    help = 'Creates user, profile, and auth token'

    def add_arguments(self, parser):
        parser.add_argument('-u', '--user', type=str, default='test_user',
                            help='Username of User account to create')
        parser.add_argument('-p', '--password', type=str, default='test_pass',
                            help='Password to use for web access on the user account')
        parser.add_argument('-e', '--email', type=str, default='test_email@fake.test',
                            help='Email to use for the user account')
        parser.add_argument('-t', '--token', type=str, default='123456789abcdefg',
                            help='API Token for the user. Defaults to `123456789abcdefg`. Use empty string to have a random token generated.')
        parser.add_argument('--superuser', action='store_true',
                            help='The user should be created as a super-user')

    def handle(self, *args, **options):
        try:
            if options['superuser']:
                user = User.objects.create_superuser(options['user'], options['email'], options['password'])
            else:
                user = User.objects.create_user(options['user'], options['email'], options['password'])
        except IntegrityError:
            user = User.objects.get(username=options['user'])
            logging.warning(f"user {options['user']} already exists")
        Profile.objects.get_or_create(user=user)

        token, _ = Token.objects.get_or_create(user=user)
        if options['token']:
            # Need to set the api token to some expected value
            token.delete()
            Token.objects.create(user=user, key=options['token'])
