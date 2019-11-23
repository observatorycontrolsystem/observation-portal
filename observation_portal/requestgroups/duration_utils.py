from django.utils.translation import ugettext as _
from math import ceil, floor
from django.utils import timezone
import logging

from observation_portal.proposals.models import TimeAllocationKey, Proposal, Semester
from observation_portal.common.configdb import configdb
from observation_portal.common.rise_set_utils import (get_filtered_rise_set_intervals_by_site, get_largest_interval,
                                                      get_distance_between, get_rise_set_target)

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
    conf_duration = {}
    instrumentconf_durations = [{
        'duration': get_instrument_configuration_duration(
            ic, configuration_dict['instrument_type']
        )} for ic in configuration_dict['instrument_configs']
    ]
    conf_duration['instrument_configs'] = instrumentconf_durations
    if ('REPEAT' in configuration_dict['type'] and 'repeat_duration' in configuration_dict
            and configuration_dict['repeat_duration'] is not None):
        conf_duration['duration'] = configuration_dict['repeat_duration']
    else:
        conf_duration['duration'] = sum([icd['duration'] for icd in instrumentconf_durations])
    conf_duration['duration'] += (PER_CONFIGURATION_GAP + PER_CONFIGURATION_STARTUP_TIME)
    return conf_duration


def get_request_duration_dict(request_dict, is_staff=False):
    req_durations = {'requests': []}
    for req in request_dict:
        req_info = {'duration': get_request_duration(req)}
        conf_durations = [get_configuration_duration(conf) for conf in req['configurations']]
        req_info['configurations'] = conf_durations
        rise_set_intervals = get_filtered_rise_set_intervals_by_site(req, is_staff=is_staff)
        req_info['largest_interval'] = get_largest_interval(rise_set_intervals).total_seconds()
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
            semester=tak.semester, instrument_type=tak.instrument_type
        )
        duration_hours = duration / 3600.0
        ipp_available = time_allocation.ipp_time_available
        max_ipp_allowable = min((ipp_available / duration_hours) + 1.0, MAX_IPP_LIMIT)
        truncated_max_ipp_allowable = floor(max_ipp_allowable * 1000.0) / 1000.0
        if tak.semester not in ipp_dict:
            ipp_dict[tak.semester] = {}
        ipp_dict[tak.semester][tak.instrument_type] = {
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
            instrument_type=req['configurations'][0]['instrument_type'],
            min_window_time=min([w['start'] for w in req['windows']]),
            max_window_time=max([w['end'] for w in req['windows']])
        )
        if tak not in duration_sum:
            duration_sum[tak] = 0
        duration_sum[tak] += duration
    return duration_sum


def get_num_exposures(instrument_config_dict, instrument_name,  time_available):
    duration_per_exp = get_instrument_configuration_duration_per_exposure(instrument_config_dict, instrument_name)
    exposure_time = time_available.total_seconds()
    num_exposures = exposure_time // duration_per_exp
    if exposure_time % duration_per_exp == 0:
        num_exposures -= 1
    return max(1, num_exposures)


# TODO: implement this (distance between two targets in arcsec)
def get_slew_distance(target_dict1, target_dict2, start_time):
    '''
        Get the angular distance between two targets, in units of arcseconds
    :param target_dict1:
    :param target_dict2:
    :return:
    '''
    rs_target_1 = get_rise_set_target(target_dict1)
    rs_target_2 = get_rise_set_target(target_dict2)
    distance_between = get_distance_between(rs_target_1, rs_target_2, start_time)
    return distance_between.in_degrees() * 3600


