from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.utils import IntegrityError
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from datetime import datetime
from observation_portal.accounts.models import Profile
from observation_portal.proposals.models import Proposal, Semester, Membership, ScienceCollaborationAllocation

import logging

logger = logging.getLogger()


class Command(BaseCommand):
    help = 'Creates user, proposal, and all structures needed for user to submit observations'

    def add_arguments(self, parser):
        parser.add_argument('-u', '--user', type=str, default='test_user',
                            help='Username of User account to create')
        parser.add_argument('-p', '--password', type=str, default='test_pass',
                            help='Password to use for web access on the user account')
        parser.add_argument('-t', '--token', type=str, default='123456789abcdefg',
                            help='API Token for the user')

    def handle(self, *args, **options):
        try:
            user = User.objects.create_superuser(options['user'], 'fake_email@fake.test', options['password'])
        except IntegrityError:
            user = User.objects.get(username=options['user'])
            logging.warning(f"user {options['user']} already exists")
        Profile.objects.get_or_create(user=user)

        # Need to set the api token to some expected value
        token, created = Token.objects.get_or_create(user=user)
        token.delete()
        Token.objects.create(user=user, key=options['token'])
