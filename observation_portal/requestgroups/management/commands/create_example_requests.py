from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from datetime import timedelta
import logging
import sys
import random

from rise_set.angle import Angle
from rise_set.exceptions import MovingViolation

from observation_portal.requestgroups.models import (
    RequestGroup, Request, Configuration, InstrumentConfig, Target, Window,
    AcquisitionConfig, GuidingConfig, Location, Constraints
)
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.proposals.models import Proposal
from observation_portal.common.configdb import configdb
from observation_portal.common.rise_set_utils import (get_rise_set_visibility, get_rise_set_target, get_rise_set_site,
                                                      get_largest_interval, get_rise_set_intervals_by_site)


logger = logging.getLogger()

base_requestgroup = {
    'operator': 'SINGLE',
    'ipp_value': 1.0,
}

base_constraints = {
    'max_airmass': 2.0,
    'min_lunar_distance': 0.0,
}

base_instrument_config = {
    'exposure_time': 100.0,
    'exposure_count': 2
}

TARGET_LIST = [
    {
        'name': 'm53',
        'type': 'ICRS',
        'ra': 351.2,
        'dec': 61.593,
        'proper_motion_ra': -1.938,
        'proper_motion_dec': -1.131,
        "epoch": 2000,
        'parallax': 0.596
    },
    {
        "name": "m23",
        "type": "ICRS",
        "ra": 269.267,
        "dec": -18.985,
        "proper_motion_ra": 1.18,
        "proper_motion_dec": -1.39,
        "epoch": 2000,
        "parallax": 1.354
    },
    {
        "name": "m1",
        "type": "ICRS",
        "ra": 83.63308,
        "dec": 22.0145,
        "proper_motion_ra": 0,
        "proper_motion_dec": 0,
        "epoch": 2000,
        "parallax": 0.0
    },
    {
        "name": "m76",
        "type": "ICRS",
        "ra": 25.5819186282012,
        "dec": 51.5754314258261,
        "proper_motion_ra": -0.254,
        "proper_motion_dec": -4.165,
        "epoch": 2000,
        "parallax": 0.0
    },
    {
        "name": "m41",
        "type": "ICRS",
        "ra": 101.504,
        "dec": -20.757,
        "proper_motion_ra": -3.99,
        "proper_motion_dec": -1.16,
        "epoch": 2000,
        "parallax": 1.36
    }
]


