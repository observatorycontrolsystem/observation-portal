from django.conf import settings
from elasticsearch import Elasticsearch
from elasticsearch import exceptions as es_exceptions
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from copy import deepcopy
from collections import OrderedDict
import logging
from dateutil.parser import parse

from observation_portal.common.configdb import configdb, TelescopeKey
from observation_portal.common.rise_set_utils import get_site_rise_set_intervals

logger = logging.getLogger(__name__)

ES_STRING_FORMATTER = "%Y-%m-%d %H:%M:%S"


class ElasticSearchException(Exception):
    pass


def string_to_datetime(timestamp):
    return parse(timestamp).replace(tzinfo=timezone.utc)


class TelescopeStates(object):
    EVENT_CATEGORIES = OrderedDict([
        ('Site Agent: ', 'SITE_AGENT_UNRESPONSIVE'),
        ('Weather: ', 'NOT_OK_TO_OPEN'),
        ('Sequencer: ', 'SEQUENCER_DISABLED'),
        ('Enclosure: ', 'ENCLOSURE_INTERLOCK'),
        ('Enclosure Shutter Mode: ', 'ENCLOSURE_DISABLED')
    ])

    def __init__(self, start, end, telescopes=None, sites=None, instrument_types=None, location_dict=None, only_schedulable=True):
        try:
            if not settings.ELASTICSEARCH_URL:
                raise ImproperlyConfigured("ELASTICSEARCH_URL")
            self.es = Elasticsearch([settings.ELASTICSEARCH_URL])
        except Exception:
            self.es = None
            logger.exception('Could not connect to Elasticsearch host. Make sure ELASTICSEARCH_URL is set properly. For now, it will be ignored.')

        self.instrument_types = instrument_types
        self.only_schedulable = only_schedulable
        self.available_telescopes = self._get_available_telescopes(location_dict)

        sites = list({tk.site for tk in self.available_telescopes}) if not sites else sites
        telescopes = list({tk.telescope for tk in self.available_telescopes if tk.site in sites}) \
            if not telescopes else telescopes

        self.start = start.replace(tzinfo=timezone.utc).replace(microsecond=0)
        self.end = end.replace(tzinfo=timezone.utc).replace(microsecond=0)
        self.event_data = self._get_es_data(sites, telescopes)

    def _get_available_telescopes(self, location_dict=None):
        telescope_to_instruments = configdb.get_instrument_types_per_telescope(location=location_dict,
                                                                               only_schedulable=self.only_schedulable)
        if not self.instrument_types:
            available_telescopes = telescope_to_instruments.keys()
        else:
            available_telescopes = [tk for tk, insts in telescope_to_instruments.items() if
                                    any(inst in insts for inst in self.instrument_types)]
        return available_telescopes

    def _get_es_data(self, sites, telescopes):
        event_data = []
        if self.es:
            lower_query_time = min(self.start, timezone.now())
            datum_query = {
                "query": {
                    "bool": {
                        "filter": [
                            {
                                "match": {
                                    "datumname": "Available For Scheduling Reason"
                                }
                            },
                            {
                                "range": {
                                    "timestamp": {
                                        # Retrieve documents 1 day back to ensure you get at least one datum per telescope.
                                        "gte": (lower_query_time - timedelta(days=1)).strftime(ES_STRING_FORMATTER),
                                        "lte": self.end.strftime(ES_STRING_FORMATTER),
                                        "format": "yyyy-MM-dd HH:mm:ss"
                                    }
                                }
                            },
                            {
                                "terms": {
                                    "telescope": telescopes
                                }
                            },
                            {
                                "terms": {
                                    "site": sites
                                }
                            }
                        ]
                    }
                }
            }
            query_size = 10000

            try:
                data = self.es.search(
                    index="mysql-telemetry-*", body=datum_query, size=query_size, scroll='1m',  # noqa
                    _source=['timestamp', 'telescope', 'observatory', 'site', 'value_string'],
                    sort=['site', 'observatory', 'telescope', 'timestamp']
                )
            except es_exceptions.ConnectionError:
                raise ElasticSearchException

            event_data.extend(data['hits']['hits'])
            total_events = data['hits']['total']
            events_read = min(query_size, total_events)
            scroll_id = data.get('_scroll_id', 0)
            while events_read < total_events:
                data = self.es.scroll(scroll_id=scroll_id, scroll='1m') # noqa
                scroll_id = data.get('_scroll_id', 0)
                event_data.extend(data['hits']['hits'])
                events_read += len(data['hits']['hits'])
        return event_data

    def get(self):
        telescope_states = {}
        current_lump = {'telescope': None}

        for event in self.event_data:
            telcode = self._telescope(event['_source'])
            if telcode not in self.available_telescopes:
                if current_lump['telescope']:
                    self._save_lump(telescope_states, current_lump, self.end)
                    current_lump = {'telescope': None}
                continue

            event_start = string_to_datetime(event['_source']['timestamp'])
            event_type, event_reason = self._categorize(event['_source'])

            if current_lump['telescope'] and telcode != current_lump['telescope']:
                telescope_states = self._save_lump(telescope_states, current_lump, self.end)
                current_lump = self._create_lump(telcode, event_type, event_reason, event_start)
            elif event_start > self.end:
                if current_lump['telescope']:
                    telescope_states = self._save_lump(telescope_states, current_lump, self.end)
                    current_lump = {'telescope': None}
            elif event_start < self.start:
                current_lump = self._create_lump(telcode, event_type, event_reason, event_start)
            else:
                if current_lump['telescope']:
                    if event_type != current_lump['event_type'] or event_reason != current_lump['event_reason']:
                        telescope_states = self._save_lump(telescope_states, current_lump, min(self.end, event_start))
                        current_lump = self._create_lump(telcode, event_type, event_reason, event_start)
                else:
                    current_lump = self._create_lump(telcode, event_type, event_reason, event_start)

        if current_lump['telescope']:
            # We have a final current lump we were in, so save it
            self._save_lump(telescope_states, current_lump, self.end)

        return telescope_states

    def _save_lump(self, telescope_states, lump, end):
        lump['end'] = min(self.end, end)
        lump['start'] = max(self.start, lump['start'])
        telkey = lump['telescope']
        lump['telescope'] = str(lump['telescope'])
        if telkey not in telescope_states:
            telescope_states[telkey] = []
        telescope_states[telkey].append(lump)

        return telescope_states

    @staticmethod
    def _create_lump(telcode, event_type, event_reason, event_start):
        return {
            'telescope': telcode,
            'event_type': event_type,
            'event_reason': event_reason,
            'start': event_start,
        }

    def _categorize(self, event):
        # TODO: Categorize each lump in a useful way for network users.
        reason = event['value_string']
        if not reason:
            return "AVAILABLE", "Available for scheduling"

        reasons = reason.split('.')
        for key in self.EVENT_CATEGORIES.keys():
            for r in reasons:
                if key in r:
                    return self.EVENT_CATEGORIES[key], reason

        return "NOT_AVAILABLE", "Unknown"

    @staticmethod
    def _telescope(event_source):
        return TelescopeKey(
            site=event_source['site'],
            enclosure=event_source['observatory'],
            telescope=event_source['telescope']
        )


