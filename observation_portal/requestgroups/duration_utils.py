import itertools
from django.utils.translation import ugettext as _
from math import ceil, floor
import logging

from observation_portal.proposals.models import TimeAllocationKey, Proposal, Semester
from observation_portal.common.configdb import configdb
from observation_portal.common.rise_set_utils import get_rise_set_intervals, get_largest_interval

logger = logging.getLogger(__name__)


PER_MOLECULE_GAP = 5.0             # in-between configuration gap - shared for all instruments
PER_MOLECULE_STARTUP_TIME = 11.0   # per-configuration startup time, which encompasses initial pointing
OVERHEAD_ALLOWANCE = 1.1           # amount of leeway in a proposals timeallocation before rejecting that request
MAX_IPP_LIMIT = 2.0                # the maximum allowed value of ipp
MIN_IPP_LIMIT = 0.5                # the minimum allowed value of ipp
semesters = None

# TODO: Redo calculations including new overheads from configdb


def get_semesters():
    global semesters
    if not semesters:
        semesters = list(Semester.objects.all().order_by('-start'))
    return semesters


def get_semester_in(start_date, end_date):
    semesters = get_semesters()
    for semester in semesters:
        if start_date >= semester.start and end_date <= semester.end:
            return semester

    return None


def get_num_mol_changes(configurations):
    return len(list(itertools.groupby([conf['type'].upper() for conf in configurations])))


# TODO: filters go away replaced with optical elements groups
def get_num_filter_changes(configurations):
    return len(list(itertools.groupby([conf.get('filter', '') for conf in configurations])))


def get_instrument_configuration_duration_per_exposure(instrument_configuration_dict):
    total_overhead_per_exp = configdb.get_exposure_overhead(instrument_configuration_dict['name'], instrument_configuration_dict['bin_x'])
    duration_per_exp = instrument_configuration_dict['exposure_time'] + total_overhead_per_exp
    return duration_per_exp


def get_instrument_configuration_duration(instrument_config_dict):
    duration_per_exposure = get_instrument_configuration_duration_per_exposure(instrument_config_dict)
    return instrument_config_dict['exposure_count'] * duration_per_exposure


def get_configuration_duration(configuration_dict):
    duration = 0
    for inst_config in configuration_dict['instrument_configs']:
        duration += get_instrument_configuration_duration(inst_config)
    return duration + PER_MOLECULE_GAP + PER_MOLECULE_STARTUP_TIME


def get_request_duration_dict(request_dict):
    req_durations = {'requests': []}
    for req in request_dict:
        req_info = {'duration': get_request_duration(req)}
        # TODO: Have configuration duration as well as instrument configuration duration
        conf_durations = [{'duration': get_configuration_duration(conf)} for conf in req['configurations']]
        req_info['configurations'] = conf_durations
        req_info['largest_interval'] = get_largest_interval(get_rise_set_intervals(req)).total_seconds()
        req_info['largest_interval'] -= (PER_MOLECULE_STARTUP_TIME + PER_MOLECULE_GAP)
        req_durations['requests'].append(req_info)
    req_durations['duration'] = sum([req['duration'] for req in req_durations['requests']])

    return req_durations


def get_max_ipp_for_requestgroup(requestgroup_dict):
    proposal = Proposal.objects.get(pk=requestgroup_dict['proposal'])
    request_durations = get_request_duration_sum(requestgroup_dict)
    ipp_dict = {}
    for tak, duration in request_durations.items():
        time_allocation = proposal.timeallocation_set.get(
            semester=tak.semester, telescope_class=tak.telescope_class, instrument_name=tak.instrument_name
        )
        duration_hours = duration / 3600.0
        ipp_available = time_allocation.ipp_time_available
        max_ipp_allowable = min((ipp_available / duration_hours) + 1.0, MAX_IPP_LIMIT)
        truncated_max_ipp_allowable = floor(max_ipp_allowable * 1000.0) / 1000.0
        if tak.semester not in ipp_dict:
            ipp_dict[tak.semester] = {}
        if tak.telescope_class not in ipp_dict[tak.semester]:
            ipp_dict[tak.semester][tak.telescope_class] = {}
        ipp_dict[tak.semester][tak.telescope_class][tak.instrument_name] = {
            'ipp_time_available': ipp_available,
            'ipp_limit': time_allocation.ipp_limit,
            'request_duration': duration_hours,
            'max_allowable_ipp_value': truncated_max_ipp_allowable,
            'min_allowable_ipp_value': MIN_IPP_LIMIT
        }
    return ipp_dict


