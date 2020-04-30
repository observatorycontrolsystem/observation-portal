from rest_framework import serializers
from observation_portal.common.configdb import configdb, ConfigDB, ConfigDBException

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
    instrument_class = InstrumentInfoSerializer()

class TelescopeStateSerializer(serializers.Serializer):
    start = serializers.CharField()
    end = serializers.CharField()
    telescope = serializers.CharField()
    event_type = serializers.CharField()
    event_reason = serializers.CharField()

class TelescopeStatesSerializer(serializers.Serializer):
    telescope_key = TelescopeStateSerializer(many=True)

class TelescopeAvailabilitySerializer(serializers.Serializer):
    dates = serializers.ListField(child=serializers.DateField())
    availabilities = serializers.ListField(child=serializers.FloatField())

class TelescopesAvailabilitySerializer(serializers.Serializer):
    telescope_key = TelescopeAvailabilitySerializer()

class ContentionDataSerializer(serializers.Serializer):
    proposal_id = serializers.FloatField()

class ContentionSerializer(serializers.Serializer):
    ra_hours = serializers.ListField(child=serializers.IntegerField(), default=[r for r in range(24)])
    instrument_type = serializers.CharField()
    time_calculated = serializers.DateTimeField()
    contention_data = ContentionDataSerializer(many=True)

class SiteNightSerializer(serializers.Serializer):
    name = serializers.ChoiceField(choices=configdb.get_site_tuples())
    start = serializers.FloatField()
    stop = serializers.FloatField()

class PressureDataSerializer(serializers.Serializer):
    proposal_id = serializers.FloatField()

class PressureSerializer(serializers.Serializer):
    site_nights = SiteNightSerializer(many=True)
    time_bins = serializers.ListField(child=serializers.DateTimeField())
    instrument_type = serializers.ChoiceField(choices=configdb.get_instrument_type_tuples(include_all=True))
    site = serializers.ChoiceField(choices=configdb.get_site_tuples(include_all=True))
    time_calculated = serializers.DateTimeField()
    pressure_data = PressureDataSerializer(many=True)
