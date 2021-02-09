from math import cos, radians
from collections import defaultdict
from datetime import datetime, timedelta
import json

from time_intervals.intervals import Intervals
from rise_set.astrometry import (
    make_ra_dec_target, make_satellite_target, make_hour_angle_target, make_minor_planet_target, mean_to_apparent,
    make_comet_target, make_major_planet_target, angular_distance_between, date_to_tdb
)
from rise_set.angle import Angle
from rise_set.rates import ProperMotion
from rise_set.visibility import Visibility
from rise_set.exceptions import MovingViolation
from django.core.cache import cache

from observation_portal.common.configdb import configdb, ConfigDB
from observation_portal.common.downtimedb import DowntimeDB
from observation_portal.requestgroups.target_helpers import TARGET_TYPE_HELPER_MAP

HOURS_PER_DEGREES = 15.0


def get_largest_interval(intervals_by_site):
    largest_interval = timedelta(seconds=0)
    for intervals in intervals_by_site.values():
        for interval in intervals:
            largest_interval = max((interval[1] - interval[0]), largest_interval)

    return largest_interval


def get_rise_set_intervals_by_site(request: dict, only_schedulable: bool = False) -> dict:
    """Get rise_set intervals by site for a request

    Computes the intervals only if they do not already exist in cache.

    Parameters:
        request: The request for which to get the intervals
    Returns:
        rise_set intervals by site
    """
    site_details = configdb.get_sites_with_instrument_type_and_location(
        instrument_type=request['configurations'][0]['instrument_type'],
        only_schedulable=only_schedulable
    )
    intervals_by_site = {}
    for site in site_details:
        intervals_by_site[site] = None
        if request.get('id'):
            cache_key = '{}.{}.rsi'.format(request['id'], site)
            intervals_by_site[site] = cache.get(cache_key, None)

        if intervals_by_site[site] is None:
            # There is no cached rise_set intervals for this request and site, so recalculate it now
            intervals_by_site[site] = []
            rise_set_site = get_rise_set_site(site_details[site])
            unique_targets_constraints = set([json.dumps((configuration['target'], configuration['constraints'])) for configuration in request['configurations']])

            for window in request['windows']:
                visibility = get_rise_set_visibility(rise_set_site, window['start'], window['end'], site_details[site])
                target_intervals = Intervals()
                first_target = True
                for target_constraints in unique_targets_constraints:
                    (target, constraints) = json.loads(target_constraints)
                    rise_set_target = get_rise_set_target(target)
                    try:
                        rs_interval = visibility.get_observable_intervals(
                            rise_set_target,
                            airmass=constraints['max_airmass'],
                            moon_distance=Angle(
                                degrees=constraints['min_lunar_distance']
                            )
                        )
                        # We only want times when all targets are visible to keep things simple
                        if first_target:
                            first_target = False
                            target_intervals = Intervals(rs_interval)
                        else:
                            target_intervals = Intervals(rs_interval).intersect([target_intervals])
                    except MovingViolation:
                        pass
                intervals_by_site[site].extend(target_intervals.toTupleList())

            if request.get('id'):
                cache.set(cache_key, intervals_by_site[site], 86400 * 30)  # cache for 30 days
    return intervals_by_site


def get_filtered_rise_set_intervals_by_site(request_dict, site='', is_staff=False):
    intervals = {}
    site = site if site else request_dict['location'].get('site', '')
    only_schedulable = not (is_staff and ConfigDB.is_location_fully_set(request_dict.get('location', {})))
    telescope_details = configdb.get_telescopes_with_instrument_type_and_location(
        request_dict['configurations'][0]['instrument_type'],
        site,
        request_dict['location'].get('enclosure', ''),
        request_dict['location'].get('telescope', ''),
        only_schedulable
    )
    if not telescope_details:
        return intervals

    intervals_by_site = get_rise_set_intervals_by_site(request_dict, only_schedulable)
    intervalsets_by_telescope = intervals_by_site_to_intervalsets_by_telescope(
        intervals_by_site, telescope_details.keys()
    )
    filtered_intervalsets_by_telescope = filter_out_downtime_from_intervalsets(intervalsets_by_telescope)
    filtered_intervals_by_site = intervalsets_by_telescope_to_intervals_by_site(filtered_intervalsets_by_telescope)
    return filtered_intervals_by_site


