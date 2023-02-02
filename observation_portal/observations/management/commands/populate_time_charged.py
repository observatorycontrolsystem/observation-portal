from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from observation_portal.observations.time_accounting import configuration_time_used
from observation_portal.observations.models import ConfigurationStatus

import logging
logger = logging.getLogger()


class Command(BaseCommand):
    help = 'Attempts to fill in the time_charged field for a set of configuration statuses.'

    def add_arguments(self, parser):
        parser.add_argument('--start', default=timezone.now() - timedelta(days=180), type=datetime.fromisoformat,
                            help='Semester start date (datetime in isoformat)')
        parser.add_argument('--end', default=timezone.now(), type=datetime.fromisoformat,
                            help='Semester end date (datetime in isoformat)')

    def handle(self, *args, **options):
        for configuration_status in ConfigurationStatus.objects.filter(created__gte=options['start'], created__lte=options['end']).exclude(state='PENDING', time_charged__gt=0).iterator():
            try:
                has_summary = hasattr(configuration_status, 'summary')
                if has_summary:
                    time_used = configuration_time_used(configuration_status.summary, configuration_status.observation.request.request_group.observation_type)
                    configuration_status.time_charged = time_used.total_seconds() / 3600.0
                    configuration_status.save()
            except Exception as ex:
                logger.warning(f"Failed to update time_charged for configuration status {configuration_status.id}: {repr(ex)}")
