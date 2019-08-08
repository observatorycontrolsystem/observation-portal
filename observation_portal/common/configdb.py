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
        self, instrument_type: str = '', site_code: str = '', enclosure_code: str = '', telescope_code: str = ''
    ) -> dict:
        """Get the location details for each site for which a resource exists.

        The results are filtered by any arguments passed in. If no arguments are provided,
        get location details for all sites.

        Parameters:
            instrument_type: Instrument type
            site_code: 3-letter site code
            enclosure_code: 4-letter enclosure code
            telescope_code: 4-letter telescope code
        Returns:
            Site location details
        """
        telescope_details = self.get_telescopes_with_instrument_type_and_location(
            instrument_type, site_code, enclosure_code, telescope_code
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

    def get_instrument_type_tuples(self):
        instrument_types = set()
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        instrument_types.add(instrument['science_camera']['camera_type']['code'].upper())
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
            for config_type in instrument['science_camera']['camera_type']['configuration_types']:
                configuration_types.add(config_type.upper())
        return [(config_type, config_type) for config_type in configuration_types]

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
                                            instrument['science_camera']['camera_type']['code'].lower()
                                        )
        return {'names': instrument_names, 'types': instrument_types}

    def get_telescopes_with_instrument_type_and_location(
            self, instrument_type='', site_code='', enclosure_code='', telescope_code=''
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
                                    if self.is_schedulable(instrument):
                                        camera_type = instrument['science_camera']['camera_type']['code']
                                        if not instrument_type or instrument_type.upper() == camera_type.upper():
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

    def is_valid_instrument_type(self, instrument_type):
        for site in self.get_site_data():
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        if (
                                instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper()
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
                            instruments.append(instrument)

        return instruments

    def get_instrument_types_per_telescope(self, only_schedulable: bool = False) -> dict:
        """Get a set of available instrument types per telescope.

        Parameters:
            only_schedulable: Whether to only include schedulable telescopes
        Returns:
            Available instrument types
        """
        if only_schedulable:
            exclude_states = ['DISABLED', 'MANUAL', 'COMMISSIONING', 'STANDBY']
        telescope_instrument_types = {}
        for instrument in self.get_instruments(exclude_states=exclude_states):
            if instrument['telescope_key'] not in telescope_instrument_types:
                telescope_instrument_types[instrument['telescope_key']] = []
            instrument_type = instrument['science_camera']['camera_type']['code'].upper()
            if instrument_type not in telescope_instrument_types[instrument['telescope_key']]:
                telescope_instrument_types[instrument['telescope_key']].append(instrument_type)
        return telescope_instrument_types

    def get_instrument_names(
            self, instrument_type: str, site_code: str, enclosure_code: str, telescope_code: str
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
                    and instrument['science_camera']['camera_type']['code'].lower() == instrument_type.lower()
            ):
                instrument_names.add(instrument['science_camera']['code'].lower())
        return instrument_names

    def get_instrument_types_per_telescope_class(self, exclude_states=None) -> dict:
        """Get a set of instrument types.

        Instrument types are returned by telescope class (0m4, 1m0, etc...)

        Parameters:
            only_schedulable: Whether to only include schedulable telescopes
        Returns:
            Instrument types separated by class
        """
        telescope_instrument_types = {}
        for instrument in self.get_instruments(exclude_states=exclude_states):
            tel_code = instrument['telescope_key'].telescope[:3]
            if tel_code not in telescope_instrument_types:
                telescope_instrument_types[tel_code] = set()
            telescope_instrument_types[tel_code].add(instrument['science_camera']['camera_type']['code'].upper())
        return telescope_instrument_types

    def get_telescopes_per_instrument_type(self, instrument_type: str, only_schedulable: bool = False) -> set:
        """Get a set of telescope keys.

        Parameters:
            instrument_type: Telescopes must have this instrument type available
            only_schedulable: Whether to only include schedulable telescopes
        Returns:
             Telescope keys
        """
        if only_schedulable:
            exclude_states = ['DISABLED', 'MANUAL', 'COMMISSIONING', 'STANDBY']
        instrument_telescopes = set()
        for instrument in self.get_instruments(exclude_states=exclude_states):
            if instrument['science_camera']['camera_type']['code'].upper() == instrument_type:
                instrument_telescopes.add(instrument['telescope_key'])
        return instrument_telescopes

    def get_configuration_types(self, instrument_type):
        configuration_types = set()
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                configuration_types.update(instrument['science_camera']['camera_type']['configuration_types'])
        return configuration_types

    def get_optical_elements(self, instrument_type: str) -> dict:
        """Get the available optical elements.

        Parameters:
            instrument_type: Instrument type for which to get the optical elements
        Returns:
             Available optical elements
        """
        optical_elements = defaultdict(list)
        optical_elements_tracker = defaultdict(set)
        for instrument in self.get_instruments(exclude_states=['DISABLED', ]):
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                for optical_element_group in instrument['science_camera']['optical_element_groups']:
                    for element in optical_element_group['optical_elements']:
                        if element['code'] not in optical_elements_tracker[optical_element_group['type']]:
                            optical_elements_tracker[optical_element_group['type']].add(element['code'])
                            optical_elements[optical_element_group['type']].append(element)
        return optical_elements

    def get_modes_by_type(self, instrument_type: str, mode_type: str = '') -> dict:
        """Get the set of available modes.

        Parameters:
            instrument_type: Instrument type for which to retrieve the modes
            mode_type: Mode type to restrict to
        Returns:
            Available modes by type
        """
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                if not mode_type:
                    return {
                        mode_group['type']: mode_group
                        for mode_group in instrument['science_camera']['camera_type']['mode_types']
                    }
                else:
                    for mode_group in instrument['science_camera']['camera_type']['mode_types']:
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
                if mode['params'].get('binning', -1) == binning:
                    return mode

        raise ConfigDBException(f'No readout mode found with binning {binning} for instrument type {instrument_type}')

    def get_default_modes_by_type(self, instrument_type: str, mode_type: str = '') -> dict:
        """Get the default mode of each available mode_type.

        Parameters:
            instrument_type: Instrument type for which to get the default mode
            mode_type: Mode type to restrict to, empty string is no restriction
        Returns:
             Default modes
        """
        modes = self.get_modes_by_type(instrument_type, mode_type)
        default_modes = {}
        for m_type, m_set in modes.items():
            for mode in m_set['modes']:
                if 'default' in m_set and mode['code'] == m_set['default']:
                    default_modes[m_type] = mode
                    break
        return default_modes

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
            if 'binning' in mode['params']:
                available_binnings.add(mode['params']['binning'])
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
            if readout_modes['readout']['default'] == mode['code'] and 'binning' in mode['params']:
                return mode['params']['binning']
        return None

    def get_default_acceptability_threshold(self, instrument_type):
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                return instrument['science_camera']['camera_type']['default_acceptability_threshold']

    def get_max_rois(self, instrument_type):
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                return instrument['science_camera']['camera_type']['max_rois']

    def get_ccd_size(self, instrument_type):
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                return {
                    'x': instrument['science_camera']['camera_type']['pixels_x'],
                    'y': instrument['science_camera']['camera_type']['pixels_y']
                }

    def get_instrument_type_full_name(self, instrument_type):
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                return instrument['science_camera']['camera_type']['name']
        return instrument_type

    def get_instrument_type_telescope_class(self, instrument_type):
        for instrument in self.get_instruments():
            if instrument_type.upper() == instrument['science_camera']['camera_type']['code'].upper():
                return instrument['__str__'].split('.')[2][0:3]
        return instrument_type[0:3]

    def get_active_instrument_types(self, location: dict) -> set:
        """Get the available instrument_types.

        Parameters:
            location: Dictionary of the location, with class, site, enclosure, and telescope fields
        Returns:
            Available instrument_types (i.e. 1M0-SCICAM-SBIG, etc.)
        """
        instrument_types = set()
        for instrument in self.get_instruments(exclude_states=['DISABLED', 'MANUAL', 'COMMISSIONING', 'STANDBY']):
            split_string = instrument['__str__'].lower().split('.')
            if (location.get('site', '').lower() in split_string[0]
                    and location.get('enclosure', '').lower() in split_string[1]
                    and location.get('telescope_class', '').lower() in split_string[2]
                    and location.get('telescope', '').lower() in split_string[2]):
                instrument_types.add(instrument['science_camera']['camera_type']['code'].upper())
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
                elif instrument['science_camera']['camera_type']['allow_self_guiding'] and guide_camera_name.lower() == instrument_name.lower():
                    return True
        return False

    def get_exposure_overhead(self, instrument_type, binning, readout_mode=''):
        # using the instrument type, build an instrument with the correct configdb parameters
        for instrument in self.get_instruments():
            if instrument['science_camera']['camera_type']['code'].upper() == instrument_type.upper():
                camera_type = instrument['science_camera']['camera_type']

        modes_by_type = self.get_modes_by_type(instrument_type, mode_type='readout')
        if 'readout' in modes_by_type:
            default_mode = {}
            for mode in modes_by_type['readout']['modes']:
                if mode['code'] == modes_by_type['readout'].get('default'):
                    default_mode = mode
                if readout_mode and readout_mode.lower() != mode['code'].lower():
                    continue
                if 'binning' in mode['params'] and mode['params']['binning'] == binning:
                    return mode['overhead'] + camera_type['fixed_overhead_per_exposure']
            # if the binning is not found, return the default binning (Added to support legacy 2x2 Sinistro obs)
            return default_mode['overhead'] + camera_type['fixed_overhead_per_exposure']

        raise ConfigDBException(f'Instrument type {instrument_type} not found in configdb.')

    def get_request_overheads(self, instrument_type: str) -> dict:
        """Get the set of overheads needed to compute the duration of a request.

        This assumes a fixed set of overheads per instrument_type, but in the future these could split off
        further by specific telescopes or instruments.

        Parameters:
            instrument_type: Instrument type for which to get overheads
        Raises:
            ConfigDBException: If the instrument type is not found
        Returns:
            Request overheads
        """
        site_data = self.get_site_data()
        modes_by_type = self.get_modes_by_type(instrument_type)
        for site in site_data:
            for enclosure in site['enclosure_set']:
                for telescope in enclosure['telescope_set']:
                    for instrument in telescope['instrument_set']:
                        camera_type = instrument['science_camera']['camera_type']
                        if camera_type['code'].upper() == instrument_type.upper():
                            return {
                                'instrument_change_overhead': telescope['instrument_change_overhead'],
                                'slew_rate': telescope['slew_rate'],
                                'minimum_slew_overhead': telescope['minimum_slew_overhead'],
                                'maximum_slew_overhead': telescope.get('maximum_slew_overhead', 0.0),
                                'config_change_overhead': camera_type['config_change_time'],
                                'default_acquisition_exposure_time': camera_type['acquire_exposure_time'],
                                'acquisition_overheads': {
                                    am['code']: am['overhead']
                                    for am in modes_by_type['acquisition']['modes']
                                } if 'acquisition' in modes_by_type else {},
                                'guiding_overheads': {
                                    gm['code']: gm['overhead']
                                    for gm in modes_by_type['guiding']['modes']
                                } if 'guiding' in modes_by_type else {},
                                'front_padding': camera_type['front_padding'],
                                'optical_element_change_overheads': {
                                    oeg['type']: oeg['element_change_overhead']
                                    for oeg in instrument['science_camera']['optical_element_groups']
                                }
                            }
        raise ConfigDBException(f'Instrument type {instrument_type} not found in configdb.')

    @staticmethod
    def is_spectrograph(instrument_type):
        return instrument_type.upper() in ['2M0-FLOYDS-SCICAM', '0M8-NRES-SCICAM', '1M0-NRES-SCICAM',
                                           '1M0-NRES-COMMISSIONING', 'SOAR_GHTS_REDCAM']

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


configdb = ConfigDB()
