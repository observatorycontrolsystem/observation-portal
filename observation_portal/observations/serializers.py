from rest_framework import serializers
from django.utils.translation import ugettext as _

from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.requestgroups.serializers import (RequestSerializer, ConfigurationSerializer)


class SummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Summary
        fields = '__all__'


class ConfigurationStatusSerializer(serializers.ModelSerializer):
    # summary = SummarySerializer()

    class Meta:
        model = ConfigurationStatus
        exclude = ('configuration', 'observation')


class ConfigurationWithStatusSerializer(ConfigurationSerializer):
    configuration_status = ConfigurationStatusSerializer()

    def to_representation(self, instance):
        # Merge the configuration data into this data at the same level
        data = super().to_representation(instance)
        config = data.get('configuration_status', {})
        if config:
            del data['configuration_status']
            data.update(config)
        return data


class ObserveRequestSerializer(RequestSerializer):
    configurations = ConfigurationWithStatusSerializer(many=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # remove the location and window sections
        del data['location']
        del data['windows']
        return data


class ObservationSerializer(serializers.ModelSerializer):
    request = ObserveRequestSerializer()
    proposal = serializers.SerializerMethodField()
    submitter = serializers.SerializerMethodField()
    observation_type = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    ipp_value = serializers.SerializerMethodField()

    class Meta:
        model = Observation
        fields = '__all__'

    def get_proposal(self, obj):
        return obj.request.request_group.proposal.id

    def get_submitter(self, obj):
        return obj.request.request_group.submitter.username

    def get_observation_type(self, obj):
        return obj.request.request_group.observation_type

    def get_name(self, obj):
        return obj.request.request_group.name

    def get_ipp_value(self, obj):
        return obj.request.request_group.ipp_value




