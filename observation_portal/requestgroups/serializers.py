import json
import logging
from math import cos, sin, radians
from json import JSONDecodeError
from abc import ABC, abstractmethod

from cerberus import Validator
from rest_framework import serializers
from django.utils.translation import ugettext as _
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

from observation_portal.proposals.models import TimeAllocation, Membership
from observation_portal.requestgroups.models import (
    Request, Target, Window, RequestGroup, Location, Configuration, Constraints, InstrumentConfig,
    AcquisitionConfig, GuidingConfig, RegionOfInterest
)
from observation_portal.requestgroups.models import DraftRequestGroup
from observation_portal.common.state_changes import debit_ipp_time, TimeAllocationError, validate_ipp
from observation_portal.requestgroups.target_helpers import TARGET_TYPE_HELPER_MAP
from observation_portal.common.mixins import ExtraParamsFormatter
from observation_portal.common.configdb import configdb, ConfigDB
from observation_portal.requestgroups.duration_utils import (
    get_total_request_duration, get_requestgroup_duration, get_total_duration_dict,
    get_instrument_configuration_duration, get_semester_in
)
from datetime import timedelta
from observation_portal.common.rise_set_utils import get_filtered_rise_set_intervals_by_site, get_largest_interval

logger = logging.getLogger(__name__)


class ValidationHelper(ABC):
    """Base class for validating documents"""
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def validate(self, config_dict: dict) -> dict:
        pass

    def _validate_document(self, document: dict, validation_schema: dict) -> (Validator, dict):
        """
        Perform validation on a document using Cerberus validation schema
        :param document: Document to be validated
        :param validation_schema: Cerberus validation schema
        :return: Tuple of validator and a validated document
        """
        validator = Validator(validation_schema)
        validator.allow_unknown = True
        validated_config_dict = validator.validated(document) or document.copy()

        return validator, validated_config_dict

    def _cerberus_validation_error_to_str(self, validation_errors: dict) -> str:
        """
        Unpack and format Cerberus validation errors as a string
        :param validation_errors: Errors from validator (validator.errors)
        :return: String containing information about validation errors
        """
        error_str = ''
        for field, value in validation_errors.items():
            if (isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict)):
                error_str += f'{field}{{{self._cerberus_validation_error_to_str(value[0])}}}'
            else:
                error_str += f'{field} error: {", ".join(value)}, '

        error_str = error_str.rstrip(', ')
        return error_str


class InstrumentTypeValidationHelper(ValidationHelper):
    """Class to validate config based on InstrumentType in ConfigDB"""
    def __init__(self, instrument_type: str):
        self.instrument_type = instrument_type

    def validate(self, config_dict: dict) -> dict:
        """
        Using the validation_schema within the instrument type, validate the configuration
        :param config_dict: Configuration dictionary
        :return: Validated configuration
        :raises: ValidationError if config is invalid
        """
        instrument_type_dict = configdb.get_instrument_type_by_code(self.instrument_type)
        validation_schema = instrument_type_dict.get('validation_schema', {})
        validator, validated_config_dict = self._validate_document(config_dict, validation_schema)
        if validator.errors:
            raise serializers.ValidationError(_(
                f'Invalid configuration: {self._cerberus_validation_error_to_str(validator.errors)}'
            ))

        return validated_config_dict


class ModeValidationHelper(ValidationHelper):
    """Class used to validate GenericModes of different types defined in ConfigDB"""
    def __init__(self, mode_type: str, instrument_type: str, modes_group: dict, mode_key='mode', is_extra_param_mode=False):
        self._mode_type = mode_type.lower()
        self._instrument_type = instrument_type
        self._modes_group = modes_group
        self._mode_key = mode_key
        self.is_extra_param_mode = is_extra_param_mode

    def _get_mode_from_config_dict(self, config_dict: dict) -> str:
        if self.is_extra_param_mode:
            return config_dict.get('extra_params', {}).get(self._mode_key, '')
        return config_dict.get(self._mode_key, '')

    def _set_mode_in_config_dict(self, mode_value: str, config_dict: dict) -> dict:
        if self.is_extra_param_mode:
            if 'extra_params' not in config_dict:
                config_dict['extra_params'] = {}
            config_dict['extra_params'][self._mode_key] = mode_value
        else:
            config_dict[self._mode_key] = mode_value
        return config_dict

    def validate(self, config_dict) -> dict:
        """Validates the mode using its relevant configuration dict

        Returns a validated configuration dict with the mode filled in. If no mode is given in the input
        dict, a default mode will be filled in if availble. If the mode has a validation_schema, it will
        be used to validate the input dict. If any error is encountered during the process, A serializer
        ValidationError will be raised with the error.

        Args:
            config_dict (dict): A dictionary of input structure that this mode is a part of
        Returns:
            dict: A version of the input dictionary with defaults filled in based on the validation_schema
        Raises:
            serializers.ValidationError: If validation fails
        """
        mode_value = self._get_mode_from_config_dict(config_dict)
        if not mode_value:
            mode_value = self.get_default_mode()
            if not mode_value:
                return config_dict
        self.mode_exists_and_is_schedulable(mode_value)
        config_dict = self._set_mode_in_config_dict(mode_value, config_dict)
        mode = configdb.get_mode_with_code(self._instrument_type, mode_value, self._mode_type)
        validation_schema = mode.get('validation_schema', {})
        validator, validated_config_dict = self._validate_document(config_dict, validation_schema)
        if validator.errors:
            raise serializers.ValidationError(_(
                f'{self._mode_type.capitalize()} mode {mode_value} requirements are not met: {self._cerberus_validation_error_to_str(validator.errors)}'
            ))
        return validated_config_dict

    def mode_exists_and_is_schedulable(self, mode_value: str) -> bool:
        if self._modes_group and mode_value:
            for mode in self._modes_group['modes']:
                if mode['code'].lower() == mode_value.lower() and mode['schedulable']:
                    return True
            raise serializers.ValidationError(_(
                f'{self._mode_type.capitalize()} mode {mode_value} is not available for '
                f'instrument type {self._instrument_type}'
            ))
        return True

    def get_default_mode(self) -> str:
        """Choose a mode to set"""
        possible_modes = self._modes_group['modes']
        if len(possible_modes) == 1:
            # There is only one mode to choose from, so set that.
            return possible_modes[0]['code']
        elif self._modes_group.get('default'):
            return self._modes_group['default']
        elif len(possible_modes) > 1:
            # There are many possible modes, make the user choose.
            raise serializers.ValidationError(_(
                f'Must set a {self._mode_type} mode, choose '
                f'from {", ".join([mode["code"] for mode in self._modes_group["modes"]])}'
            ))
        return ''


class CadenceSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    period = serializers.FloatField(validators=[MinValueValidator(0.02)])
    jitter = serializers.FloatField(validators=[MinValueValidator(0.02)])

    def validate_end(self, value):
        if value < timezone.now():
            raise serializers.ValidationError('End time must be in the future')
        return value

    def validate(self, data):
        if data['start'] >= data['end']:
            msg = _("Cadence end '{}' cannot be earlier than cadence start '{}'.").format(data['start'], data['end'])
            raise serializers.ValidationError(msg)
        return data


class ConstraintsSerializer(serializers.ModelSerializer):
    max_airmass = serializers.FloatField(
        default=1.6, validators=[MinValueValidator(1.0), MaxValueValidator(25.0)]  # Duplicated in models.py
    )
    min_lunar_distance = serializers.FloatField(
        default=30.0, validators=[MinValueValidator(0.0), MaxValueValidator(180.0)]  # Duplicated in models.py
    )

    class Meta:
        model = Constraints
        exclude = Constraints.SERIALIZER_EXCLUDE


class RegionOfInterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegionOfInterest
        exclude = RegionOfInterest.SERIALIZER_EXCLUDE

    def validate(self, data):
        return data


class InstrumentConfigSerializer(ExtraParamsFormatter, serializers.ModelSerializer):
    rois = import_string(settings.SERIALIZERS['requestgroups']['RegionOfInterest'])(many=True, required=False)

    class Meta:
        model = InstrumentConfig
        exclude = InstrumentConfig.SERIALIZER_EXCLUDE

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data['rois']:
            del data['rois']
        return data


class AcquisitionConfigSerializer(ExtraParamsFormatter, serializers.ModelSerializer):
    class Meta:
        model = AcquisitionConfig
        exclude = AcquisitionConfig.SERIALIZER_EXCLUDE

    def validate(self, data):
        return data


class GuidingConfigSerializer(ExtraParamsFormatter, serializers.ModelSerializer):
    class Meta:
        model = GuidingConfig
        exclude = GuidingConfig.SERIALIZER_EXCLUDE

    def validate(self, data):
        return data


class TargetSerializer(ExtraParamsFormatter, serializers.ModelSerializer):
    class Meta:
        model = Target
        exclude = Target.SERIALIZER_EXCLUDE
        extra_kwargs = {
            'name': {'error_messages': {'blank': 'Please provide a name.'}}
        }

    def to_representation(self, instance):
        # Only return data for the specific target type
        data = super().to_representation(instance)
        target_helper = TARGET_TYPE_HELPER_MAP[data['type']](data)
        target_dict = {k: data.get(k) for k in target_helper.fields if data.get(k) is not None}
        target_dict['extra_params'] = data.get('extra_params', {})
        return target_dict

    def validate(self, data):
        target_helper = TARGET_TYPE_HELPER_MAP[data['type']](data)
        if target_helper.is_valid():
            data.update(target_helper.data)
        else:
            raise serializers.ValidationError(target_helper.error_dict)
        return data