def intervalsets_by_telescope_to_intervals_by_site(intervalsets_by_telescope: dict) -> dict:
    """Convert rise_sets ordered by telescope to rise_set ordered by site. Also convert from intervalset
        to datetime tuple lists per site.
    :param intervalsets_by_telescope:
    :return: intervals by site
    """
    intervals_by_site = defaultdict(Intervals)
    for telescope, intervalset in intervalsets_by_telescope.items():
        site = telescope.split('.')[2]
        intervals_by_site[site] = intervals_by_site[site].union([intervalset])

    return {site: intervalset.toTupleList() for site, intervalset in intervals_by_site.items()}


def intervals_by_site_to_intervalsets_by_telescope(intervals_by_site: dict, telescopes: list) -> dict:
    """Convert rise_set intervals ordered by site to be ordered by telescope

     `telescopes` must be telescope details for the request that the `intervals_by_site` were
     calculated for.

    Parameters:
        intervals_by_site: rise_set intervals ordered by site
        telescopes: Available telescope details for the request
    Returns:
        rise_set intervals ordered by telescope
    """
    intervalsets_by_telescope = {}
    for telescope in telescopes:
        if telescope not in intervalsets_by_telescope:
            site = telescope.split('.')[2]
            datetime_intervals = []
            for start, end in intervals_by_site[site]:
                datetime_intervals.append({'type': 'start', 'time': start})
                datetime_intervals.append({'type': 'end', 'time': end})
            intervalsets_by_telescope[telescope] = Intervals(datetime_intervals)
    return intervalsets_by_telescope


def filter_out_downtime_from_intervalsets(intervalsets_by_telescope: dict) -> dict:
    """Remove downtime intervals.

    Parameters:
        intervalsets_by_telescope: rise_set intervals by telescope
    Returns:
        rise_set intervals by telescope with downtimes filtered out
    """
    downtime_intervals = DowntimeDB.get_downtime_intervals()
    filtered_intervalsets_by_telescope = {}
    for telescope in intervalsets_by_telescope.keys():
        if telescope not in downtime_intervals:
            filtered_intervalsets_by_telescope[telescope] = intervalsets_by_telescope[telescope]
        else:
            filtered_intervalsets_by_telescope[telescope] = intervalsets_by_telescope[telescope].subtract(
                downtime_intervals[telescope]
            )
    return filtered_intervalsets_by_telescope


def get_proper_motion(target_dict):
    # The proper motion fields are sometimes not present in HOUR_ANGLE targets
    pm = {'pmra': None, 'pmdec': None}
    if 'proper_motion_ra' in target_dict and target_dict['proper_motion_ra'] is not None:
        pm['pmra'] = ProperMotion(
            Angle(
                degrees=(target_dict['proper_motion_ra'] / 1000.0 / cos(radians(target_dict['dec']))) / 3600.0,
                units='arc'
            ),
            time='year'
        )
    if 'proper_motion_dec' in target_dict and target_dict['proper_motion_dec'] is not None:
        pm['pmdec'] = ProperMotion(
            Angle(
                degrees=(target_dict['proper_motion_dec'] / 1000.0) / 3600.0,
                units='arc'
            ),
            time='year'
        )
    return pm


