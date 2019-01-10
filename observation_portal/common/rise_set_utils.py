from math import cos, radians
from datetime import timedelta
from time_intervals.intervals import Intervals
from rise_set.astrometry import make_ra_dec_target, make_satellite_target, make_minor_planet_target
from rise_set.astrometry import make_comet_target, make_major_planet_target
from rise_set.angle import Angle
from rise_set.rates import ProperMotion
from rise_set.visibility import Visibility
from rise_set.moving_objects import MovingViolation
from django.core.cache import cache

from observation_portal.common.configdb import configdb
from observation_portal.common.downtimedb import DowntimeDB

HOURS_PER_DEGREES = 15.0


def get_largest_interval(intervals):
    largest_interval = timedelta(seconds=0)
    for interval in intervals:
        largest_interval = max((interval[1] - interval[0]), largest_interval)

    return largest_interval


def get_rise_set_intervals_by_site(request_dict):
    ''' Computes or Retrieves from cache a dictionary of rise_set intervals by site for the request
    '''
    site_details = configdb.get_sites_with_instrument_type_and_location()
    intervals_by_site = {}
    for site in site_details:
        intervals_by_site[site] = None
        if request_dict.get('id'):
            cache_key = '{}.{}.rsi'.format(request_dict['id'], site)
            intervals_by_site[site] = cache.get(cache_key, None)

        if intervals_by_site[site] is None:
            # There is no cached rise_set intervals for this request and site, so recalculate it now
            intervals_by_site[site] = []
            rise_set_site = get_rise_set_site(site_details[site])
            rise_set_target = get_rise_set_target(request_dict['target'])
            for window in request_dict['windows']:
                visibility = get_rise_set_visibility(rise_set_site, window['start'], window['end'], site_details[site])
                try:
                    intervals_by_site[site].extend(
                        visibility.get_observable_intervals(
                            rise_set_target,
                            airmass=request_dict['constraints']['max_airmass'],
                            moon_distance=Angle(degrees=request_dict['constraints']['min_lunar_distance'])
                        )
                    )
                except MovingViolation:
                    pass
            if request_dict.get('id'):
                cache.set(cache_key, intervals_by_site[site], 86400 * 30) # cache for 30 days

    return intervals_by_site


def get_rise_set_intervals(request_dict, site=''):
    intervals = []
    site = site if site else request_dict['location'].get('site', '')
    telescope_details = configdb.get_telescopes_with_instrument_type_and_location(
            request_dict['molecules'][0]['instrument_name'],
            site,
            request_dict['location'].get('observatory', ''),
            request_dict['location'].get('telescope', '')
    )
    if not telescope_details:
        return intervals

    intervals_by_site = get_rise_set_intervals_by_site(request_dict)
    intervalsets_by_telescope = intervals_by_site_to_intervalsets_by_telescope(intervals_by_site, telescope_details.keys())
    filtered_intervalsets_by_telescope = filter_out_downtime_from_intervalsets(intervalsets_by_telescope)
    filtered_intervalset = Intervals().union(filtered_intervalsets_by_telescope.values())
    filtered_intervals = filtered_intervalset.toTupleList()

    return filtered_intervals


def intervals_by_site_to_intervalsets_by_telescope(intervals_by_site, telescopes):
    ''' Takes in a dictionary of rise_set intervals by sites and a dictionary of telescope details for the request.
        Returns a dictionary by telescopes of rise_set intervals for the request
    '''
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


def filter_out_downtime_from_intervalsets(intervalsets_by_telescope):
    ''' Takes a dictionary of rise_set intervalsets by telescopes and returns the same with downtime intervals removed
    '''
    downtime_intervals = DowntimeDB.get_downtime_intervals()
    filtered_intervalsets_by_telescope = {}
    for telescope in intervalsets_by_telescope.keys():
        if telescope not in downtime_intervals:
            filtered_intervalsets_by_telescope[telescope] = intervalsets_by_telescope[telescope]
        else:
            filtered_intervalsets_by_telescope[telescope] = intervalsets_by_telescope[telescope].subtract(downtime_intervals[telescope])

    return filtered_intervalsets_by_telescope


def get_rise_set_target(target_dict):
    if target_dict['type'] == 'SIDEREAL':
        pmra = (target_dict['proper_motion_ra'] / 1000.0 / cos(radians(target_dict['dec']))) / 3600.0
        pmdec = (target_dict['proper_motion_dec'] / 1000.0) / 3600.0
        return make_ra_dec_target(ra=Angle(degrees=target_dict['ra']),
                                  dec=Angle(degrees=target_dict['dec']),
                                  ra_proper_motion=ProperMotion(Angle(degrees=pmra, units='arc'), time='year'),
                                  dec_proper_motion=ProperMotion(Angle(degrees=pmdec, units='arc'), time='year'),
                                  parallax=target_dict['parallax'], rad_vel=0.0, epoch=target_dict['epoch'])

    elif target_dict['type'] == 'SATELLITE':
        return make_satellite_target(alt=target_dict['altitude'], az=target_dict['azimuth'],
                                     diff_alt_rate=target_dict['diff_pitch_rate'],
                                     diff_az_rate=target_dict['diff_roll_rate'],
                                     diff_alt_accel=target_dict['diff_pitch_acceleration'],
                                     diff_az_accel=target_dict['diff_roll_acceleration'],
                                     diff_epoch_rate=target_dict['diff_epoch_rate'])

    elif target_dict['type'] == 'NON_SIDEREAL':
        if target_dict['scheme'] == 'MPC_MINOR_PLANET':
            return make_minor_planet_target(target_type=target_dict['scheme'],
                                            epoch=target_dict['epochofel'],
                                            inclination=target_dict['orbinc'],
                                            long_node=target_dict['longascnode'],
                                            arg_perihelion=target_dict['argofperih'],
                                            semi_axis=target_dict['meandist'],
                                            eccentricity=target_dict['eccentricity'],
                                            mean_anomaly=target_dict['meananom']
                                            )
        elif target_dict['scheme'] == 'MPC_COMET':
            return make_comet_target(target_type=target_dict['scheme'],
                                     epoch=target_dict['epochofel'],
                                     epochofperih=target_dict['epochofperih'],
                                     inclination=target_dict['orbinc'],
                                     long_node=target_dict['longascnode'],
                                     arg_perihelion=target_dict['argofperih'],
                                     perihdist=target_dict['perihdist'],
                                     eccentricity=target_dict['eccentricity'],
                                     )
        elif target_dict['scheme'] == 'JPL_MAJOR_PLANET':
            return make_major_planet_target(target_type=target_dict['scheme'],
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