def get_request_duration_sum(requestgroup_dict):
    duration_sum = {}
    for req in requestgroup_dict['requests']:
        duration = get_request_duration(req)
        tak = get_time_allocation_key(
            telescope_class=req['location']['telescope_class'],
            instrument_name=req['configurations'][0]['instrument_name'],
            min_window_time=min([w['start'] for w in req['windows']]),
            max_window_time=max([w['end'] for w in req['windows']])
        )
        if tak not in duration_sum:
            duration_sum[tak] = 0
        duration_sum[tak] += duration
    return duration_sum


def get_num_exposures(configuration_dict, time_available):
    mol_duration_per_exp = get_instrument_configuration_duration_per_exposure(configuration_dict)
    exposure_time = time_available.total_seconds() - PER_MOLECULE_GAP - PER_MOLECULE_STARTUP_TIME
    num_exposures = exposure_time // mol_duration_per_exp

    return max(1, num_exposures)


def get_request_duration(request_dict):
    # calculate the total time needed by the request, based on its instrument and exposures
    request_overheads = configdb.get_request_overheads(request_dict['configurations'][0]['instrument_name'])
    duration = sum([get_configuration_duration(m) for m in request_dict['configurations']])
    if configdb.is_spectrograph(request_dict['configurations'][0]['instrument_name']):
        duration += get_num_mol_changes(request_dict['configurations']) * request_overheads['config_change_time']

        # for configuration in request_dict['configurations']:
        #     if configuration['acquire_mode'].upper() != 'OFF' and configuration['type'].upper() in ['SPECTRUM', 'NRES_SPECTRUM']:
        #         duration += request_overheads['acquire_exposure_time'] + request_overheads['acquire_processing_time']
    else:
        duration += get_num_filter_changes(request_dict['configurations']) * request_overheads['filter_change_time']

    duration += request_overheads['front_padding']
    duration = ceil(duration)

    return duration


def get_time_allocation(telescope_class, instrument_name, proposal_id, min_window_time, max_window_time):
    timeall = None
    try:
        timeall = Proposal.objects.get(pk=proposal_id).timeallocation_set.get(
            semester__start__lte=min_window_time,
            semester__end__gte=max_window_time,
            telescope_class=telescope_class,
            instrument_name=instrument_name)
    except Exception:
        logger.warn(_("proposal {0} has overlapping time allocations for {1} {2}").format(
            proposal_id, telescope_class, instrument_name
        ))
    return timeall


def get_time_allocation_key(telescope_class, instrument_name, min_window_time, max_window_time):
    semester = get_semester_in(min_window_time, max_window_time)
    return TimeAllocationKey(semester.id, instrument_name)


def get_total_duration_dict(requestgroup_dict):
    durations = []
    for request in requestgroup_dict['requests']:
        min_window_time = min([window['start'] for window in request['windows']])
        max_window_time = max([window['end'] for window in request['windows']])
        tak = get_time_allocation_key(request['location']['telescope_class'],
                                      request['configurations'][0]['instrument_name'],
                                      min_window_time,
                                      max_window_time
                                      )
        duration = get_request_duration(request)
        durations.append((tak, duration))
    # check the proposal has a time allocation with enough time for all requests depending on operator
    total_duration = {}
    if requestgroup_dict['operator'] == 'SINGLE':
        (tak, duration) = durations[0]
        total_duration[tak] = duration

    elif requestgroup_dict['operator'] in ['MANY', 'ONEOF']:
        for (tak, duration) in durations:
            total_duration[tak] = max(total_duration.get(tak, 0.0), duration)
    elif requestgroup_dict['operator'] == 'AND':
        for (tak, duration) in durations:
            if tak not in total_duration:
                total_duration[tak] = 0
            total_duration[tak] += duration

    return total_duration