def get_rise_set_target(target_dict):
    # This is a hack to protect against poorly formatted or empty targets that are submitted directly.
    # TODO: Remove this check when target models are updated to handle when there is no target
    if (
            'type' not in target_dict
            or target_dict['type'].upper() not in TARGET_TYPE_HELPER_MAP
            or not TARGET_TYPE_HELPER_MAP[target_dict['type'].upper()](target_dict).is_valid()
    ):
        return make_hour_angle_target(
            hour_angle=Angle(degrees=0),
            dec=Angle(degrees=0),
        )
    if target_dict['type'] in ['ICRS', 'HOUR_ANGLE']:
        pm = get_proper_motion(target_dict)
        if target_dict['type'] == 'ICRS':
            return make_ra_dec_target(
                ra=Angle(degrees=target_dict['ra']),
                dec=Angle(degrees=target_dict['dec']),
                ra_proper_motion=pm['pmra'],
                dec_proper_motion=pm['pmdec'],
                parallax=target_dict['parallax'],
                rad_vel=0.0,
                epoch=target_dict['epoch']
            )
        elif target_dict['type'] == 'HOUR_ANGLE':
            return make_hour_angle_target(
                hour_angle=Angle(degrees=target_dict['hour_angle']),
                dec=Angle(degrees=target_dict['dec']),
                ra_proper_motion=pm['pmra'],
                dec_proper_motion=pm['pmdec'],
                parallax=target_dict['parallax'],
                epoch=target_dict['epoch']
            )
    elif target_dict['type'] == 'SATELLITE':
        return make_satellite_target(
            alt=target_dict['altitude'],
            az=target_dict['azimuth'],
            diff_alt_rate=target_dict['diff_altitude_rate'],
            diff_az_rate=target_dict['diff_azimuth_rate'],
            diff_alt_accel=target_dict['diff_altitude_acceleration'],
            diff_az_accel=target_dict['diff_azimuth_acceleration'],
            diff_epoch_rate=target_dict['diff_epoch']
        )
    elif target_dict['type'] == 'ORBITAL_ELEMENTS':
        if target_dict['scheme'] == 'MPC_MINOR_PLANET':
            return make_minor_planet_target(
                target_type=target_dict['scheme'],
                epoch=target_dict['epochofel'],
                inclination=target_dict['orbinc'],
                long_node=target_dict['longascnode'],
                arg_perihelion=target_dict['argofperih'],
                semi_axis=target_dict['meandist'],
                eccentricity=target_dict['eccentricity'],
                mean_anomaly=target_dict['meananom']
            )
        elif target_dict['scheme'] == 'MPC_COMET':
            return make_comet_target(
                target_type=target_dict['scheme'],
                epoch=target_dict['epochofel'],
                epochofperih=target_dict['epochofperih'],
                inclination=target_dict['orbinc'],
                long_node=target_dict['longascnode'],
                arg_perihelion=target_dict['argofperih'],
                perihdist=target_dict['perihdist'],
                eccentricity=target_dict['eccentricity'],
            )
        elif target_dict['scheme'] == 'JPL_MAJOR_PLANET':
            return make_major_planet_target(
                target_type=target_dict['scheme'],
                epochofel=target_dict['epochofel'],
                inclination=target_dict['orbinc'],
                long_node=target_dict['longascnode'],
                arg_perihelion=target_dict['argofperih'],
                semi_axis=target_dict['meandist'],
                eccentricity=target_dict['eccentricity'],
                mean_anomaly=target_dict['meananom'],
                dailymot=target_dict['dailymot']
            )
        else:
            raise TypeError('Invalid scheme ' + target_dict['scheme'])
    else:
        raise TypeError('Invalid target type' + target_dict['type'])


def get_distance_between(rs_target_1: dict, rs_target_2: dict, start_time: datetime) -> Angle:
    """Get the angular distance between two ICRS rise_set targets as a rise_set Angle.

    Parameters:
        rs_target_1: First ICRS rise_set target
        rs_target_2: Second ICRS rise_set target
        start_time: Time of computation
    Returns:
         rise_set Angle
    """
    start_tdb = date_to_tdb(start_time)
    apparent_ra_1, apparent_dec_1 = mean_to_apparent(rs_target_1, start_tdb)
    apparent_ra_2, apparent_dec_2 = mean_to_apparent(rs_target_2, start_tdb)
    return angular_distance_between(apparent_ra_1, apparent_dec_1, apparent_ra_2, apparent_dec_2)


def get_rise_set_site(site_detail):
    return {
        'latitude': Angle(degrees=site_detail['latitude']),
        'longitude': Angle(degrees=site_detail['longitude']),
        'horizon': Angle(degrees=site_detail['horizon']),
        'ha_limit_neg': Angle(degrees=site_detail['ha_limit_neg'] * HOURS_PER_DEGREES),
        'ha_limit_pos': Angle(degrees=site_detail['ha_limit_pos'] * HOURS_PER_DEGREES)
    }


def get_rise_set_visibility(rise_set_site, start, end, site_detail):
    return Visibility(
        site=rise_set_site,
        start_date=start,
        end_date=end,
        horizon=site_detail['horizon'],
        ha_limit_neg=site_detail['ha_limit_neg'],
        ha_limit_pos=site_detail['ha_limit_pos'],
        zenith_blind_spot=site_detail['zenith_blind_spot'],
        twilight='nautical'
    )


def get_site_rise_set_intervals(start, end, site_code):
    site_details = configdb.get_sites_with_instrument_type_and_location(site_code=site_code)
    if site_code in site_details:
        site_detail = site_details[site_code]
        rise_set_site = get_rise_set_site(site_detail)
        v = get_rise_set_visibility(rise_set_site, start, end, site_detail)

        return v.get_dark_intervals()

    return []
