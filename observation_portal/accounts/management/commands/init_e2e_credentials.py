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
        parser.add_argument('-p', '--proposal', type=str, default='TestProposal',
                            help='Proposal id to create')
        parser.add_argument('-u', '--user', type=str, default='test_user',
                            help='User id to create')
        parser.add_argument('-t', '--token', type=str, default='123456789abcdefg',
                            help='API Token for the user')

    def handle(self, *args, **options):
        proposal_str = options['proposal']
        user_str = options['user']

        Semester.objects.get_or_create(id="Semester1", start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                                       end=datetime(2100, 1, 1, tzinfo=timezone.utc))
        try:
            user = User.objects.create_superuser(user_str, 'fake_email@lco.global', 'password')
        except IntegrityError:
            user = User.objects.get(username=user_str)
            logging.warning(f"user {user_str} already exists")
        Profile.objects.get_or_create(user=user)
        sca, _ = ScienceCollaborationAllocation.objects.get_or_create(name="Test SCA")
        try:
            proposal = Proposal.objects.create(id=proposal_str, active=True, title="Test Proposal",
                                               public=False, non_science=True, direct_submission=True,
                                               sca=sca)
            Membership.objects.create(proposal=proposal, user=user, role=Membership.PI)
        except IntegrityError:
            logging.warning(f'proposal {proposal_str} already exists')

        # Need to set the api token to some expected value
        token, created = Token.objects.get_or_create(user=user)
        token.delete()
        Token.objects.create(user=user, key=options['token'])
