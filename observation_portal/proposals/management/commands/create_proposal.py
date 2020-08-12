from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

import logging
import sys

from observation_portal.proposals.models import (Proposal, Membership, TimeAllocation,
                                                 Semester, ScienceCollaborationAllocation)
from observation_portal.common.configdb import configdb

logger = logging.getLogger()


class Command(BaseCommand):
    help = 'Creates a proposal using the given parameters, optionally creating time allocations and associating a PI.'

    def add_arguments(self, parser):
        parser.add_argument('--id', default='TestProposal', type=str,
                            help='Proposal Id')
        parser.add_argument('--active', dest='active', action='store_true',
                            help='The proposal should be considered active (available for submission)')
        parser.add_argument('--public', dest='public', action='store_true',
                            help='The proposal should be considered public (visible to anyone)')
        parser.add_argument('--non-science', dest='non_science', action='store_true',
                            help='The proposal is a non-science proposal (Education or Engineering)')
        parser.add_argument('--direct', dest='direct', action='store_true',
                            help='The proposal should allow direct submission observations')
        parser.add_argument('--title', default='A Simple Test Proposal', type=str,
                            help='Title of the proposal')
        parser.add_argument('--priority', default=10, type=int,
                            help='Scheduling priority for requests from this proposal')
        parser.add_argument('--pi', required=False, type=str,
                            help='User account id to make pi of this proposal (must exist already)')
        parser.add_argument('--time-allocation', dest='time_allocation', action='store_true',
                            help='Should fill in time allocation for this proposal with all instruments. Current semester must exist.')

    def handle(self, *args, **options):
        current_semester = None
        if options['time_allocation']:
            try:
                current_semester = Semester.current_semesters().first()
            except Exception:
                logger.error("You must have a current semester defined in the db to allocate time on a proposal.")
                sys.exit(1)

        user = None
        if options['pi']:
            try:
                user = User.objects.get(username=options['pi'])
            except Exception:
                logger.error(f"Failed to get user with name {options['pi']}. Make sure the user account is created.")
                sys.exit(1)
        # Proposal requires an SCA to be assigned
        sca, _ = ScienceCollaborationAllocation.objects.get_or_create(id='tst', name="Test SCA", admin=user)

        proposal, created = Proposal.objects.get_or_create(
            id=options['id'],
            title=options['title'],
            active=options['active'],
            public=options['public'],
            non_science=options['non_science'],
            direct_submission=options['direct'],
            tac_priority=options['priority'],
            sca=sca
        )
        if user:
            Membership.objects.get_or_create(proposal=proposal, user=user, role=Membership.PI)

        if current_semester:
            instrument_types = configdb.get_instrument_types(location={}, only_schedulable=True)
            for instrument in instrument_types:
                TimeAllocation.objects.get_or_create(
                    semester=current_semester,
                    proposal=proposal,
                    instrument_type=instrument,
                    defaults={
                        'std_allocation': 100,
                        'rr_allocation': 100,
                        'tc_allocation': 100,
                        'ipp_limit': 10,
                        'ipp_time_available': 5
                    }
                )

        if created:
            logger.info(f"Created proposal with id {options['id']}.")
        else:
            logger.info(f"Proposal with id {options['id']} already exists.")
        sys.exit(0)
