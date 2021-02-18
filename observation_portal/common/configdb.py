import logging
from typing import Union
from collections import namedtuple, defaultdict

import requests
from django.core.cache import caches
from django.utils.translation import ugettext as _
from django.conf import settings

logger = logging.getLogger(__name__)


class ConfigDBException(Exception):
    """Raise on error retrieving or processing configuration data."""
    pass


class TelescopeKey(namedtuple('TelescopeKey', ['site', 'enclosure', 'telescope'])):
    """Generate the key of a telescope."""
    __slots__ = ()

    def __str__(self):
        return '.'.join(s for s in [self.site, self.enclosure, self.telescope] if s)


class ConfigDB(object):
    """Class to retrieve and process configuration data."""

    @staticmethod
    def _get_configdb_data(resource: str):
        """Return all configuration data.

        Return all data from ConfigDB at the given endpoint. Check first if the data is already cached, and
        if so, return that.

        Parameters:
            resource: ConfigDB endpoint
        Returns:
            Data retrieved
        """
        error_message = _((
            'ConfigDB connection is currently down, please wait a few minutes and try again. If this problem '
            'persists then please contact support.'
        ))
        data = caches['locmem'].get(resource)
        if not data:
            try:
                r = requests.get(settings.CONFIGDB_URL + f'/{resource}/')
                r.raise_for_status()
            except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
                msg = f'{e.__class__.__name__}: {error_message}'
                raise ConfigDBException(msg)
            try:
                data = r.json()['results']
            except KeyError:
                raise ConfigDBException(error_message)
            # Cache the results for 15 minutes.
            caches['locmem'].set(resource, data, 900)
        return data

    def get_site_data(self):
        """Return ConfigDB sites data."""
        return self._get_configdb_data('sites')

    def get_sites_with_instrument_type_and_location(
        self, instrument_type: str = '', site_code: str = '', enclosure_code: str = '', telescope_code: str = '',
        only_schedulable: bool = True
    ) -> dict:
        """Get the location details for each site for which a resource exists.

        The results are filtered by any arguments passed in. If no arguments are provided,
        get location details for all sites.

        Parameters:
            instrument_type: Instrument type
            site_code: 3-letter site code
            enclosure_code: 4-letter enclosure code
            telescope_code: 4-letter telescope code
            only_schedulable: whether to only include SCHEDULABLE instruments or all non-DISABLED
        Returns:
            Site location details
        """
        telescope_details = self.get_telescopes_with_instrument_type_and_location(
            instrument_type, site_code, enclosure_code, telescope_code, only_schedulable
        )
        site_details = {}
        for code in telescope_details.keys():
            site = code.split('.')[2]
            if site not in site_details:
                site_details[site] = telescope_details[code]
        return site_details

    def get_site_tuples(self, include_blank=False):
        site_data = self.get_site_data()
        sites = [(site['code'], site['code']) for site in site_data]
        if include_blank:
            sites.append(('', ''))
        return sites

    def get_enclosure_tuples(self, include_blank=False):
        enclosure_set = set()
        site_data = self.get_site_data()
        for site in site_data:
            for enclosure in site['enclosure_set']:
                enclosure_set.add(enclosure['code'])

        enclosures = [(enclosure, enclosure) for enclosure in enclosure_set]
        if include_blank:
            enclosures.append(('', ''))
        return enclosures

    def get_telescope_tuples(self, include_blank=False):
        telescope_set = set()
        site_data = self.get_site_data()
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    telescope_set.add(telescope['code'])

        telescopes = [(telescope, telescope) for telescope in telescope_set]
        if include_blank:
            telescopes.append(('', ''))
        return telescopes

    def get_telescope_class_tuples(self):
        telescope_classes = set()
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    telescope_classes.add(telescope['code'][:-1])
        return [(telescope_class, telescope_class) for telescope_class in telescope_classes]

    def get_telescope_name_tuples(self):
        telescope_names = set()
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    telescope_names.add(telescope['name'].strip().lower())
        return [(telescope_name, telescope_name) for telescope_name in telescope_names]

    def get_instrument_type_tuples(self):
        instrument_types = set()
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        instrument_types.add(instrument['instrument_type']['code'].upper())
        return [(instrument_type, instrument_type) for instrument_type in instrument_types]

    def get_instrument_name_tuples(self):
        instrument_names = set()
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        instrument_names.add(instrument['code'].lower())
        return [(instrument_name, instrument_name) for instrument_name in instrument_names]

    def get_configuration_type_tuples(self):
        configuration_types = set()
        for instrument in self.get_instruments():
            for config_type in instrument['instrument_type']['configuration_types']:
                configuration_types.add(config_type.upper())
        return [(config_type, config_type) for config_type in configuration_types]

    def get_raw_telescope_name(self, telescope_name):
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    if telescope['name'].strip().lower() == telescope_name.strip().lower():
                        return telescope['name'].strip()
        return telescope_name

    def get_instruments_at_location(self, site_code, enclosure_code, telescope_code, only_schedulable=False):
        instrument_names = set()
        instrument_types = set()
        for site in self.get_site_data():
            if site['code'].lower() == site_code.lower():
                for enclosure in site['enclosure_set']:
                    if enclosure['code'].lower() == enclosure_code.lower():
                        for telescope in enclosure['telescope_set']:
                            if telescope['code'].lower() == telescope_code.lower():
                                for instrument in telescope['instrument_set']:
                                    if (
                                            only_schedulable and self.is_schedulable(instrument)
                                            or (not only_schedulable and self.is_active(instrument))
                                    ):
                                        instrument_names.add(instrument['code'].lower())
                                        instrument_types.add(
                                            instrument['instrument_type']['code'].lower()
                                        )
        return {'names': instrument_names, 'types': instrument_types}

    def get_telescopes_with_instrument_type_and_location(
            self, instrument_type_code='', site_code='', enclosure_code='', telescope_code='', only_schedulable=True
    ):
        site_data = self.get_site_data()
        telescope_details = {}
        for site in site_data:
            if not site_code or site_code == site['code']:
                for enclosure in site['enclosure_set']:
                    if not enclosure_code or enclosure_code == enclosure['code']:
                        for telescope in enclosure['telescope_set']:
                            if not telescope_code or telescope_code == telescope['code']:
                                code = '.'.join([telescope['code'], enclosure['code'], site['code']])
                                for instrument in telescope['instrument_set']:
                                    if (self.is_schedulable(instrument) or
                                            (not only_schedulable and self.is_active(instrument))):
                                        instrument_type = instrument['instrument_type']['code']
                                        if not instrument_type_code or instrument_type_code.upper() == instrument_type.upper():
                                            if code not in telescope_details:
                                                telescope_details[code] = {
                                                    'latitude': telescope['lat'],
                                                    'longitude': telescope['long'],
                                                    'horizon': telescope['horizon'],
                                                    'altitude': site['elevation'],
                                                    'ha_limit_pos': telescope['ha_limit_pos'],
                                                    'ha_limit_neg': telescope['ha_limit_neg'],
                                                    'zenith_blind_spot': telescope['zenith_blind_spot']
                                                }
        return telescope_details

    def is_valid_instrument_type(self, instrument_type_code):
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        if (
                                instrument_type_code.upper() == instrument['instrument_type']['code'].upper()
                                and self.is_active(instrument)
                        ):
                            return True
        return False

    def is_valid_instrument(self, instrument_name):
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        if instrument_name.upper() == instrument['code'].upper() and self.is_active(instrument):
                            return True
        return False

    def get_instruments(self, exclude_states=None):
        if not exclude_states:
            exclude_states = []
        site_data = self.get_site_data()
        instruments = []
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        if instrument['state'].upper() not in exclude_states:
                            telescope_key = TelescopeKey(
                                site=site['code'],
                                enclosure=enclosure['code'],
                                telescope=telescope['code']
                            )
                            instrument['telescope_key'] = telescope_key
                            instrument['telescope_name'] = telescope['name'].strip().lower()
                            instruments.append(instrument)
        return instruments

    def get_instrument_types_per_telescope(self, location: dict = None, only_schedulable: bool = False) -> dict:
        """Get a set of available instrument types per telescope.

        Parameters:
            only_schedulable: Whether to only include schedulable telescopes
        Returns:
            Available instrument types
        """
        if not location:
            location = {}
        exclude_states = ['DISABLED']
        if only_schedulable:
            exclude_states = ['DISABLED', 'ENABLED', 'MANUAL', 'COMMISSIONING', 'STANDBY']
        telescope_instrument_types = {}
        for instrument in self.get_instruments(exclude_states=exclude_states):
            split_string = instrument['__str__'].lower().split('.')
            if (location.get('site', '').lower() in split_string[0]
                    and location.get('enclosure', '').lower() in split_string[1]
                    and location.get('telescope_class', '').lower() in split_string[2]
                    and location.get('telescope', '').lower() in split_string[2]):
                if instrument['telescope_key'] not in telescope_instrument_types:
                    telescope_instrument_types[instrument['telescope_key']] = []
                instrument_type_code = instrument['instrument_type']['code'].upper()
                if instrument_type_code not in telescope_instrument_types[instrument['telescope_key']]:
                    telescope_instrument_types[instrument['telescope_key']].append(instrument_type_code)
        return telescope_instrument_types

    def get_instrument_names(
            self, instrument_type_code: str, site_code: str, enclosure_code: str, telescope_code: str
    ) -> set:
        """Get a set of available instrument names.

        Parameters:
            instrument_type: Instrument type
            site_code: 3-letter site code
            enclosure_code: 4-letter enclosure
            telescope_code: 4-letter telescope code
        Returns:
            Available instrument names
        """
        instrument_names = set()
        for instrument in self.get_instruments(exclude_states=['DISABLED', ]):
            if (
                    instrument['telescope_key'].site.lower() == site_code.lower()
                    and instrument['telescope_key'].enclosure.lower() == enclosure_code.lower()
                    and instrument['telescope_key'].telescope.lower() == telescope_code.lower()
                    and instrument['instrument_type']['code'].lower() == instrument_type_code.lower()
            ):
                instrument_names.add(instrument['code'].lower())
        return instrument_names

    def get_telescope_name_by_instrument_types(self, exclude_states=None) -> dict:
        """Get a mapping of instrument type to telescope name.

        Telescope names that are returned are e.g. 1 meter, 2 meter, etc...

        Parameters:
            exclude_states: Instrument states to exclude
        Returns:
            Instrument types mapped to telescope names
        """
        instrument_types_to_telescope_name = {}
        for instrument in self.get_instruments(exclude_states=exclude_states):
            tel_name = instrument['telescope_name']
            instrument_types_to_telescope_name[instrument['instrument_type']['code'].upper()] = tel_name
        return instrument_types_to_telescope_name

    def get_telescopes_per_instrument_type(self, instrument_type_code: str, only_schedulable: bool = False) -> set:
        """Get a set of telescope keys.

        Parameters:
            instrument_type_code: Telescopes must have this instrument type available
            only_schedulable: Whether to only include schedulable telescopes
        Returns:
             Telescope keys
        """
        exclude_states = ['DISABLED']
        if only_schedulable:
            exclude_states = ['DISABLED', 'ENABLED', 'MANUAL', 'COMMISSIONING', 'STANDBY']
        instrument_telescopes = set()
        for instrument in self.get_instruments(exclude_states=exclude_states):
            if instrument['instrument_type']['code'].upper() == instrument_type_code:
                instrument_telescopes.add(instrument['telescope_key'])
        return instrument_telescopes

    def get_configuration_types(self, instrument_type_code):
        configuration_types = set()
        for instrument in self.get_instruments():
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                configuration_types.update(instrument['instrument_type']['configuration_types'])
        return configuration_types

    def get_optical_elements(self, instrument_type_code: str) -> dict:
        """Get the available optical elements.

        Parameters:
            instrument_type_code: Instrument type for which to get the optical elements
        Returns:
             Available optical elements
        """
        optical_elements = defaultdict(list)
        optical_elements_tracker = defaultdict(set)
        for instrument in self.get_instruments(exclude_states=['DISABLED', ]):
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                for science_camera in instrument['science_cameras']:
                    for optical_element_group in science_camera['optical_element_groups']:
                        for element in optical_element_group['optical_elements']:
                            if element['code'] not in optical_elements_tracker[optical_element_group['type']]:
                                if optical_element_group['default'].upper() == element['code'].upper():
                                    element['default'] = True
                                else:
                                    element['default'] = False
                                optical_elements_tracker[optical_element_group['type']].add(element['code'])
                                optical_elements[optical_element_group['type']].append(element)
        return optical_elements

    def get_modes_by_type(self, instrument_type_code: str, mode_type: str = '') -> dict:
        """Get the set of available modes.

        Parameters:
            instrument_type_code: Instrument type for which to retrieve the modes
            mode_type: Mode type to restrict to
        Returns:
            Available modes by type
        """
        for instrument in self.get_instruments():
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                if not mode_type:
                    return {
                        mode_group['type']: mode_group
                        for mode_group in instrument['instrument_type']['mode_types']
                    }
                else:
                    for mode_group in instrument['instrument_type']['mode_types']:
                        if mode_group['type'] == mode_type:
                            return {mode_type: mode_group}
        return {}

    def get_mode_with_code(self, instrument_type, code, mode_type=''):
        modes_by_type = self.get_modes_by_type(instrument_type, mode_type)
        for _, mode_group in modes_by_type.items():
            for mode in mode_group['modes']:
                if mode['code'].lower() == code.lower():
                    return mode

        raise ConfigDBException(f'No mode named {code} found for instrument type {instrument_type}')

    def get_readout_mode_with_binning(self, instrument_type, binning):
        readout_modes = self.get_modes_by_type(instrument_type, 'readout')
        if readout_modes:
            modes = sorted(
                readout_modes['readout']['modes'], key=lambda x: x['code'] == readout_modes['readout'].get('default'),
                reverse=True
            )  # Start with the default
            for mode in modes:
                if mode['validation_schema'].get('bin_x', {}).get('default', -1) == binning:
                    return mode

        raise ConfigDBException(f'No readout mode found with binning {binning} for instrument type {instrument_type}')

    def get_binnings(self, instrument_type: str) -> set:
        """Create a set of available binning modes.

        Parameters:
            instrument_type: Instrument type for which to create binning modes
        Returns:
             Available set of binnings
        Examples:
            >>> configdb.get_binnings('1M0-SCICAM-SBIG')
            1
        """
        available_binnings = set()
        readout_modes = self.get_modes_by_type(instrument_type, 'readout')
        for mode in readout_modes['readout']['modes'] if 'readout' in readout_modes else []:
            if 'bin_x' in mode['validation_schema'] and 'default' in mode['validation_schema']['bin_x']:
                available_binnings.add(mode['validation_schema']['bin_x']['default'])
        return available_binnings

    def get_default_binning(self, instrument_type: str) -> Union[None, int]:
        """Get the default binning.

        Parameters:
            instrument_type: Instrument type
        Returns:
             Default binning
        """
        readout_modes = self.get_modes_by_type(instrument_type, 'readout')
        for mode in readout_modes['readout']['modes'] if 'readout' in readout_modes else []:
            if (readout_modes['readout']['default'] == mode['code'] and 'bin_x' in mode['validation_schema']
                and 'default' in mode['validation_schema']['bin_x']):
                return mode['validation_schema']['bin_x']['default']
        return None

    def get_default_acceptability_threshold(self, instrument_type_code):
        for instrument in self.get_instruments():
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                return instrument['instrument_type']['default_acceptability_threshold']

    def get_max_rois(self, instrument_type_code):
        # TODO: This assumes the max ROIs for the science cameras of an instrument are the same
        for instrument in self.get_instruments():
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                return instrument['science_cameras'][0]['camera_type']['max_rois']

    def get_ccd_size(self, instrument_type_code):
        # TODO: This assumes the pixels for the science cameras of an instrument are the same
        for instrument in self.get_instruments():
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                return {
                    'x': instrument['science_cameras'][0]['camera_type']['pixels_x'],
                    'y': instrument['science_cameras'][0]['camera_type']['pixels_y']
                }

    def get_instrument_type_full_name(self, instrument_type_code):
        for instrument in self.get_instruments():
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                return instrument['instrument_type']['name']
        return instrument_type_code

    def get_instrument_type_telescope_class(self, instrument_type_code):
        for instrument in self.get_instruments():
            if instrument_type_code.upper() == instrument['instrument_type']['code'].upper():
                return instrument['__str__'].split('.')[2][0:3]
        return instrument_type_code[0:3]

    def get_instrument_types(self, location: dict, only_schedulable: bool = False) -> set:
        """Get the available instrument_types.

        Parameters:
            location: Dictionary of the location, with class, site, enclosure, and telescope fields
        Returns:
            Available instrument_types (i.e. 1M0-SCICAM-SBIG, etc.)
        """
        instrument_types = set()
        exclude_states = ['DISABLED']
        if only_schedulable:
            exclude_states = ['DISABLED', 'ENABLED', 'MANUAL', 'COMMISSIONING', 'STANDBY']
        for instrument in self.get_instruments(exclude_states=exclude_states):
            split_string = instrument['__str__'].lower().split('.')
            if (location.get('site', '').lower() in split_string[0]
                    and location.get('enclosure', '').lower() in split_string[1]
                    and location.get('telescope_class', '').lower() in split_string[2]
                    and location.get('telescope', '').lower() in split_string[2]):
                instrument_types.add(instrument['instrument_type']['code'].upper())
        return instrument_types

    def get_guider_for_instrument_name(self, instrument_name):
        instruments = self.get_instruments(exclude_states=['DISABLED'])
        for instrument in instruments:
            if instrument['code'].lower() == instrument_name.lower():
                return instrument['autoguider_camera']['code'].lower()
        raise ConfigDBException(_(f'Instrument not found: {instrument_name}'))

    def is_valid_guider_for_instrument_name(self, instrument_name, guide_camera_name):
        instruments = self.get_instruments(exclude_states=['DISABLED'])
        for instrument in instruments:
            if instrument['code'].upper() == instrument_name.upper():
                if instrument['autoguider_camera']['code'].lower() == guide_camera_name.lower():
                    return True
                elif instrument['instrument_type']['allow_self_guiding'] and guide_camera_name.lower() == instrument_name.lower():
                    return True
        return False

    def get_exposure_overhead(self, instrument_type_code, binning, readout_mode=''):
        # using the instrument type code, build an instrument with the correct configdb parameters
        for instrument in self.get_instruments():
            if instrument['instrument_type']['code'].upper() == instrument_type_code.upper():
                instrument_type = instrument['instrument_type']

        modes_by_type = self.get_modes_by_type(instrument_type_code, mode_type='readout')
        if 'readout' in modes_by_type:
            default_mode = {}
            for mode in modes_by_type['readout']['modes']:
                if mode['code'] == modes_by_type['readout'].get('default'):
                    default_mode = mode
                if readout_mode and readout_mode.lower() != mode['code'].lower():
                    continue
                if mode['validation_schema'].get('bin_x', {}).get('default', -1) == binning:
                    return mode['overhead'] + instrument_type['fixed_overhead_per_exposure']
            # if the binning is not found, return the default binning (Added to support legacy 2x2 Sinistro obs)
            return default_mode['overhead'] + instrument_type['fixed_overhead_per_exposure']

        raise ConfigDBException(f'Instruments of type {instrument_type_code} not found in configdb.')

    def get_request_overheads(self, instrument_type_code: str) -> dict:
        """Get the set of overheads needed to compute the duration of a request.

        This assumes a fixed set of overheads per instrument_type, but in the future these could split off
        further by specific telescopes or instruments.

        Parameters:
            instrument_type_code: Instrument type for which to get overheads
        Raises:
            ConfigDBException: If the instrument type is not found
        Returns:
            Request overheads
        """
        site_data = self.get_site_data()
        modes_by_type = self.get_modes_by_type(instrument_type_code)
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        instrument_type = instrument['instrument_type']
                        if instrument_type['code'].upper() == instrument_type_code.upper():
                            oe_overheads_by_type = {}
                            for science_camera in instrument['science_cameras']:
                                for oeg in science_camera['optical_element_groups']:
                                    oe_overheads_by_type[oeg['type']] = oeg['element_change_overhead']
                            return {
                                'instrument_change_overhead': telescope['instrument_change_overhead'],
                                'slew_rate': telescope['slew_rate'],
                                'minimum_slew_overhead': telescope['minimum_slew_overhead'],
                                'maximum_slew_overhead': telescope.get('maximum_slew_overhead', 0.0),
                                'config_change_overhead': instrument_type['config_change_time'],
                                'default_acquisition_exposure_time': instrument_type['acquire_exposure_time'],
                                'acquisition_overheads': {
                                    am['code']: am['overhead']
                                    for am in modes_by_type['acquisition']['modes']
                                } if 'acquisition' in modes_by_type else {},
                                'guiding_overheads': {
                                    gm['code']: gm['overhead']
                                    for gm in modes_by_type['guiding']['modes']
                                } if 'guiding' in modes_by_type else {},
                                'front_padding': instrument_type['front_padding'],
                                'optical_element_change_overheads': oe_overheads_by_type
                            }
        raise ConfigDBException(f'Instruments of type {instrument_type_code} not found in configdb.')

    @staticmethod
    def is_spectrograph(instrument_type):
        return instrument_type.upper() in ['2M0-FLOYDS-SCICAM', '0M8-NRES-SCICAM', '1M0-NRES-SCICAM',
                                           '1M0-NRES-COMMISSIONING', 'SOAR_GHTS_REDCAM', 'SOAR_GHTS_BLUECAM']

    @staticmethod
    def is_nres(instrument_type):
        return 'NRES' in instrument_type.upper()

    @staticmethod
    def is_floyds(instrument_type):
        return 'FLOYDS' in instrument_type.upper()

    @staticmethod
    def is_active(instrument: dict) -> bool:
        return instrument['state'].upper() != 'DISABLED'

    @staticmethod
    def is_schedulable(instrument: dict) -> bool:
        return instrument['state'] == 'SCHEDULABLE'

    @staticmethod
    def is_location_fully_set(location: dict) -> bool:
        for constraint in ['telescope_class', 'telescope', 'enclosure', 'site']:
            if constraint not in location or not location.get(constraint):
                return False
        return True


configdb = ConfigDB()