class ConfigurationSerializer(ExtraParamsFormatter, serializers.ModelSerializer):
    fill_window = serializers.BooleanField(required=False, write_only=True)
    constraints = import_string(settings.SERIALIZERS['requestgroups']['Constraints'])()
    instrument_configs = import_string(settings.SERIALIZERS['requestgroups']['InstrumentConfig'])(many=True)
    acquisition_config = import_string(settings.SERIALIZERS['requestgroups']['AcquisitionConfig'])()
    guiding_config = import_string(settings.SERIALIZERS['requestgroups']['GuidingConfig'])()
    target = import_string(settings.SERIALIZERS['requestgroups']['Target'])()

    class Meta:
        model = Configuration
        exclude = Configuration.SERIALIZER_EXCLUDE
        read_only_fields = ('priority',)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Only return the repeat duration if its a REPEAT type configuration
        if 'REPEAT' not in data.get('type') and 'repeat_duration' in data:
            del data['repeat_duration']

        return data

    def validate_instrument_configs(self, value):
        if len(value) < 1:
            raise serializers.ValidationError(_('A configuration must have at least one instrument configuration'))
        return value

    def validate_instrument_type(self, value):
        is_staff = False
        request_context = self.context.get('request')
        if request_context:
            is_staff = request_context.user.is_staff
        if value and value not in configdb.get_instrument_type_codes({}, only_schedulable=(not is_staff)):
            raise serializers.ValidationError(
                _('Invalid instrument type {}. Valid instruments may include: {}').format(
                    value, ', '.join(configdb.get_instrument_type_codes({}, only_schedulable=(not is_staff)))
                )
            )
        return value

    def validate(self, data):
        # TODO: Validate the guiding optical elements on the guiding instrument types
        instrument_type = data['instrument_type']
        configuration_types = configdb.get_configuration_types(instrument_type)
        data['type'] = data['type'].upper()
        modes = configdb.get_modes_by_type(instrument_type)
        guiding_config = data['guiding_config']

        # Validate the guide mode
        guide_validation_helper = ModeValidationHelper('guiding', instrument_type, modes['guiding'])
        guiding_config = guide_validation_helper.validate(guiding_config)
        data['guiding_config'] = guiding_config

        # Validate the configuration type is available for the instrument requested
        if data['type'] not in configuration_types.keys():
            raise serializers.ValidationError(_(
                f'configuration type {data["type"]} is not valid for instrument type {instrument_type}'
            ))
        elif not configuration_types.get(data['type'], {}).get('schedulable', False):
            raise serializers.ValidationError(_(
                f'configuration type {data["type"]} is not schedulable for instrument type {instrument_type}'
            ))

        if configuration_types.get(data['type'], {}).get('force_acquisition_off', False):
            # These types of observations should only ever be set to guiding mode OFF, but the acquisition modes for
            # spectrographs won't necessarily have that mode. Force OFF here.
            data['acquisition_config']['mode'] = AcquisitionConfig.OFF
        else:
            # Validate acquire modes
            acquisition_config = data['acquisition_config']
            acquire_validation_helper = ModeValidationHelper('acquisition', instrument_type, modes['acquisition'])
            acquisition_config = acquire_validation_helper.validate(acquisition_config)
            if not acquisition_config.get('mode'):
                # Acquisition modes have an implicit default of OFF (we could just put this in all relevent validation_schema)
                acquisition_config['mode'] = AcquisitionConfig.OFF
            data['acquisition_config'] = acquisition_config

        available_optical_elements = configdb.get_optical_elements(instrument_type)
        for i, instrument_config in enumerate(data['instrument_configs']):
            # Validate the named readout mode if set, or set the default readout mode if left blank
            readout_mode = instrument_config.get('mode', '')
            readout_validation_helper = ModeValidationHelper('readout', instrument_type, modes['readout'])
            instrument_config = readout_validation_helper.validate(instrument_config)

            instrument_type_validation_helper = InstrumentTypeValidationHelper(instrument_type)
            instrument_config = instrument_type_validation_helper.validate(instrument_config)

            data['instrument_configs'][i] = instrument_config

            # Validate the rotator modes
            if 'rotator' in modes:
                rotator_mode_validation_helper = ModeValidationHelper('rotator', instrument_type, modes['rotator'],
                                                                      mode_key='rotator_mode')
                instrument_config = rotator_mode_validation_helper.validate(instrument_config)
                data['instrument_configs'][i] = instrument_config

            # Check that the optical elements specified are valid in configdb
            for oe_type, value in instrument_config.get('optical_elements', {}).items():
                plural_type = '{}s'.format(oe_type)
                if plural_type not in available_optical_elements:
                    raise serializers.ValidationError(_("optical_element of type {} is not available on {} instruments"
                                                        .format(oe_type, data['instrument_type'])))
                available_elements = {element['code'].lower(): element['code'] for element in available_optical_elements[plural_type]}
                if plural_type in available_optical_elements and value.lower() not in available_elements.keys():
                    raise serializers.ValidationError(_("optical element {} of type {} is not available".format(
                        value, oe_type
                    )))
                else:
                    instrument_config['optical_elements'][oe_type] = available_elements[value.lower()]

            # Also check that any optical element group in configdb is specified in the request unless this configuration type does
            # not require optical elements to be set. This will typically be the case for certain configuration types, like BIAS or DARK.
            if configuration_types.get(data['type'], {}).get('requires_optical_elements', True):
                for oe_type in available_optical_elements.keys():
                    singular_type = oe_type[:-1] if oe_type.endswith('s') else oe_type
                    if singular_type not in instrument_config.get('optical_elements', {}):
                        raise serializers.ValidationError(_(
                            f'Must set optical element of type {singular_type} for instrument type {instrument_type}'
                        ))
            # Validate any regions of interest
            if 'rois' in instrument_config:
                max_rois = configdb.get_max_rois(instrument_type)
                ccd_size = configdb.get_ccd_size(instrument_type)
                if len(instrument_config['rois']) > max_rois:
                    raise serializers.ValidationError(_(
                        f'Instrument type {instrument_type} supports up to {max_rois} regions of interest'
                    ))
                for roi in instrument_config['rois']:
                    if 'x1' not in roi and 'x2' not in roi and 'y1' not in roi and 'y2' not in roi:
                        raise serializers.ValidationError(_('Must submit at least one bound for a region of interest'))

                    if 'x1' not in roi:
                        roi['x1'] = 0
                    if 'x2' not in roi:
                        roi['x2'] = ccd_size['x']
                    if 'y1' not in roi:
                        roi['y1'] = 0
                    if 'y2' not in roi:
                        roi['y2'] = ccd_size['y']

                    if roi['x1'] >= roi['x2'] or roi['y1'] >= roi['y2']:
                        raise serializers.ValidationError(_(
                            'Region of interest pixels start must be less than pixels end'
                        ))

                    if roi['x2'] > ccd_size['x'] or roi['y2'] > ccd_size['y']:
                        raise serializers.ValidationError(_(
                            'Regions of interest for instrument type {} must be in range 0<=x<={} and 0<=y<={}'.format(
                                instrument_type, ccd_size['x'], ccd_size['y']
                            ))
                        )

            # Validate the exposure modes
            if 'exposure' in modes:
                exposure_mode_validation_helper = ModeValidationHelper(
                    'exposure', instrument_type, modes['exposure'], mode_key='exposure_mode', is_extra_param_mode=True
                )
                instrument_config = exposure_mode_validation_helper.validate(instrument_config)
                data['instrument_configs'][i] = instrument_config

        if data['type'] == 'SCRIPT':
            if (
                    'extra_params' not in data
                    or 'script_name' not in data['extra_params']
                    or not data['extra_params']['script_name']
            ):
                raise serializers.ValidationError(_(
                    'Must specify a script_name in extra_params for SCRIPT configuration type'
                ))

        # Validate duration is set if it's a REPEAT_* type configuration
        if 'REPEAT' in data['type']:
            if 'repeat_duration' not in data or data['repeat_duration'] is None:
                raise serializers.ValidationError(_(
                    f'Must specify a configuration repeat_duration for {data["type"]} type configurations.'
                ))
            else:
                # Validate that the duration exceeds the minimum to run everything at least once
                min_duration = sum(
                    [get_instrument_configuration_duration(
                        ic, data['instrument_type']) for ic in data['instrument_configs']]
                )
                if min_duration > data['repeat_duration']:
                    raise serializers.ValidationError(_(
                        f'Configuration repeat_duration of {data["repeat_duration"]} is less than the minimum of '
                        f'{min_duration} required to repeat at least once'
                    ))
        else:
            if 'repeat_duration' in data and data['repeat_duration'] is not None:
                raise serializers.ValidationError(_(
                    'You may only specify a repeat_duration for REPEAT_* type configurations.'
                ))

        # Validate dither pattern

        is_dither_sequence = False
        for instrument_config in data['instrument_configs']:
            offset_ra = instrument_config.get('extra_params', {}).get('offset_ra', 0)
            offset_dec = instrument_config.get('extra_params', {}).get('offset_dec', 0)
            if offset_dec != 0 or offset_ra != 0:
                is_dither_sequence = True
                break

        dither_pattern_is_set = 'extra_params' in data and 'dither_pattern' in data['extra_params']
        dither_pattern = data.get('extra_params', {}).get('dither_pattern', None)

        # Check that if a dither pattern is set, this configuration is actually a dither sequence
        if dither_pattern_is_set and not is_dither_sequence:
            raise serializers.ValidationError(_(
                f'You set a dither pattern of {dither_pattern} but did not supply any non-zero dither offsets. You must specify '
                'offset_ra and/or offset_dec fields in the extra_params in one or more instrument_configs to create a '
                'dither pattern.'
            ))

        # Check that any dither pattern that is set is valid
        if dither_pattern_is_set:
            valid_patterns = list(settings.DITHER['valid_expansion_patterns']) + [settings.DITHER['custom_pattern_key']]
            if dither_pattern not in valid_patterns:
                raise serializers.ValidationError(_(
                    f'Invalid dither pattern {dither_pattern} set in the configuration extra_params, choose from {", ".join(valid_patterns)}'
                ))

        # If a dither pattern is not yet set and this is part of a dither sequence, set the custom dither pattern field.
        if not dither_pattern_is_set and is_dither_sequence:
            if 'extra_params' not in data:
                data['extra_params'] = {}
            data['extra_params']['dither_pattern'] = settings.DITHER['custom_pattern_key']

        return data


