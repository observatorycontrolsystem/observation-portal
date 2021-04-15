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
    def _order_downtime_by_resource_and_instrument_type(raw_downtime_intervals):
        ''' Puts the raw downtime interval sets into a dictionary by resource and then by instrument_type or "all"
        '''
        downtime_intervals = {}
        for interval in raw_downtime_intervals:
            resource = '.'.join([interval['telescope'], interval['enclosure'], interval['site']])
            if resource not in downtime_intervals:
                downtime_intervals[resource] = {}
            instrument_type = interval['instrument_type'] if interval['instrument_type'] else 'all'
            if instrument_type not in downtime_intervals[resource]:
                downtime_intervals[resource][instrument_type] = []
            start = datetime.strptime(interval['start'], DOWNTIME_DATE_FORMAT).replace(tzinfo=timezone.utc)
            end = datetime.strptime(interval['end'], DOWNTIME_DATE_FORMAT).replace(tzinfo=timezone.utc)
            downtime_intervals[resource][instrument_type].append({'type': 'start', 'time': start})
            downtime_intervals[resource][instrument_type].append({'type': 'end', 'time': end})

        for resource in downtime_intervals:
            for instrument_type, intervals in downtime_intervals[resource].items():
                downtime_intervals[resource][instrument_type] = Intervals(intervals)

        return downtime_intervals

    @staticmethod
    def get_downtime_intervals():
        ''' Returns dictionary of IntervalSets of downtime intervals per telescope resource and per instrument_type or "all".
            Caches the data and will attempt to update the cache every 15 minutes, but fallback on using previous downtime list otherwise.
        '''
        downtime_intervals = caches['locmem'].get('downtime_intervals', [])
        if not downtime_intervals:
            # If the cache has expired, attempt to update the downtime intervals
            try:
                data = DowntimeDB._get_downtime_data()
                downtime_intervals = DowntimeDB._order_downtime_by_resource_and_instrument_type(data)
                caches['locmem'].set('downtime_intervals', downtime_intervals, 900)
                caches['locmem'].set('downtime_intervals.no_expire', downtime_intervals)
            except DowntimeDBException as e:
                downtime_intervals = caches['locmem'].get('downtime_intervals.no_expire', [])
                logger.warning(repr(e))

        return downtime_intervals