class Command(BaseCommand):
    help = 'Populates the DB with a set of example requests'

    def add_arguments(self, parser):
        parser.add_argument('-p', '--proposal', type=str,
                            help='Proposal code to use for submitted requests. The proposal must have time allocated.')
        parser.add_argument('-s', '--submitter', type=str,
                            help='The username of the user submitting the example requests')

    def _instrument_defaults(self, instrument_type):
        '''Get a set of default values for optical elements and modes for an instrument'''
        modes = configdb.get_modes_by_type(instrument_type)
        optical_elements = configdb.get_optical_elements(instrument_type)
        defaults = {
            'optical_elements': {}
        }
        for oe_type, elements in optical_elements.items():
            for element in elements:
                if element['default']:
                    defaults['optical_elements'][oe_type[:-1]] = element['code']
        for mode_type, mode_group in modes.items():
            defaults[mode_type] = mode_group.get('default', '')

        return defaults

    def _get_observation_details(self, duration, instrument_type, intervals_by_site):
        for site, intervals in intervals_by_site.items():
            for interval in intervals:
                interval_duration = interval[1] - interval[0]
                # Just choose the midpoint of the first interval that fits the request
                if interval_duration > duration:
                    telescope_details = configdb.get_telescopes_with_instrument_type_and_location(instrument_type, site)
                    tel_code = list(telescope_details.keys())[0]
                    observation_details = {
                        'site': site,
                        'enclosure': tel_code.split('.')[1],
                        'telescope': tel_code.split('.')[0],
                        'start': interval[0] + interval_duration / 2.0 - duration / 2.0,
                        'end': interval[0] + interval_duration / 2.0 + duration / 2.0
                    }
                    return observation_details
        return {}

    def _visible_targets(self, instrument_type, windows):
        '''Return a list of targets that are currently visible in the window'''
        site_details = configdb.get_sites_with_instrument_type_and_location(instrument_type)
        visible_targets = []
        for target in TARGET_LIST:
            intervals_by_site = {}
            for site in site_details:
                rise_set_site = get_rise_set_site(site_details[site])
                rise_set_target = get_rise_set_target(target)
                intervals_by_site[site] = []
                for window in windows:
                    visibility = get_rise_set_visibility(rise_set_site, window['start'], window['end'], site_details[site])
                    try:
                        intervals_by_site[site].extend(visibility.get_observable_intervals(
                            rise_set_target,
                            airmass=2.0,
                            moon_distance=Angle(degrees=0.0)
                        ))
                    except MovingViolation:
                        pass
            largest_interval = get_largest_interval(intervals_by_site)
            if largest_interval > timedelta(minutes=15):
                visible_targets.append(target)
        return visible_targets

    def _create_observations(self, instrument_type, request_group):
        '''Create an observation for the given requestgroup'''
        for request in request_group.requests.all():
            if request.state != 'CANCELED':
                request_dict = request.as_dict()
                intervals_by_site = get_rise_set_intervals_by_site(request_dict, only_schedulable=True)
                observation_details = self._get_observation_details(
                    timedelta(seconds=request.duration), instrument_type, intervals_by_site
                )
                if observation_details:
                    now = timezone.now()
                    if observation_details['end'] < now:
                        if request_group.state == 'WINDOW_EXPIRED':
                            observation_details['state'] = 'FAILED'
                        elif request_group.state == 'CANCELED':
                            observation_details['state'] = 'CANCELED'
                        else:
                            observation_details['state'] = 'COMPLETED'
                    else:
                        observation_details['state'] = 'PENDING'
                    observation = Observation.objects.create(
                        request=request,
                        **observation_details
                    )
                    instrument_name = list(configdb.get_instrument_names(
                        instrument_type, observation_details['site'],
                        observation_details['enclosure'], observation_details['telescope']
                    ))[0]
                    for configuration in request.configurations.all():            
                        state = observation_details['state'] if observation_details['state'] != 'CANCELED' else 'PENDING'
                        configuration_status = ConfigurationStatus.objects.create(
                            configuration=configuration,
                            observation=observation,
                            state=state,
                            instrument_name=instrument_name,
                            guide_camera_name=instrument_name,
                        )
                        instrument_config = configuration.instrument_configs.first()
                        reason = ''
                        time_completed = instrument_config.exposure_time * instrument_config.exposure_count
                        if state == 'FAILED':
                            time_completed /= 2.0
                            reason = 'Observation failed for XYZ reason'
                        if state != 'PENDING':
                            Summary.objects.create(
                                configuration_status=configuration_status,
                                start=observation_details['start'],
                                end=observation_details['end'],
                                state=state,
                                reason=reason,
                                time_completed=time_completed
                            )

    def _create_requestgroups(self, name_base, instrument_type, proposal, submitter, windows):
        '''Create a set of requestgroups given the set of parameters'''
        states = ['CANCELED']
        if windows[0]['end'] > timezone.now():
            states.append('PENDING')
        else:
            states.append('COMPLETED')
            states.append('WINDOW_EXPIRED')
        observation_types = ['NORMAL', 'TIME_CRITICAL', 'RAPID_RESPONSE']
        visible_targets = self._visible_targets(instrument_type, windows)
        instrument_defaults = self._instrument_defaults(instrument_type)
        binning = configdb.get_default_binning(instrument_type)
        counter = 0
        for state in states:
            for observation_type in observation_types:
                target = random.choice(visible_targets)
                with transaction.atomic():
                    rg = RequestGroup.objects.create(
                        submitter=submitter,
                        proposal=proposal,
                        state=state,
                        observation_type=observation_type,
                        name=f'{name_base}-{counter}',
                        **base_requestgroup
                    )
                    r = Request.objects.create(
                        state=state,
                        request_group=rg
                    )

                    Location.objects.create(
                        request=r,
                        telescope_class=instrument_type[:3].lower()
                    )
                    for window in windows:
                        Window.objects.create(
                            request=r,
                            start=window['start'],
                            end=window['end']
                        )
                    configuration = Configuration.objects.create(
                        request=r,
                        instrument_type=instrument_type,
                        type='EXPOSE'
                    )

                    Target.objects.create(
                        configuration=configuration,
                        **target
                    )

                    Constraints.objects.create(
                        configuration=configuration,
                        **base_constraints
                    )

                    InstrumentConfig.objects.create(
                        configuration=configuration,
                        optical_elements=instrument_defaults['optical_elements'],
                        mode=instrument_defaults.get('readout', ''),
                        rotator_mode=instrument_defaults.get('rotator', ''),
                        bin_x=binning or 1,
                        bin_y=binning or 1,
                        **base_instrument_config
                    )

                    GuidingConfig.objects.create(
                        configuration=configuration,
                        mode=instrument_defaults.get('guiding', ''),
                        exposure_time=10
                    )

                    AcquisitionConfig.objects.create(
                        configuration=configuration,
                        mode=instrument_defaults.get('acquisition', ''),
                        exposure_time=10
                    )

                    rg.refresh_from_db()
                    self._create_observations(instrument_type, rg)
                    counter += 1

    def handle(self, *args, **options):
        try:
            proposal = Proposal.objects.get(id=options['proposal'])
        except Exception:
            logger.error(f"Proposal {options['proposal']} doesn't exist. Please create it first and try again.")
            sys.exit(1)

        try:
            user = User.objects.get(username=options['submitter'])
        except Exception:
            logger.error(f"Submitter username {options['submitter']} doesn't exist. Please submit a valid user account.")

        time_allocations = proposal.timeallocation_set.filter(semester=proposal.current_semester)
        if not time_allocations:
            logger.error(f"Proposal {options['proposal']} doesn't have any time allocations in the current semester")
            sys.exit(1)

        # Loop over all the current time allocations, which should include all available instrument types
        for time_allocation in time_allocations:
            instrument_type = time_allocation.instrument_type
            # Make a set of requests in the past, present, and future for each available instrument
            past_windows = [{
                'start': (timezone.now() - timedelta(days=15)),
                'end': (timezone.now() - timedelta(days=7))
            }]
            self._create_requestgroups('Past RequestGroup', instrument_type, proposal, user, past_windows)
            future_windows = [{
                'start': timezone.now(),
                'end': (timezone.now() + timedelta(days=7))
            }]
            self._create_requestgroups('Future RequestGroup', instrument_type, proposal, user, future_windows)

        logger.info(f"Created example requestgroups for proposal {options['proposal']} and submitter {options['submitter']}")
        sys.exit(0)