class LocationSerializer(serializers.ModelSerializer):
    site = serializers.ChoiceField(choices=configdb.get_site_tuples(), required=False)
    enclosure = serializers.ChoiceField(choices=configdb.get_enclosure_tuples(), required=False)
    telescope = serializers.ChoiceField(choices=configdb.get_telescope_tuples(), required=False)
    telescope_class = serializers.ChoiceField(choices=configdb.get_telescope_class_tuples(), required=True)

    class Meta:
        model = Location
        exclude = Location.SERIALIZER_EXCLUDE

    def validate(self, data):
        if 'enclosure' in data and 'site' not in data:
            raise serializers.ValidationError(_("Must specify a site with an enclosure."))
        if 'telescope' in data and 'enclosure' not in data:
            raise serializers.ValidationError(_("Must specify an enclosure with a telescope."))

        site_data_dict = {site['code']: site for site in configdb.get_site_data()}
        if 'site' in data:
            if data['site'] not in site_data_dict:
                msg = _('Site {} not valid. Valid choices: {}').format(data['site'], ', '.join(site_data_dict.keys()))
                raise serializers.ValidationError(msg)
            enc_set = site_data_dict[data['site']]['enclosure_set']
            enc_dict = {enc['code']: enc for enc in enc_set}
            if 'enclosure' in data:
                if data['enclosure'] not in enc_dict:
                    raise serializers.ValidationError(_(
                        f'Enclosure {data["enclosure"]} not valid. Valid choices: {", ".join(enc_dict.keys())}'
                    ))
                tel_set = enc_dict[data['enclosure']]['telescope_set']
                tel_list = [tel['code'] for tel in tel_set]
                if 'telescope' in data and data['telescope'] not in tel_list:
                    msg = _('Telescope {} not valid. Valid choices: {}').format(data['telescope'], ', '.join(tel_list))
                    raise serializers.ValidationError(msg)

        return data

    def to_representation(self, instance):
        """
        This method is overridden to remove blank fields from serialized output. We could put this into a subclassed
        ModelSerializer if we want it to apply to all our Serializers.
        """
        rep = super().to_representation(instance)
        return {key: val for key, val in rep.items() if val}


