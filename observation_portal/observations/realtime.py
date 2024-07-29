from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User

from observation_portal.proposals.models import Semester
from observation_portal.common.configdb import configdb
from observation_portal.common.rise_set_utils import filtered_dark_intervalset_for_telescope


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
    for resource in telescopes_availability.keys():
        telescope, enclosure, site = resource.split('.')
        intervals = filtered_dark_intervalset_for_telescope(start, end, site, enclosure, telescope)
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