def get_complete_configurations_duration(configurations_list, start_time, priority_after=-1):
    previous_conf_type = ''
    previous_optical_elements = {}
    previous_instrument = ''
    previous_target = {}
    duration = 0
    for configuration_dict in configurations_list:
        if configuration_dict['priority'] > priority_after:
            duration += get_configuration_duration(configuration_dict)['duration']
            request_overheads = configdb.get_request_overheads(configuration_dict['instrument_type'])
            # Add the instrument change time if the instrument has changed
            if previous_instrument != configuration_dict['instrument_type']:
                duration += request_overheads['instrument_change_overhead']
            previous_instrument = configuration_dict['instrument_type']

            # Now add in optical element change time if the set of optical elements has changed
            for inst_config in configuration_dict['instrument_configs']:
                optical_elements = inst_config.get('optical_elements', {})
                change_overhead = 0
                for oe_type, oe_value in optical_elements.items():
                    if oe_type not in previous_optical_elements or oe_value != previous_optical_elements[oe_type]:
                        if '{}s'.format(oe_type) in request_overheads['optical_element_change_overheads']:
                            change_overhead = max(request_overheads['optical_element_change_overheads']['{}s'.format(oe_type)], change_overhead)
                previous_optical_elements = optical_elements
                duration += change_overhead

            # Now add in the slew time between targets (configurations). Only Sidereal can be calculated based on position.
            if (
                    not previous_target
                    or previous_target['type'].upper() != 'ICRS'
                    or configuration_dict['target']['type'].upper() != 'ICRS'
            ):
                duration += request_overheads['maximum_slew_overhead']
            elif previous_target != configuration_dict['target']:
                duration += min(max(get_slew_distance(previous_target, configuration_dict['target'], start_time)
                                    * request_overheads['slew_rate'], request_overheads['minimum_slew_overhead']),
                                request_overheads['maximum_slew_overhead'])
            previous_target = configuration_dict['target']

            # Now add the Acquisition overhead if this request requires it
            if configuration_dict['acquisition_config']['mode'] != 'OFF':
                if configuration_dict['acquisition_config']['mode'] in request_overheads['acquisition_overheads']:
                    duration += request_overheads['acquisition_overheads'][configuration_dict['acquisition_config']['mode']]
                    if 'exposure_time' in configuration_dict['acquisition_config'] and configuration_dict['acquisition_config']['exposure_time']:
                        duration += configuration_dict['acquisition_config']['exposure_time']
                    else:
                        duration += request_overheads['default_acquisition_exposure_time']

            # Now add the Guiding overhead if this request requires it
            guide_optional = configuration_dict['guiding_config']['optional'] if 'optional' in configuration_dict['guiding_config'] \
                else True
            if configuration_dict['guiding_config']['mode'] != 'OFF' and not guide_optional:
                if configuration_dict['guiding_config']['mode'] in request_overheads['guiding_overheads']:
                    duration += request_overheads['guiding_overheads'][configuration_dict['guiding_config']['mode']]

            # TODO: find out if we need to have a configuration type change time for spectrographs?
            if configdb.is_spectrograph(configuration_dict['instrument_type']):
                if previous_conf_type != configuration_dict['type']:
                    duration += request_overheads['config_change_overhead']
            previous_conf_type = configuration_dict['type']
        else:
            previous_conf_type = configuration_dict['type']
            previous_instrument = configuration_dict['instrument_type']
            previous_target = configuration_dict['target']
            previous_optical_elements = configuration_dict['instrument_configs'][-1].get('optical_elements', {})

    return duration


def get_request_duration(request_dict):
    # calculate the total time needed by the request, based on its instrument and exposures
    duration = 0
    previous_instrument = ''
    previous_target = {}
    previous_conf_type = ''
    previous_optical_elements = {}
    start_time = (min([window['start'] for window in request_dict['windows']])
                  if 'windows' in request_dict and request_dict['windows'] else timezone.now())
    try:
        configurations = sorted(request_dict['configurations'], key=lambda x: x['priority'])
    except KeyError:
        configurations = request_dict['configurations']
    duration += get_complete_configurations_duration(configurations, start_time)
    request_overheads = configdb.get_request_overheads(request_dict['configurations'][0]['instrument_type'])
    duration += request_overheads['front_padding']
    duration = ceil(duration)

    return duration


def get_time_allocation(instrument_type, proposal_id, min_window_time, max_window_time):
    timeall = None
    try:
        timeall = Proposal.objects.get(pk=proposal_id).timeallocation_set.get(
            semester__start__lte=min_window_time,
            semester__end__gte=max_window_time,
            instrument_type=instrument_type)
    except Exception:
        logger.warn(_("proposal {0} has overlapping time allocations for {1}").format(proposal_id, instrument_type))
    return timeall


def get_time_allocation_key(instrument_type, min_window_time, max_window_time):
    semester = get_semester_in(min_window_time, max_window_time)
    return TimeAllocationKey(semester.id, instrument_type)


def get_total_duration_dict(requestgroup_dict):
    durations = []
    for request in requestgroup_dict['requests']:
        min_window_time = min([window['start'] for window in request['windows']])
        max_window_time = max([window['end'] for window in request['windows']])
        tak = get_time_allocation_key(
            request['configurations'][0]['instrument_type'],
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
