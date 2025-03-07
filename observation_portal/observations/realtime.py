from datetime import timedelta, datetime
from collections import defaultdict

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from time_intervals.intervals import Intervals

from observation_portal.proposals.models import Semester
from observation_portal.observations.models import Observation
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.common.configdb import configdb
from observation_portal.common.rise_set_utils import filtered_dark_intervalset_for_telescope


def get_already_booked_intervals(user: User, start: datetime, end: datetime):
    """ Get already booked times for this user to block out on all telescopes
    """
    already_booked_obs = Observation.objects.filter(
        request__request_group__submitter=user,
        request__request_group__observation_type=RequestGroup.REAL_TIME,
        start__lt=end,
        end__gt=start
    )
    already_booked_intervals = []
    for obs in already_booked_obs:
        already_booked_intervals.append((obs.start, obs.end))
    return Intervals(already_booked_intervals)


def obs_query_to_intervals_by_resource(obs_query):
    """ Takes in a django queryset of Observations and returns a dict of Intervals by resource for those observations
    """
    intervals_by_resource = defaultdict(list)
    # Iterate over all observations and add their start/end times to tuple list per resource
    for obs in obs_query:
        resource = f'{obs.telescope}.{obs.enclosure}.{obs.site}'
        intervals_by_resource[resource].append((obs.start, obs.end))

    # Now iterate over all interval tuple lists and convert them to interval objects
    for resource in intervals_by_resource.keys():
        intervals_by_resource[resource] = Intervals(intervals_by_resource[resource])

    return intervals_by_resource


def get_in_progress_observation_intervals_by_resource(telescope_filter: str, start: datetime, end: datetime):
    """ Get a dict of in progress observation intervals of time to block off by resource (tel.enc.site)
    """
    # First get the set of currently running observations in the time interval
    running_obs = Observation.objects.filter(
        state='IN_PROGRESS',
        start__lt=end,
        end__gt=start,
    )
    # If a specific telescope_filter is specified, we can restrict the query here
    if telescope_filter:
        telescope, enclosure, site = telescope_filter.split('.')
        running_obs.filter(
            telescope=telescope,
            enclosure=enclosure,
            site=site
        )

    return obs_query_to_intervals_by_resource(running_obs)


def get_future_important_scheduled_observation_intervals_by_resource(telescope_filter: str, start: datetime, end: datetime):
    """ Get a dict of future observation intervals of time to block off by resource (tel.enc.site)
    """
    # First get the set of future TC, RR, and Direct observations in the time interval
    future_important_obs = Observation.objects.filter(
        request__request_group__observation_type__in=[
            RequestGroup.TIME_CRITICAL, RequestGroup.RAPID_RESPONSE, RequestGroup.DIRECT],
        start__lt=end,
        end__gt=start,
    )
    # If a specific telescope_filter is specified, we can restrict the query here
    if telescope_filter:
        telescope, enclosure, site = telescope_filter.split('.')
        future_important_obs.filter(
            telescope=telescope,
            enclosure=enclosure,
            site=site
        )

    return obs_query_to_intervals_by_resource(future_important_obs)


def get_realtime_availability(user: User, telescope_filter: str = ''):
    """ Returns a dict of lists of availability intervals for each
        telescope, limited to just a specific telescope if specified

        telescope_filter should be of the form telescope_code.enclosure_code.site_code (i.e. 0m4a.clma.tst)
    """
    # Get the set of telescopes available for a users proposals and optionally filtered by the telescope param
    instrument_types_available = set()
    telescopes_availability = {}
    for proposal in user.profile.current_proposals:
        for ta in proposal.timeallocation_set.filter(semester=Semester.current_semesters().first()):
            if ta.realtime_allocation > 0 and ta.realtime_time_used < ta.realtime_allocation:
                for instrument_type in ta.instrument_types:
                    instrument_types_available.add(instrument_type)
                    telescope_info = configdb.get_telescopes_with_instrument_type_and_location(instrument_type)
                    for key in telescope_info:
                        if not telescope_filter or key == telescope_filter:
                            telescopes_availability[key] = []

    # Now go through each telescope and get its availability intervals
    start = timezone.now() + timedelta(minutes=settings.REAL_TIME_AVAILABILITY_MINUTES_IN)
    end = start + timedelta(days=settings.REAL_TIME_AVAILABILITY_DAYS_OUT)

    # Get already booked times for this user to block out on all telescopes
    already_booked_interval = get_already_booked_intervals(user, start, end)
    # Get in progress observation intervals by resource
    in_progress_intervals = get_in_progress_observation_intervals_by_resource(telescope_filter, start, end)
    # Get future scheduled TC, RR, and Direct observation intervals by resource
    future_intervals = get_future_important_scheduled_observation_intervals_by_resource(telescope_filter, start, end)

    for resource in telescopes_availability.keys():
        telescope, enclosure, site = resource.split('.')
        intervals = filtered_dark_intervalset_for_telescope(start, end, site, enclosure, telescope)
        intervals_to_block = []
        # Now also filter out running obs, future high priority (TC, RR, Direct) obs, and obs overlapping in time by the user
        if resource in in_progress_intervals:
            intervals_to_block.append(in_progress_intervals[resource])
        if resource in future_intervals:
            intervals_to_block.append(future_intervals[resource])
        intervals_to_block = already_booked_interval.union(intervals_to_block)
        intervals = intervals.subtract(intervals_to_block)
        for interval in intervals.toTupleList():
            telescopes_availability[resource].append([interval[0].isoformat(), interval[1].isoformat()])

    return telescopes_availability


def realtime_time_available(instrument_types: list, proposal: str):
    """ Returns the (max) realtime time available on the proposal given a set of
        potential instrument_types. The instrument_types are really just a standin for
        the telescope, since real time blocks are per telescope and block the whole telescope.
    """
    realtime_available = 0.0
    for ta in proposal.timeallocation_set.filter(semester=Semester.current_semesters().first()):
        for instrument_type in ta.instrument_types:
            if instrument_type.upper() in instrument_types:
                # Just return the max time allocation available since its possible to have multiple that match
                realtime_available = max(realtime_available, ta.realtime_allocation - ta.realtime_time_used)
                continue
    return realtime_available