def filter_telescope_states_by_intervals(telescope_states, sites_intervals, start, end):
    filtered_states = {}
    for telescope_key, events in telescope_states.items():
        # now loop through the events for the telescope, and tally the time the telescope is available for each 'day'
        if telescope_key.site in sites_intervals:
            site_intervals = sites_intervals[telescope_key.site]
            filtered_events = []

            for event in events:
                event_start = max(event['start'], start)
                event_end = min(event['end'], end)
                for interval in site_intervals:
                    if event_start >= interval[0] and event_end <= interval[1]:
                        # the event is fully contained to add it and break out
                        extra_event = deepcopy(event)
                        extra_event['start'] = event_start
                        extra_event['end'] = event_end
                        filtered_events.append(deepcopy(event))
                    elif event_start < interval[0] and event_end > interval[1]:
                        # start is before interval and end is after, so it spans the interval
                        extra_event = deepcopy(event)
                        extra_event['start'] = interval[0]
                        extra_event['end'] = interval[1]
                        filtered_events.append(deepcopy(extra_event))
                    elif event_start < interval[0] and event_end > interval[0] and event_end <= interval[1]:
                        # start is before interval and end is in interval, so truncate start
                        extra_event = deepcopy(event)
                        extra_event['start'] = interval[0]
                        extra_event['end'] = event_end
                        filtered_events.append(deepcopy(extra_event))
                    elif event_start >= interval[0] and event_start < interval[1] and event_end > interval[1]:
                        # start is within interval and end is after, so truncate end
                        extra_event = deepcopy(event)
                        extra_event['start'] = event_start
                        extra_event['end'] = interval[1]
                        filtered_events.append(deepcopy(extra_event))

            filtered_states[telescope_key] = filtered_events

    return filtered_states


