import itertools
from django.utils.translation import ugettext as _
from math import ceil, floor
import logging

from observation_portal.proposals.models import TimeAllocationKey, Proposal, Semester
from observation_portal.common.configdb import configdb
from observation_portal.common.rise_set_utils import get_rise_set_intervals, get_largest_interval

logger = logging.getLogger(__name__)


PER_CONFIGURATION_GAP = 5.0             # in-between configuration gap - shared for all instruments
PER_CONFIGURATION_STARTUP_TIME = 11.0   # per-configuration startup time, which encompasses initial pointing
OVERHEAD_ALLOWANCE = 1.1           # amount of leeway in a proposals timeallocation before rejecting that request
MAX_IPP_LIMIT = 2.0                # the maximum allowed value of ipp
MIN_IPP_LIMIT = 0.5                # the minimum allowed value of ipp
semesters = None


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


def get_instrument_configuration_duration_per_exposure(instrument_configuration_dict, instrument_name):
    total_overhead_per_exp = configdb.get_exposure_overhead(instrument_name,
                                                            instrument_configuration_dict['bin_x'],
                                                            instrument_configuration_dict['mode'])
    duration_per_exp = instrument_configuration_dict['exposure_time'] + total_overhead_per_exp
    return duration_per_exp


def get_instrument_configuration_duration(instrument_config_dict, instrument_name):
    duration_per_exposure = get_instrument_configuration_duration_per_exposure(instrument_config_dict, instrument_name)
    return instrument_config_dict['exposure_count'] * duration_per_exposure


def get_configuration_duration(configuration_dict):
    request_overheads = configdb.get_request_overheads(configuration_dict['instrument_name'])
    duration = 0
    previous_optical_elements = {}
    for inst_config in configuration_dict['instrument_configs']:
        duration += get_instrument_configuration_duration(inst_config, configuration_dict['instrument_name'])
        change_overhead = 0
        # Assume all optical element changes are done in parallel so just take the max of all elements changing
        for oe_type, oe_value in inst_config['optical_elements'].items():
            if oe_type not in previous_optical_elements or oe_value != previous_optical_elements[oe_type]:
                change_overhead = max(request_overheads['optical_element_change_overheads']['{}s'.format(oe_type)], change_overhead)
        previous_optical_elements = inst_config['optical_elements']
        duration += change_overhead
    return duration + PER_CONFIGURATION_GAP + PER_CONFIGURATION_STARTUP_TIME


def get_request_duration_dict(request_dict):
    req_durations = {'requests': []}
    for req in request_dict:
        req_info = {'duration': get_request_duration(req)}
        # TODO: Have configuration duration as well as instrument configuration duration
        conf_durations = [{'duration': get_configuration_duration(conf)} for conf in req['configurations']]
        req_info['configurations'] = conf_durations
        req_info['largest_interval'] = get_largest_interval(get_rise_set_intervals(req)).total_seconds()
        req_info['largest_interval'] -= (PER_CONFIGURATION_STARTUP_TIME + PER_CONFIGURATION_GAP)
        req_durations['requests'].append(req_info)
    req_durations['duration'] = sum([req['duration'] for req in req_durations['requests']])

    return req_durations


def get_max_ipp_for_requestgroup(requestgroup_dict):
    proposal = Proposal.objects.get(pk=requestgroup_dict['proposal'])
    request_durations = get_request_duration_sum(requestgroup_dict)
    ipp_dict = {}
    for tak, duration in request_durations.items():
        time_allocation = proposal.timeallocation_set.get(
            semester=tak.semester, instrument_name=tak.instrument_name
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
    exposure_time = time_available.total_seconds() - PER_CONFIGURATION_GAP - PER_CONFIGURATION_STARTUP_TIME
    num_exposures = exposure_time // mol_duration_per_exp

    return max(1, num_exposures)


# TODO: implement this (distance between two targets in arcsec)
def get_slew_distance(target_dict1, target_dict2):
    return 0


def get_request_duration(request_dict):
    # calculate the total time needed by the request, based on its instrument and exposures
    duration = 0
    previous_instrument = ''
    previous_target = {}
    previous_conf_type = ''
    configurations = sorted(request_dict['configurations'], key=lambda x: x['priority'])
    for configuration in configurations:
        duration += get_configuration_duration(configuration)
        request_overheads = configdb.get_request_overheads(configuration['instrument_name'])
        # Add the instrument change time if the instrument has changed
        if previous_instrument != configuration['instrument_name']:
            duration += request_overheads['instrument_change_overhead']
        previous_instrument = configuration['instrument_name']

        # Now add in the slew time between targets (configurations)
        if previous_target != configuration['target']:
            duration += max(get_slew_distance(previous_target, configuration['target']) * request_overheads['slew_rate'], request_overheads['minimum_slew_overhead'])
        previous_target = configuration['target']

        # Now add the Acquisition overhead if this request requires it
        if configuration['acquisition_config']['mode'] != 'OFF':
            if configuration['acquisition_config']['mode'] in request_overheads['acquisition_overheads']:
                duration += request_overheads['acquisition_overheads'][configuration['acquisition_config']['mode']]

        # Now add the Guiding overhead if this request requires it
        if configuration['guiding_config']['state'] == 'ON':
            if configuration['guiding_config']['mode'] in request_overheads['guiding_overheads']:
                duration += request_overheads['guiding_overheads'][configuration['guiding_config']['mode']]

        # TODO: find out if we need to have a configuration type change time for spectrographs?
        if configdb.is_spectrograph(configuration['instrument_name']):
            if previous_conf_type != configuration['type']:
                duration += request_overheads['config_change_time']
        previous_conf_type = configuration['type']

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


def get_time_allocation_key(instrument_name, min_window_time, max_window_time):
    semester = get_semester_in(min_window_time, max_window_time)
    return TimeAllocationKey(semester.id, instrument_name)


def get_total_duration_dict(requestgroup_dict):
    durations = []
    for request in requestgroup_dict['requests']:
        min_window_time = min([window['start'] for window in request['windows']])
        max_window_time = max([window['end'] for window in request['windows']])
        tak = get_time_allocation_key(request['configurations'][0]['instrument_name'],
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
