from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import ugettext as _

from observation_portal.common.configdb import configdb
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.requestgroups.serializers import (RequestSerializer, RequestGroupSerializer,
                                                          ConfigurationSerializer)
from observation_portal.requestgroups.models import RequestGroup
from observation_portal.proposals.models import Proposal


class SummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Summary
        exclude = ('configuration_status', 'id')


class ConfigurationStatusSerializer(serializers.ModelSerializer):
    summary = SummarySerializer()
    instrument_name = serializers.CharField(required=False)

    class Meta:
        model = ConfigurationStatus
        exclude = ('observation', 'modified', 'created')


class ObservationConfigurationSerializer(ConfigurationSerializer):
    def validate_instrument_class(self, value):
        # Check with ALL instrument type instead of just schedulable ones
        if not configdb.is_valid_instrument_type(value):
            raise serializers.ValidationError(_("Invalid Instrument Name {}".format(value)))
        return value


class ObserveRequestSerializer(RequestSerializer):
    configurations = ObservationConfigurationSerializer(many=True)
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

    class Meta:
        model = Observation
        exclude = ('modified', 'created')

    def validate_start(self, value):
        if value < timezone.now():
            raise serializers.ValidationError(_("Start time must be in the future"))
        return value

    def validate_proposal(self, value):
        try:
            proposal = Proposal.objects.get(id=value)
        except Proposal.DoesNotExist:
            raise serializers.ValidationError(_("Proposal {} does not exist".format(value)))
        if not proposal.direct_submission:
            raise serializers.ValidationError(_("Proposal {} is not allowed to submit observations directly".format(
                value
            )))
        return value

    def validate(self, data):
        # Validate the observation times
        if data['end'] <= data['start']:
            raise serializers.ValidationError(_("End time must be after start time"))

        # Validate the site/obs/tel is a valid combination with the instrument class requested
        allowable_instruments = configdb.get_instruments_at_location(
            data['site'], data['enclosure'], data['telescope']
        )
        for configuration in data['request']['configurations']:
            if configuration['instrument_class'].lower() not in allowable_instruments['types']:
                raise serializers.ValidationError(_("instrument type {} is not available at {}.{}.{}".format(
                    configuration['instrument_class'], data['site'], data['enclosure'], data['telescope']
                )))
            if not configuration.get('instrument_name', ''):
                instrument_names = configdb.get_instrument_names(
                    configuration['instrument_class'], data['site'], data['enclosure'], data['telescope']
                )
                if len(instrument_names) > 1:
                    raise serializers.ValidationError(_(
                        'There is more than one valid instrument on the specified telescope, please select from: {}'
                        .format(instrument_names)
                    ))
                else:
                    configuration['instrument_name'] = instrument_names[0]

            elif configuration['instrument_name'].lower() not in allowable_instruments['names']:
                raise serializers.ValidationError(_('instrument {} is not available at {}.{}.{}'.format(
                    configuration['instrument_name'], data['site'], data['enclosure'], data['telescope']
                )))

        # Add in the request group defaults for an observation
        data['observation_type'] = RequestGroup.DIRECT
        data['operator'] = 'SINGLE'
        data['ipp_value'] = 1.0
        return data

    def create(self, validated_data):
        # separate out the observation and request_group fields
        OBS_FIELDS = ['site', 'enclosure', 'telescope', 'start', 'end']
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
        # Add in the indirect fields from the requestgroup parent
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