def get_telescope_availability_per_day(start, end, telescopes=None, sites=None, instrument_types=None):
    telescope_states = TelescopeStates(start, end, telescopes, sites, instrument_types).get()
    # go through each telescopes list of states, grouping it up by observing night at the site
    rise_set_intervals = {}
    for telescope_key, events in telescope_states.items():
        if telescope_key.site not in rise_set_intervals:
            # remove the first and last interval as they may only be partial intervals
            rise_set_intervals[telescope_key.site] = get_site_rise_set_intervals(start - timedelta(days=1),
                                                                                 end + timedelta(days=1),
                                                                                 telescope_key.site)[1:]
    telescope_states = filter_telescope_states_by_intervals(telescope_states, rise_set_intervals, start, end)
    # now just compute a % available each day from the rise_set filtered set of events
    telescope_availability = {}
    for telescope_key, events in telescope_states.items():
        telescope_availability[telescope_key] = []
        time_available = timedelta(seconds=0)
        time_total = timedelta(seconds=0)
        if events:
            current_day = list(events)[0]['start'].date()
            current_end = list(events)[0]['start']
        for event in events:
            if (event['start'] - current_end) > timedelta(hours=4):
                if (event['start'].date() != current_day):
                    # we must be in a new observing day, so tally time in previous day and increment day counter
                    telescope_availability[telescope_key].append([current_day, (
                        time_available.total_seconds() / time_total.total_seconds())])
                time_available = timedelta(seconds=0)
                time_total = timedelta(seconds=0)
                current_day = event['start'].date()

            if 'AVAILABLE' == event['event_type'].upper():
                time_available += event['end'] - event['start']
            time_total += event['end'] - event['start']
            current_end = event['end']

        if time_total > timedelta():
            telescope_availability[telescope_key].append([current_day, (
                time_available.total_seconds() / time_total.total_seconds())])

    return telescope_availability


def combine_telescope_availabilities_by_site_and_class(telescope_availabilities):
    combined_keys = {TelescopeKey(tk.site, '', tk.telescope[:-1]) for tk in telescope_availabilities.keys()}
    combined_availabilities = {}
    for key in combined_keys:
        num_groups = 0
        total_availability = []
        for telescope_key, availabilities in telescope_availabilities.items():
            if telescope_key.site == key.site and telescope_key.telescope[:-1] == key.telescope:
                num_groups += 1
                if not total_availability:
                    total_availability = availabilities
                else:
                    for i, availability in enumerate(availabilities):
                        total_availability[i][1] += availability[1]

        for i, availability in enumerate(total_availability):
            total_availability[i][1] /= num_groups
        combined_availabilities[key] = total_availability

    return combined_availabilities
