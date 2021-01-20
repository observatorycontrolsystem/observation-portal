import requests
from django.core.cache import caches
from django.utils.translation import ugettext as _
from django.conf import settings
from django.utils import timezone
import logging
from time_intervals.intervals import Intervals
from datetime import datetime

logger = logging.getLogger(__name__)

DOWNTIMEDB_ERROR_MSG = _(("DowntimeDB connection is currently down, cannot update downtime information. "
                          "Using the last known value."))
DOWNTIME_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


class DowntimeDBException(Exception):
    pass


class DowntimeDB(object):
    @staticmethod
    def _get_downtime_data():
        ''' Gets all the data from downtimedb
        :return: list of dictionaries of downtime periods in time order (default)
        '''
        try:
            r = requests.get(settings.DOWNTIMEDB_URL + 'api/?limit=10000')
            r.raise_for_status()
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
            msg = "{}: {}".format(e.__class__.__name__, DOWNTIMEDB_ERROR_MSG)
            raise DowntimeDBException(msg)

        return r.json()['results']

    @staticmethod
    def _order_downtime_by_resource(raw_downtime_intervals):
        ''' Puts the raw downtime interval sets into a dictionary by resource
        '''
        downtime_intervals = {}
        for interval in raw_downtime_intervals:
            resource = '.'.join([interval['telescope'], interval['enclosure'], interval['site']])
            if resource not in downtime_intervals:
                downtime_intervals[resource] = []
            start = datetime.strptime(interval['start'], DOWNTIME_DATE_FORMAT).replace(tzinfo=timezone.utc)
            end = datetime.strptime(interval['end'], DOWNTIME_DATE_FORMAT).replace(tzinfo=timezone.utc)
            downtime_intervals[resource].append({'type': 'start', 'time': start})
            downtime_intervals[resource].append({'type': 'end', 'time': end})

        for resource in downtime_intervals:
            downtime_intervals[resource] = Intervals(downtime_intervals[resource])

        return downtime_intervals

    @staticmethod
    def get_downtime_intervals():
        ''' Returns dictionary of IntervalSets of downtime intervals per telescope resource. Caches the data and will
            attempt to update the cache every 15 minutes, but fallback on using previous downtime list otherwise.
        '''
        downtime_intervals = caches['locmem'].get('downtime_intervals', [])
        if not downtime_intervals:
            # If the cache has expired, attempt to update the downtime intervals
            try:
                data = DowntimeDB._get_downtime_data()
                downtime_intervals = DowntimeDB._order_downtime_by_resource(data)
                caches['locmem'].set('downtime_intervals', downtime_intervals, 900)
                caches['locmem'].set('downtime_intervals.no_expire', downtime_intervals)
            except DowntimeDBException as e:
                downtime_intervals = caches['locmem'].get('downtime_intervals.no_expire', [])
                logger.warning(repr(e))

        return downtime_intervals