class WindowSerializer(serializers.ModelSerializer):
    start = serializers.DateTimeField(required=False)

    class Meta:
        model = Window
        exclude = Window.SERIALIZER_EXCLUDE

    def validate(self, data):
        if 'start' not in data:
            data['start'] = timezone.now()
        if data['end'] <= data['start']:
            msg = _(f"Window end '{data['end']}' cannot be earlier than window start '{data['start']}'")
            raise serializers.ValidationError(msg)

        if not get_semester_in(data['start'], data['end']):
            raise serializers.ValidationError('The observation window does not fit within any defined semester.')
        return data

    def validate_end(self, value):
        if value < timezone.now():
            raise serializers.ValidationError('Window end time must be in the future')
        return value


class RequestSerializer(serializers.ModelSerializer):
    location = import_string(settings.SERIALIZERS['requestgroups']['Location'])()
    configurations = import_string(settings.SERIALIZERS['requestgroups']['Configuration'])(many=True)
    windows = import_string(settings.SERIALIZERS['requestgroups']['Window'])(many=True)
    cadence = import_string(settings.SERIALIZERS['requestgroups']['Cadence'])(required=False, write_only=True)
    duration = serializers.ReadOnlyField()

    class Meta:
        model = Request
        read_only_fields = (
            'id', 'created', 'duration', 'state',
        )
        exclude = Request.SERIALIZER_EXCLUDE

    def validate_configurations(self, value):
        if not value:
            raise serializers.ValidationError(_('You must specify at least 1 configuration'))

        # Only one configuration can have the fill_window attribute set
        if [config.get('fill_window', False) for config in value].count(True) > 1:
            raise serializers.ValidationError(_('Only one configuration can have `fill_window` set'))

        # Set the relative priority of molecules in order
        for i, configuration in enumerate(value):
            configuration['priority'] = i + 1

        return value

    def validate_windows(self, value):
        if not value:
            raise serializers.ValidationError(_('You must specify at least 1 window'))

        if len(set([get_semester_in(window['start'], window['end']) for window in value])) > 1:
            raise serializers.ValidationError(_('The observation windows must all be in the same semester'))

        return value

    def validate_cadence(self, value):
        if value:
            raise serializers.ValidationError(_('Please use the cadence endpoint to expand your cadence request'))
        return value

    def validate(self, data):
        is_staff = False
        only_schedulable = True
        request_context = self.context.get('request')
        if request_context:
            is_staff = request_context.user.is_staff
            only_schedulable = not (is_staff and ConfigDB.is_location_fully_set(data.get('location', {})))
        # check if the instrument specified is allowed
        # TODO: Check if ALL instruments are available at a resource defined by location
        if 'location' in data:
            # Check if the location is fully specified, and if not then use only schedulable instruments
            valid_instruments = configdb.get_instrument_type_codes(data.get('location', {}),
                                                              only_schedulable=only_schedulable)
            for configuration in data['configurations']:
                if configuration['instrument_type'] not in valid_instruments:
                    msg = _("Invalid instrument type '{}' at site={}, enc={}, tel={}. \n").format(
                        configuration['instrument_type'],
                        data.get('location', {}).get('site', 'Any'),
                        data.get('location', {}).get('enclosure', 'Any'),
                        data.get('location', {}).get('telescope', 'Any')
                    )
                    msg += _("Valid instruments include: ")
                    for inst_name in valid_instruments:
                        msg += inst_name + ', '
                    msg += '.'
                    if is_staff and not only_schedulable:
                        msg += '\nStaff users must fully specify location to schedule on non-SCHEDULABLE instruments'
                    raise serializers.ValidationError(msg)

        if 'acceptability_threshold' not in data:
            data['acceptability_threshold'] = max(
                [configdb.get_default_acceptability_threshold(configuration['instrument_type'])
                 for configuration in data['configurations']]
            )

        if 'extra_params' in data and 'mosaic_pattern' in data['extra_params']:
            pattern = data['extra_params']['mosaic_pattern']
            valid_patterns = list(settings.MOSAIC['valid_expansion_patterns']) + [settings.MOSAIC['custom_pattern_key']]
            if pattern not in valid_patterns:
                raise serializers.ValidationError(_(
                    f'Invalid mosaic pattern {pattern} set in the request extra_params, choose from {", ".join(valid_patterns)}'
                ))

        # check that the requests window has enough rise_set visible time to accomodate the requests duration
        if data.get('windows'):
            duration = get_total_request_duration(data)
            rise_set_intervals_by_site = get_filtered_rise_set_intervals_by_site(data, is_staff=is_staff)
            largest_interval = get_largest_interval(rise_set_intervals_by_site)
            for configuration in data['configurations']:
                if 'REPEAT' in configuration['type'].upper() and configuration.get('fill_window'):
                    max_configuration_duration = largest_interval.total_seconds() - duration + configuration.get('repeat_duration', 0) - 1
                    configuration['repeat_duration'] = max_configuration_duration
                    duration = get_total_request_duration(data)

                # delete the fill window attribute, it is only used for this validation
                try:
                    del configuration['fill_window']
                except KeyError:
                    pass
            if largest_interval.total_seconds() <= 0:
                raise serializers.ValidationError(
                    _(
                        'According to the constraints of the request, the target is never visible within the time '
                        'window. Check that the target is in the nighttime sky. Consider modifying the time '
                        'window or loosening the airmass or lunar separation constraints. If the target is '
                        'non sidereal, double check that the provided elements are correct.'
                    )
                )
            if largest_interval.total_seconds() <= duration:
                raise serializers.ValidationError(
                    (
                        'According to the constraints of the request, the target is visible for a maximum of {0:.2f} '
                        'hours within the time window. This is less than the duration of your request {1:.2f} hours. '
                        'Consider expanding the time window or loosening the airmass or lunar separation constraints.'
                    ).format(
                        largest_interval.total_seconds() / 3600.0,
                        duration / 3600.0
                    )
                )
        return data


