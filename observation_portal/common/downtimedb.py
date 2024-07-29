import requests
from django.core.cache import caches
from django.utils.translation import gettext as _
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
    def refresh_downtime_intervals():
        ''' Refreshes the cached intervals of downtimes - necessary after submitting downtimes so they
            can be used right away.
        '''
        try:
            data = DowntimeDB._get_downtime_data()
            downtime_intervals = DowntimeDB._order_downtime_by_resource_and_instrument_type(data)
            caches['locmem'].set('downtime_intervals', downtime_intervals, 900)
            caches['locmem'].set('downtime_intervals.no_expire', downtime_intervals)
            return downtime_intervals
        except DowntimeDBException as e:
            logger.warning(repr(e))
        return None

    @staticmethod
    def get_downtime_intervals():
        ''' Returns dictionary of IntervalSets of downtime intervals per telescope resource and per instrument_type or "all".
            Caches the data and will attempt to update the cache every 15 minutes, but fallback on using previous downtime list otherwise.
        '''
        downtime_intervals = caches['locmem'].get('downtime_intervals', {})
        if not downtime_intervals:
            # If the cache has expired, attempt to update the downtime intervals
            downtime_intervals = DowntimeDB.refresh_downtime_intervals()
            if downtime_intervals is None:
                downtime_intervals = caches['locmem'].get('downtime_intervals.no_expire', {})

        return downtime_intervals

    @staticmethod
    def create_downtime_interval(headers, downtime):
        ''' Takes in a headers dict and downtime dict to create in the downtime app
            Returns the created downtime block and raises a DowntimeDBException on error.
        '''
        try:
            r = requests.post(settings.DOWNTIMEDB_URL + 'api/', json=downtime, headers=headers)
            r.raise_for_status()
            DowntimeDB.refresh_downtime_intervals()
            return r.json()
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
            msg = "{}: {}".format(e.__class__.__name__, DOWNTIMEDB_ERROR_MSG)
            raise DowntimeDBException(msg)

    @staticmethod
    def delete_downtime_interval(headers, site, enclosure, telescope, observation_id):
        ''' Takes in a headers dict and downtime dict to delete a downtime with those fields
            from the downtime app. Returns True if something was deleted, False otherwise.
        '''
        downtime_id = 'N/A'
        try:
            url = settings.DOWNTIMEDB_URL + "api/"
            get_url = url + f"?site={site}&enclosure={enclosure}&telescope={telescope}&reason_exact={observation_id}"
            r = requests.get(get_url, headers=headers)
            results = r.json()
            if results.get('count') != 1:
                logger.error(f"Trying to get downtimes for observation {observation_id} had {results.get('count')} results. This should never happen!")
            else:
                downtime_id = results.get('results')[0].get('id')
                r = requests.delete(url + f"{downtime_id}/", headers=headers)
                r.raise_for_status()
                DowntimeDB.refresh_downtime_intervals()
                return True
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
            logger.warning(f"Failed to delete downtime {downtime_id} for observation {observation_id}: {repr(e)}")
            return False
        return False
