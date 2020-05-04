from rest_framework import serializers
from dateutil.parser import parse
from datetime import timedelta
from django.utils import timezone

from observation_portal.requestgroups.contention import Contention, Pressure
from observation_portal.common.configdb import configdb, ConfigDB, ConfigDBException
from observation_portal.common.telescope_states import (
    TelescopeStates, get_telescope_availability_per_day, combine_telescope_availabilities_by_site_and_class,
    ElasticSearchException
)



def parse_start_end_parameters(data_dict, default_days_back):
    try:
        start = parse(data_dict.get('start'))
    except TypeError:
        start = timezone.now() - timedelta(days=default_days_back)
    start = start.replace(tzinfo=timezone.utc)
    try:
        end = parse(data_dict.get('end'))
    except TypeError:
        end = timezone.now()
    end = end.replace(tzinfo=timezone.utc)
    return start, end


class OpticalElementSerializer(serializers.Serializer):
    name = serializers.CharField()
    code = serializers.CharField()
    schedulable = serializers.BooleanField()

class OpticalElementsSerializer(serializers.Serializer):
    optical_element_group = OpticalElementSerializer(many=True)

class SpecificModeSerializer(serializers.Serializer):
    name = serializers.CharField()
    overhead = serializers.FloatField()
    code = serializers.CharField()
    params = serializers.DictField()

class ModeSerializer(serializers.Serializer):
    type = serializers.CharField()
    modes = SpecificModeSerializer(many=True)
    default = serializers.CharField()

class ModesSerializer(serializers.Serializer):
    mode_group = ModeSerializer()

class InstrumentInfoSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['SPECTRA', 'IMAGE'])
    telescope_class = serializers.ChoiceField(choices=configdb.get_telescope_class_tuples())
    name = serializers.CharField()
    optical_elements = OpticalElementsSerializer()
    modes = ModesSerializer()
    default_acceptability_threshold = serializers.FloatField(default=90.0)

class InstrumentsInfoSerializer(serializers.Serializer):
    instrument_class = InstrumentInfoSerializer(read_only=True)
    is_staff = serializers.BooleanField(write_only=True, required=True)

    def to_representation(self, instance):
        info = {}
        for instrument_type in configdb.get_instrument_types({}, only_schedulable=(not instance.get('is_staff', False))):
            info[instrument_type] = {
                'type': 'SPECTRA' if configdb.is_spectrograph(instrument_type) else 'IMAGE',
                'class': configdb.get_instrument_type_telescope_class(instrument_type),
                'name': configdb.get_instrument_type_full_name(instrument_type),
                'optical_elements': configdb.get_optical_elements(instrument_type),
                'modes': configdb.get_modes_by_type(instrument_type),
                'default_acceptability_threshold': configdb.get_default_acceptability_threshold(instrument_type)
            }
        return info

class TelescopeStateSerializer(serializers.Serializer):
    start = serializers.CharField()
    end = serializers.CharField()
    telescope = serializers.CharField()
    event_type = serializers.CharField()
    event_reason = serializers.CharField()

class TelescopeStatesSerializer(serializers.Serializer):
    telescope_key = TelescopeStateSerializer(many=True, read_only=True)
    start = serializers.DateTimeField(write_only=True)
    end = serializers.DateTimeField(write_only=True, required=False)
    site = serializers.MultipleChoiceField(choices=configdb.get_site_tuples(), write_only=True, required=False)
    telescope = serializers.MultipleChoiceField(choices=configdb.get_telescope_tuples(), write_only=True, required=False)

    def to_internal_value(self, data):
        ret_data = dict(data)
        start, end = parse_start_end_parameters(data, default_days_back=0)
        ret_data['start'] = start
        ret_data['end'] = end
        return ret_data

    def to_representation(self, instance):
        telescope_states = TelescopeStates(
            instance.get('start'), instance.get('end'), sites=list(instance.get('site', [])), 
            telescopes=list(instance.get('telescope', []))).get()
        str_telescope_states = {str(k): v for k, v in telescope_states.items()}
        return str_telescope_states

class TelescopeAvailabilitySerializer(serializers.Serializer):
    dates = serializers.ListField(child=serializers.DateField())
    availabilities = serializers.ListField(child=serializers.FloatField())

class TelescopesAvailabilitySerializer(serializers.Serializer):
    telescope_key = TelescopeAvailabilitySerializer(read_only=True)
    start = serializers.DateTimeField(write_only=True)
    end = serializers.DateTimeField(write_only=True, required=False)
    site = serializers.MultipleChoiceField(choices=configdb.get_site_tuples(), write_only=True, required=False)
    telescope = serializers.MultipleChoiceField(choices=configdb.get_telescope_tuples(), write_only=True, required=False)
    combine = serializers.BooleanField(write_only=True, default=False, required=False)

    def to_internal_value(self, data):
        ret_data = dict(data)
        start, end = parse_start_end_parameters(data, default_days_back=1)
        ret_data['start'] = start
        ret_data['end'] = end
        return ret_data

    def to_representation(self, instance):
        telescope_availability = get_telescope_availability_per_day(
            instance.get('start'), instance.get('end'), sites=list(instance.get('site', [])), 
            telescopes=list(instance.get('telescope', []))
        )
        if instance.get('combine', False):
            telescope_availability = combine_telescope_availabilities_by_site_and_class(
                telescope_availability)
        str_telescope_availability = {
            str(k): v for k, v in telescope_availability.items()}

        return str_telescope_availability

class ContentionDataSerializer(serializers.Serializer):
    proposal_id = serializers.FloatField()

class ContentionSerializer(serializers.Serializer):
    ra_hours = serializers.ListField(child=serializers.IntegerField(), default=[r for r in range(24)], read_only=True)
    instrument_type = serializers.CharField()
    time_calculated = serializers.DateTimeField(read_only=True)
    contention_data = ContentionDataSerializer(many=True, read_only=True)
    is_staff = serializers.BooleanField(write_only=True, required=True)

    def to_representation(self, instance):
        contention = Contention(instance.get('instrument_type'), anonymous=(not instance.get('is_staff', False)))

        return contention.data()

class SiteNightSerializer(serializers.Serializer):
    name = serializers.ChoiceField(choices=configdb.get_site_tuples())
    start = serializers.FloatField()
    stop = serializers.FloatField()

class PressureDataSerializer(serializers.Serializer):
    proposal_id = serializers.FloatField()

class PressureSerializer(serializers.Serializer):
    site_nights = SiteNightSerializer(many=True, read_only=True)
    time_bins = serializers.ListField(child=serializers.DateTimeField(), read_only=True)
    instrument_type = serializers.ChoiceField(choices=configdb.get_instrument_type_tuples(), allow_null=True)
    site = serializers.ChoiceField(choices=configdb.get_site_tuples(), allow_null=True)
    time_calculated = serializers.DateTimeField(read_only=True)
    pressure_data = PressureDataSerializer(many=True, read_only=True)
    is_staff = serializers.BooleanField(write_only=True, required=True)

    def to_representation(self, instance):
        pressure = Pressure(instance.get('instrument_type'), instance.get('site'),
                            anonymous=(not instance.get('is_staff', False)))

        return pressure.data()
