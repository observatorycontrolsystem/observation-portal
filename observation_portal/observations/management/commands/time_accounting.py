from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
from observation_portal.common.configdb import configdb
from observation_portal.observations.models import Observation, Summary
from observation_portal.observations.time_accounting import configuration_time_used
from observation_portal.proposals.models import Proposal, Semester
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

        semester = Semester.objects.get(id=options['semester'])
        for proposal in proposals:
            time_allocations = proposal.timeallocation_set.filter(semester=semester)
            if options['instrument_type']:
                time_allocations = time_allocations.filter(instrument_types__contains=[options['instrument_type'].upper()])
            for time_allocation in time_allocations:
                attempted_time = {
                    RequestGroup.NORMAL: 0,
                    RequestGroup.RAPID_RESPONSE: 0,
                    RequestGroup.TIME_CRITICAL: 0
                }
                observations = Observation.objects.filter(end__gt=semester.start, start__lt=semester.end,
                                                          request__request_group__proposal=proposal.id,
                                                          request__configurations__instrument_type__in=time_allocation.instrument_types,
                                                          ).exclude(state='PENDING'
                                                          ).exclude(request__request_group__observation_type__in=RequestGroup.NON_SCHEDULED_TYPES
                                                          ).prefetch_related(
                    'request',
                    'request__request_group',
                    'request__configurations',
                    'configuration_statuses',
                    'configuration_statuses__configuration',
                    'configuration_statuses__summary'
                ).order_by('start').distinct()

                for observation in observations:
                    observation_type = observation.request.request_group.observation_type
                    configuration_time = timedelta(seconds=0)
                    for configuration_status in observation.configuration_statuses.all():
                        # Configurations of other instrument_types are charged to their own TimeAllocation
                        if configuration_status.configuration.instrument_type not in time_allocation.instrument_types:
                            continue
                        try:
                            configuration_time += configuration_time_used(configuration_status.summary, observation_type)
                        except Summary.DoesNotExist:
                            pass

                    attempted_time[observation_type] += (configuration_time.total_seconds() / 3600.0)
                print(
                    "Proposal: {}, Instrument Types: {}, Used {} NORMAL hours, {} RAPID_RESPONSE hours, and {} TIME_CRITICAL hours".format(
                        proposal.id, ','.join(time_allocation.instrument_types), attempted_time[RequestGroup.NORMAL],
                        attempted_time[RequestGroup.RAPID_RESPONSE],
                        attempted_time[RequestGroup.TIME_CRITICAL]), file=self.stdout
                )

                time_used_changed = False
                if not math.isclose(time_allocation.std_time_used, attempted_time[RequestGroup.NORMAL], abs_tol=0.0001):
                    print("{} is different from existing NORMAL time {}".format(attempted_time[RequestGroup.NORMAL], time_allocation.std_time_used), file=self.stderr)
                    time_used_changed = True
                if not math.isclose(time_allocation.rr_time_used, attempted_time[RequestGroup.RAPID_RESPONSE], abs_tol=0.0001):
                    print("{} is different from existing RAPID_RESPONSE time {}".format(attempted_time[RequestGroup.RAPID_RESPONSE], time_allocation.rr_time_used), file=self.stderr)
                    time_used_changed = True
                if not math.isclose(time_allocation.tc_time_used, attempted_time[RequestGroup.TIME_CRITICAL], abs_tol=0.0001):
                    print("{} is different from existing TIME_CRITICAL time {}".format(attempted_time[RequestGroup.TIME_CRITICAL], time_allocation.tc_time_used), file=self.stderr)
                    time_used_changed = True

                if time_used_changed and not options['dry_run']:
                    # Update the time allocation for this proposal accordingly
                    time_allocation.std_time_used = attempted_time[RequestGroup.NORMAL]
                    time_allocation.rr_time_used = attempted_time[RequestGroup.RAPID_RESPONSE]
                    time_allocation.tc_time_used = attempted_time[RequestGroup.TIME_CRITICAL]
                    time_allocation._change_reason = 'Recalculated by time_accounting management command'
                    time_allocation.save()
