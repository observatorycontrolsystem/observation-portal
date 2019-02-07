from rest_framework import serializers
from django.utils.translation import ugettext as _

from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.requestgroups.serializers import (RequestSerializer, RequestGroupSerializer,
                                                          ConfigurationSerializer)
from observation_portal.requestgroups.models import (RequestGroup, Request)
import logging


class SummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Summary
        exclude = ('configuration_status', 'id')


class ConfigurationStatusSerializer(serializers.ModelSerializer):
    summary = SummarySerializer()

    class Meta:
        model = ConfigurationStatus
        exclude = ('observation', 'modified', 'created')


class ObserveRequestSerializer(RequestSerializer):
    windows = None
    location = None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # remove the location and window sections
        if 'location' in data:
            del data['location']
        if 'windows' in data:
            del data['windows']
        return data


class ObserveRequestGroupSerializer(RequestGroupSerializer):
    request = ObserveRequestSerializer()
    requests = None

    def validate(self, data):
        data['requests'] = [data['request'], ]
        del data['request']
        data = super().validate(data)
        return data


class ObservationSerializer(serializers.ModelSerializer):
    configuration_status = ConfigurationStatusSerializer(many=True, read_only=True)
    request = ObserveRequestSerializer()
    proposal = serializers.CharField(write_only=True)
    name = serializers.CharField(write_only=True)
    ipp_value = serializers.FloatField(write_only=True)

    class Meta:
        model = Observation
        exclude = ('modified', 'created')

    def validate(self, data):
        data['observation_type'] = RequestGroup.DIRECT
        data['operator'] = 'SINGLE'
        return data

    def create(self, validated_data):
        # separate out the observation and request_group fields
        OBS_FIELDS = ['site', 'observatory', 'telescope', 'start', 'end']
        obs_fields = {}
        for field in OBS_FIELDS:
            obs_fields[field] = validated_data[field]
            del validated_data[field]

        rgs = ObserveRequestGroupSerializer(data=validated_data, context=self.context)
        rgs.is_valid(True)
        rg = rgs.save()

        observation = Observation.objects.create(request=rg.requests.first(), **obs_fields)

        for config in rg.requests.first().configurations.all():
            ConfigurationStatus.objects.create(configuration=config, observation=observation)

        return observation

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['proposal'] = instance.request.request_group.proposal.id
        data['submitter'] = instance.request.request_group.submitter.username
        data['name'] = instance.request.request_group.name
        data['ipp_value'] = instance.request.request_group.ipp_value
        data['observation_type'] = instance.request.request_group.observation_type

        # Move the configuration statuses inline with their corresponding configuration section
        config_statuses = data.get('configuration_status', [])
        config_status_by_id = {cs['configuration']: cs for cs in config_statuses}
        for config in data['request']['configurations']:
            id = config['id']
            if id in config_status_by_id:
                del config_status_by_id[id]['configuration']
                config['configuration_status'] = config_status_by_id[id]['id']
                del config_status_by_id[id]['id']
                config.update(config_status_by_id[id])
        del data['configuration_status']
        return data