class CadenceRequestSerializer(RequestSerializer):
    cadence = import_string(settings.SERIALIZERS['requestgroups']['Cadence'])()
    windows = import_string(settings.SERIALIZERS['requestgroups']['Window'])(required=False, many=True)

    def validate_cadence(self, value):
        return value

    def validate_windows(self, value):
        if value:
            raise serializers.ValidationError(_('Cadence requests may not contain windows'))

        return value


class RequestGroupSerializer(serializers.ModelSerializer):
    requests = import_string(settings.SERIALIZERS['requestgroups']['Request'])(many=True)
    submitter = serializers.StringRelatedField(default=serializers.CurrentUserDefault(), read_only=True)
    submitter_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = RequestGroup
        fields = '__all__'
        read_only_fields = (
            'id', 'created', 'state', 'modified'
        )
        extra_kwargs = {
            'proposal': {'error_messages': {'null': 'Please provide a proposal.'}},
            'name': {'error_messages': {'blank': 'Please provide a name.'}}
        }

    def create(self, validated_data):
        request_data = validated_data.pop('requests')
        now = timezone.now()
        with transaction.atomic():
            request_group = RequestGroup.objects.create(**validated_data)

            for r in request_data:
                configurations_data = r.pop('configurations')

                location_data = r.pop('location', {})
                windows_data = r.pop('windows', [])
                request = Request.objects.create(request_group=request_group, **r)

                if validated_data['observation_type'] != RequestGroup.DIRECT:
                    Location.objects.create(request=request, **location_data)
                    for window_data in windows_data:
                        Window.objects.create(request=request, **window_data)

                for configuration_data in configurations_data:
                    instrument_configs_data = configuration_data.pop('instrument_configs')
                    acquisition_config_data = configuration_data.pop('acquisition_config')
                    guiding_config_data = configuration_data.pop('guiding_config')
                    target_data = configuration_data.pop('target')
                    constraints_data = configuration_data.pop('constraints')
                    configuration = Configuration.objects.create(request=request, **configuration_data)

                    AcquisitionConfig.objects.create(configuration=configuration, **acquisition_config_data)
                    GuidingConfig.objects.create(configuration=configuration, **guiding_config_data)
                    Target.objects.create(configuration=configuration, **target_data)
                    Constraints.objects.create(configuration=configuration, **constraints_data)

                    for instrument_config_data in instrument_configs_data:
                        rois_data = []
                        if 'rois' in instrument_config_data:
                            rois_data = instrument_config_data.pop('rois')
                        instrument_config = InstrumentConfig.objects.create(configuration=configuration,
                                                                            **instrument_config_data)
                        for roi_data in rois_data:
                            RegionOfInterest.objects.create(instrument_config=instrument_config, **roi_data)
                telescope_class = location_data.get('telescope_class')
                if telescope_class:
                    cache.set(f"observation_portal_last_change_time_{telescope_class}", now, None)

        if validated_data['observation_type'] == RequestGroup.NORMAL:
            debit_ipp_time(request_group)

        logger.info('RequestGroup created', extra={'tags': {
            'user': request_group.submitter.username,
            'tracking_num': request_group.id,
            'name': request_group.name
        }})
        cache.set('observation_portal_last_change_time_all', now, None)

        return request_group

    def validate(self, data):
        # check that the user belongs to the supplied proposal
        user = self.context['request'].user
        if data['proposal'] not in user.proposal_set.all():
            raise serializers.ValidationError(
                _('You do not belong to the proposal you are trying to submit')
            )

        # Validate that the ipp_value is within the min/max range
        if 'ipp_value' in data:
            if data['ipp_value'] < settings.MIN_IPP_VALUE or data['ipp_value'] > settings.MAX_IPP_VALUE:
                raise serializers.ValidationError(_(f'requestgroups ipp_value must be >= {settings.MIN_IPP_VALUE}, <= {settings.MAX_IPP_VALUE}'))

        # validation on the operator matching the number of requests
        if data['operator'] == 'SINGLE':
            if len(data['requests']) > 1:
                raise serializers.ValidationError(
                    _("'Single' type requestgroups must have exactly one child request.")
                )
        elif len(data['requests']) == 1:
            raise serializers.ValidationError(
                _("'{}' type requestgroups must have more than one child request.".format(data['operator'].title()))
            )

        # Check that the user has not exceeded the time limit on this membership
        membership = Membership.objects.get(user=user, proposal=data['proposal'])
        if membership.time_limit >= 0:
            duration = sum(d for i, d in get_requestgroup_duration(data).items())
            time_to_be_used = user.profile.time_used_in_proposal(data['proposal']) + duration
            if membership.time_limit < time_to_be_used:
                raise serializers.ValidationError(
                    _('This request\'s duration will exceed the time limit set for your account on this proposal.')
                )

        if data['observation_type'] == RequestGroup.DIRECT:
            # Don't do any time accounting stuff if it is a directly scheduled observation
            return data
        else:
            for request in data['requests']:
                for config in request['configurations']:
                    # for non-DIRECT observations, don't allow HOUR_ANGLE targets (they're not supported in rise-set yet)
                    if config['target']['type'] == 'HOUR_ANGLE':
                        raise serializers.ValidationError(_('HOUR_ANGLE Target type not supported in scheduled observations'))

        try:
            total_duration_dict = get_total_duration_dict(data)
            for tak, duration in total_duration_dict.items():
                time_allocation = TimeAllocation.objects.get(
                    semester=tak.semester,
                    instrument_types__contains=[tak.instrument_type],
                    proposal=data['proposal'],
                )
                time_available = 0
                if data['observation_type'] == RequestGroup.NORMAL:
                    time_available = time_allocation.std_allocation - time_allocation.std_time_used
                elif data['observation_type'] == RequestGroup.RAPID_RESPONSE:
                    time_available = time_allocation.rr_allocation - time_allocation.rr_time_used
                    # For Rapid Response observations, check if the end time of the window is within
                    # 24 hours + the duration of the observation
                    for request in data['requests']:
                        windows = request.get('windows')
                        for window in windows:
                            if window.get('start') - timezone.now() > timedelta(seconds=0):
                                raise serializers.ValidationError(
                                    _("The Rapid Response observation window start time cannot be in the future.")
                                )
                            if window.get('end') - timezone.now() > timedelta(seconds=(duration + 86400)):
                                raise serializers.ValidationError(
                                    _(
                                        "A Rapid Response observation must start within the next 24 hours, so the "
                                        "window end time must be within the next (24 hours + the observation duration)"
                                    )
                                )
                elif data['observation_type'] == RequestGroup.TIME_CRITICAL:
                    # Time critical time
                    time_available = time_allocation.tc_allocation - time_allocation.tc_time_used

                if time_available <= 0.0:
                    raise serializers.ValidationError(
                        _("Proposal {} does not have any {} time left allocated in semester {} on {} instruments").format(
                            data['proposal'], data['observation_type'], tak.semester, tak.instrument_type)
                    )
                elif time_available * settings.PROPOSAL_TIME_OVERUSE_ALLOWANCE < (duration / 3600.0):
                    raise serializers.ValidationError(
                        _("Proposal {} does not have enough {} time allocated in semester {}").format(
                            data['proposal'], data['observation_type'], tak.semester)
                    )
            # validate the ipp debitting that will take place later
            if data['observation_type'] == RequestGroup.NORMAL:
                validate_ipp(data, total_duration_dict)
        except ObjectDoesNotExist:
            raise serializers.ValidationError(
                _("You do not have sufficient {} time allocated on the instrument you're requesting for this proposal.".format(
                    data['observation_type']
                ))
            )
        except TimeAllocationError as e:
            raise serializers.ValidationError(repr(e))

        return data

    def validate_requests(self, value):
        if not value:
            raise serializers.ValidationError(_('You must specify at least 1 request'))
        return value


