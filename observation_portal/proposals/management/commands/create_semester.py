from django.core.management.base import BaseCommand
from django.utils import timezone

from datetime import datetime, timedelta
import logging
import sys

from observation_portal.proposals.models import Semester

logger = logging.getLogger()


class Command(BaseCommand):
    help = 'Creates a semester using the given parameters'

    def add_arguments(self, parser):
        parser.add_argument('--id', default='Semester01', type=str,
                            help='Semester Id (limited to 20 character code)')
        parser.add_argument('--start', default=timezone.now() - timedelta(days=180), type=datetime.fromisoformat,
                            help='Semester start date (datetime in isoformat)')
        parser.add_argument('--end', default=timezone.now() + timedelta(days=180), type=datetime.fromisoformat,
                            help='Semester end date (datetime in isoformat)')

    def handle(self, *args, **options):
        semester, created = Semester.objects.get_or_create(
            id=options['id'],
            defaults={
                'start': options['start'],
                'end': options['end']
            }
        )
        if created:
            logger.info(f"Created semester with id {options['id']} from {options['start']} to {options['end']}.")
        else:
            logger.info(f"Semester with id {options['id']} already exists from {semester.start} to {semester.end}.")

        sys.exit(0)
