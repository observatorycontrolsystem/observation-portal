from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from observation_portal.common.configdb import configdb
from observation_portal.observations.models import Observation, Summary
from observation_portal.proposals.models import Proposal, Semester, TimeAllocation
from observation_portal.requestgroups.models import RequestGroup

import math


class Command(BaseCommand):
    help = 'Performs time accounting on a specific proposal and instrument type and semester'

    def add_arguments(self, parser):
        proposals = [p['id'] for p in Proposal.objects.all().values('id')]
        parser.add_argument('-p', '--proposal', type=str, choices=proposals, default='',
                            help='Proposal id to perform time accounting on. Default empty string for all proposals.')
        instrument_types = [it[0] for it in configdb.get_instrument_type_tuples()]
        parser.add_argument('-i', '--instrument_type', type=str, choices=instrument_types, default='',
                            help='Instrument type to perform time accounting on. Default empty string for all types.')
        semesters = [s['id'] for s in Semester.objects.all().values('id')]
        current_semester = Semester.current_semesters().first()
        parser.add_argument('-s', '--semester', type=str, choices=semesters, default=current_semester.id,
                            help='Semester to perform time accounting on. Defaults to current semester.')
        parser.add_argument('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                            help='Dry-run mode will print the time totals but not change anything in the db.')

    def handle(self, *args, **options):
        proposal_str = options['proposal'] or 'All'
        instrument_type_str = options['instrument_type'] or 'All'
        semester_str = options['semester']
        dry_run_str = 'Dry Run Mode: ' if options['dry_run'] else ''
        print(
            f"{dry_run_str}Running time accounting for Proposal(s): {proposal_str} and Instrument Type(s): {instrument_type_str} in Semester: {semester_str}",
            file=self.stdout
        )

        if options['proposal']:
            proposals = [Proposal.objects.get(id=options['proposal'])]
        else:
            proposals = Proposal.objects.filter(active=True)

        if options['instrument_type']:
            instrument_types = [options['instrument_type'].upper()]
        else:
            instrument_types = [it[0].upper() for it in configdb.get_instrument_type_tuples()]

        semester = Semester.objects.get(id=options['semester'])
        for proposal in proposals:
            for instrument_type in instrument_types:
                attempted_time = {
                    RequestGroup.NORMAL: 0,
                    RequestGroup.RAPID_RESPONSE: 0,
                    RequestGroup.TIME_CRITICAL: 0
                }
                observations = Observation.objects.filter(end__gt=semester.start, start__lt=semester.end,
                                                          request__request_group__proposal=proposal.id,
                                                          request__configurations__instrument_type=instrument_type,
                                                          ).exclude(state='PENDING'
                                                          ).exclude(request__request_group__observation_type=RequestGroup.DIRECT
                                                          ).prefetch_related(
                    'request',
                    'request__request_group',
                    'configuration_statuses',
                    'configuration_statuses__summary'
                ).order_by('start').distinct()

                for observation in observations:
                    observation_type = observation.request.request_group.observation_type
                    configuration_time = timedelta(seconds=0)
                    for configuration_status in observation.configuration_statuses.all():
                        try:
                            if configuration_status.summary.end > observation.end and observation_type == RequestGroup.RAPID_RESPONSE:
                                configuration_time += observation.end - configuration_status.summary.start
                            else:
                                configuration_time += configuration_status.summary.end - configuration_status.summary.start
                        except Summary.DoesNotExist:
                            pass

                    attempted_time[observation_type] += (configuration_time.total_seconds() / 3600.0)
                print(
                    "Proposal: {}, Instrument Type: {}, Used {} NORMAL hours, {} RAPID_RESPONSE hours, and {} TIME_CRITICAL hours".format(
                        proposal.id, instrument_type, attempted_time[RequestGroup.NORMAL], 
                        attempted_time[RequestGroup.RAPID_RESPONSE],
                        attempted_time[RequestGroup.TIME_CRITICAL]), file=self.stdout
                )

                time_allocation = TimeAllocation.objects.get(proposal=proposal, instrument_type=instrument_type,
                                                             semester=semester)
                if not math.isclose(time_allocation.std_time_used, attempted_time[RequestGroup.NORMAL], abs_tol=0.0001):
                    print("{} is different from existing NORMAL time {}".format(attempted_time[RequestGroup.NORMAL], time_allocation.std_time_used), file=self.stderr)
                if not math.isclose(time_allocation.rr_time_used, attempted_time[RequestGroup.RAPID_RESPONSE], abs_tol=0.0001):
                    print("{} is different from existing RAPID_RESPONSE time {}".format(attempted_time[RequestGroup.RAPID_RESPONSE], time_allocation.rr_time_used), file=self.stderr)
                if not math.isclose(time_allocation.tc_time_used, attempted_time[RequestGroup.TIME_CRITICAL], abs_tol=0.0001):
                    print("{} is different from existing TIME_CRITICAL time {}".format(attempted_time[RequestGroup.TIME_CRITICAL], time_allocation.tc_time_used), file=self.stderr)

                if not options['dry_run']:
                    # Update the time allocation for this proposal accordingly
                    time_allocation.std_time_used = attempted_time[RequestGroup.NORMAL]
                    time_allocation.rr_time_used = attempted_time[RequestGroup.RAPID_RESPONSE]
                    time_allocation.tc_time_used = attempted_time[RequestGroup.TIME_CRITICAL]
                    time_allocation.save()