class CadenceRequestGroupSerializer(RequestGroupSerializer):
    requests = import_string(settings.SERIALIZERS['requestgroups']['CadenceRequest'])(many=True)

    # override the validate method from the RequestGroupSerializer and use the Cadence Request serializer to
    # validate the cadence request
    def validate(self, data):
        if len(data['requests']) > 1:
            raise ValidationError('Cadence requestgroups may only contain a single request')

        return data


class PatternExpansionSerializer(serializers.Serializer):
    pattern = serializers.ChoiceField(choices=('line', 'grid', 'spiral'), required=True)
    num_points = serializers.IntegerField(required=False)
    point_spacing = serializers.FloatField(required=False)
    line_spacing = serializers.FloatField(required=False)
    orientation = serializers.FloatField(required=False, default=0.0)
    num_rows = serializers.IntegerField(required=False)
    num_columns = serializers.IntegerField(required=False)
    center = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        validated_data = super().validate(data)
        if 'num_points' not in validated_data and validated_data.get('pattern') in ['line', 'spiral']:
            raise serializers.ValidationError(_('Must specify num_points when selecting a line or spiral pattern'))
        if 'line_spacing' not in validated_data and 'point_spacing' in validated_data and validated_data.get('pattern') == 'grid':
            # Set a default line spacing equal to the point spacing if it is not specified
            validated_data['line_spacing'] = validated_data['point_spacing']
        if validated_data.get('pattern') == 'grid':
            if 'num_rows' not in validated_data or 'num_columns' not in validated_data:
                raise serializers.ValidationError(_('Must specify num_rows and num_columns when selecting a grid pattern'))
        return validated_data


