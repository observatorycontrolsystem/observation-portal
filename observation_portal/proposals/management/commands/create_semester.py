from django.core.management.base import BaseCommand

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
        parser.add_argument('--start', default=datetime.now() - timedelta(days=180), type=datetime.fromisoformat,
                            help='Semester start date (datetime in isoformat)')
        parser.add_argument('--end', default=datetime.now() + timedelta(days=180), type=datetime.fromisoformat,
                            help='Semester end date (datetime in isoformat)')

    def handle(self, *args, **options):
        Semester.objects.create(
            id=options['id'],
            start=options['start'],
            end=options['end']
        )

        logger.info(f"Created semester with id {options['id']} from {options['start']} to {options['end']}.")
        sys.exit(0)
