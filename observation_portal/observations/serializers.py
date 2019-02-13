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
    guide_camera_name = serializers.CharField(required=False)

    class Meta:
        model = ConfigurationStatus
        exclude = ('observation', 'modified', 'created')


class ObservationConfigurationSerializer(ConfigurationSerializer):
    instrument_name = serializers.CharField(required=False, write_only=True)
    guide_camera_name = serializers.CharField(required=False, write_only=True)

    def validate_instrument_type(self, value):
        # Check with ALL instrument type instead of just schedulable ones
        if not configdb.is_valid_instrument_type(value):
            raise serializers.ValidationError(_("Invalid Instrument Type {}".format(value)))
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
    site = serializers.ChoiceField(choices=configdb.get_site_tuples())
    enclosure = serializers.ChoiceField(choices=configdb.get_enclosure_tuples())
    telescope = serializers.ChoiceField(choices=configdb.get_telescope_tuples())

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
            if configuration['instrument_type'].lower() not in allowable_instruments['types']:
                raise serializers.ValidationError(_("instrument type {} is not available at {}.{}.{}".format(
                    configuration['instrument_type'], data['site'], data['enclosure'], data['telescope']
                )))
            if not configuration.get('instrument_name', ''):
                instrument_names = configdb.get_instrument_names(
                    configuration['instrument_type'], data['site'], data['enclosure'], data['telescope']
                )
                if len(instrument_names) > 1:
                    raise serializers.ValidationError(_(
                        'There is more than one valid instrument on the specified telescope, please select from: {}'
                        .format(instrument_names)
                    ))
                else:
                    configuration['instrument_name'] = instrument_names.pop()
            elif configuration['instrument_name'].lower() not in allowable_instruments['names']:
                raise serializers.ValidationError(_(
                    '{} is not an available {} instrument on {}.{}.{}, available instruments are: {}'.format(
                        configuration['instrument_name'], configuration['instrument_type'], data['site'],
                        data['enclosure'], data['telescope'], allowable_instruments['names']
                    )
                ))

            # Also check the guide and acquisition cameras are valid if specified
            if not configuration.get('guide_camera_name', ''):
                if 'self_guide' in configuration['extra_params'] and configuration['extra_params']['self_guide']:
                    configuration['guide_camera_name'] = configuration['instrument_name']
                else:
                    configuration['guide_camera_name'] = configdb.get_guider_for_instrument_name(
                        configuration['instrument_name']
                    )
            if not configdb.is_valid_guider_for_instrument_name(configuration['instrument_name'],
                                                                configuration['guide_camera_name']):
                raise serializers.ValidationError(_("Invalid guide camera {} for instrument {}".format(
                    configuration['guide_camera_name'],
                    configuration['instrument_name']
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

        # pull out the instrument_names to store later
        config_instrument_names = []
        for configuration in validated_data['request']['configurations']:
            config_instrument_names.append((configuration['instrument_name'], configuration['guide_camera_name']))
            del configuration['instrument_name']
            del configuration['guide_camera_name']

        rgs = ObserveRequestGroupSerializer(data=validated_data, context=self.context)
        rgs.is_valid(True)
        rg = rgs.save()

        observation = Observation.objects.create(request=rg.requests.first(), **obs_fields)

        for i, config in enumerate(rg.requests.first().configurations.all()):
            ConfigurationStatus.objects.create(configuration=config, observation=observation,
                                               instrument_name=config_instrument_names[i][0],
                                               guide_camera_name=config_instrument_names[i][1])

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