class MosaicSerializer(PatternExpansionSerializer):
    request = import_string(settings.SERIALIZERS['requestgroups']['Request'])()
    pattern = serializers.ChoiceField(choices=settings.MOSAIC['valid_expansion_patterns'], required=True)
    point_overlap_percent = serializers.FloatField(required=False, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    line_overlap_percent = serializers.FloatField(required=False, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])

    def validate_request(self, request):
        if len(request.get('configurations', [])) > 1:
            raise serializers.ValidationError(_("Cannot expand a request for mosaicing with more than one configuration set"))
        if request['configurations'][0]['target']['type'] != 'ICRS':
            raise serializers.ValidationError(_("Mosaic expansion is only for ICRS Targets. Try using dither expansion for patterns with other target types"))

        return request

    def validate(self, data):
        validated_data = super().validate(data)
        # If point_overlap_percent is set, we will overwrite the point_spacing based on the requested
        # instrument_type and its fov on horizontal axis. If line_overlap_percent is specified, we will
        # do the same for the fov on the vertical axis - if it is not specified we will use the
        # point_overlap_percent and overwrite the line_spacing value
        if 'point_overlap_percent' in validated_data:
            instrument_type = data['request']['configurations'][0]['instrument_type']
            ccd_orientation = configdb.get_average_ccd_orientation(instrument_type)
            pattern_orientation = validated_data.get('orientation', 0.0)
            pattern_orientation = pattern_orientation % 360
            # Decide to flip the point/line overlapped sense based on general orientation
            if pattern_orientation < 45 or pattern_orientation > 315:
                flip = False
            elif pattern_orientation < 135:
                flip = True
            elif pattern_orientation < 225:
                flip = False
            elif pattern_orientation < 315:
                flip = True
            ccd_size = configdb.get_ccd_size(instrument_type)
            pixel_scale = configdb.get_pixel_scale(instrument_type)
            coso = cos(radians(ccd_orientation))
            sino = sin(radians(ccd_orientation))
            # Rotate the ccd dimensions by the ccd orientation - needed so our % overlap is in the correct frame
            rotated_ccd_x = ccd_size['x'] * coso + ccd_size['y'] * sino
            rotated_ccd_y = ccd_size['x'] * -sino + ccd_size['y'] * coso
            if 'line_overlap_percent' not in validated_data:
                validated_data['line_overlap_percent'] = validated_data['point_overlap_percent']
            validated_data['point_spacing'] = abs(rotated_ccd_y) * pixel_scale * ((100.0 - validated_data['point_overlap_percent']) / 100.0)
            validated_data['line_spacing'] = abs(rotated_ccd_x) * pixel_scale * ((100.0 - validated_data['line_overlap_percent']) / 100.0)
            if flip:
                # If the pattern orientation is closer to 90 or 270 (within 45 degrees), then flip the point/line spacing to better align with pattern orientation
                temp = validated_data['line_spacing']
                validated_data['line_spacing'] = validated_data['point_spacing']
                validated_data['point_spacing'] = temp
        elif 'point_spacing' not in validated_data:
            # One of point_spacing or point_overlap_percent must be specified
            raise serializers.ValidationError(_("Must specify one of point_spacing or point_overlap_percent"))
        return validated_data


class DitherSerializer(PatternExpansionSerializer):
    configuration = import_string(settings.SERIALIZERS['requestgroups']['Configuration'])()
    pattern = serializers.ChoiceField(choices=settings.DITHER['valid_expansion_patterns'], required=True)
    point_spacing = serializers.FloatField(required=True)


class DraftRequestGroupSerializer(serializers.ModelSerializer):
    author = serializers.SlugRelatedField(
        read_only=True,
        slug_field='username',
        default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = DraftRequestGroup
        fields = '__all__'
        read_only_fields = ('author',)

    def validate(self, data):
        if data['proposal'] not in self.context['request'].user.proposal_set.all():
            raise serializers.ValidationError('You are not a member of that proposal')
        return data

    def validate_content(self, data):
        try:
            json.loads(data)
        except JSONDecodeError:
            raise serializers.ValidationError('Content must be valid JSON')
        return data


class LastChangedSerializer(serializers.Serializer):
    last_change_time = serializers.DateTimeField()
