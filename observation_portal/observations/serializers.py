from rest_framework import serializers
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction
from django.utils.translation import ugettext as _

from observation_portal.common.configdb import configdb
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.requestgroups.serializers import (RequestSerializer, RequestGroupSerializer,
                                                          ConfigurationSerializer, TargetSerializer)
from observation_portal.requestgroups.models import RequestGroup, AcquisitionConfig, GuidingConfig, Target
from observation_portal.proposals.models import Proposal

import logging

from datetime import timedelta

logger = logging.getLogger()


class SummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Summary
        fields = ('start', 'end', 'state', 'reason', 'time_completed', 'events')


class ConfigurationStatusSerializer(serializers.ModelSerializer):
    TERMINAL_STATES = ['COMPLETED', 'ABORTED', 'FAILED', 'NOT_ATTEMPTED']
    summary = SummarySerializer(required=False)
    instrument_name = serializers.CharField(required=False)
    guide_camera_name = serializers.CharField(required=False)
    end = serializers.DateTimeField(required=False)

    class Meta:
        model = ConfigurationStatus
        exclude = ('observation', 'modified', 'created')

    def validate(self, data):
        data = super().validate(data)
        if self.context.get('request').method == 'PATCH':
            # For a partial update, only validate the end time if its set
            if 'end' in data and data['end'] <= timezone.now():
                raise serializers.ValidationError(_('Updated end time must be in the future'))
            return data

        if ('guide_camera_name' in data and
                not configdb.is_valid_guider_for_instrument_name(data['instrument_name'], data['guide_camera_name'])):
            raise serializers.ValidationError(_('{} is not a valid guide camera for {}'.format(
                data['guide_camera_name'], data['instrument_name']
            )))
        return data

    def update(self, instance, validated_data):
        update_fields = ['state']
        if instance.state not in ConfigurationStatusSerializer.TERMINAL_STATES:
            instance.state = validated_data.get('state', instance.state)
            instance.save(update_fields=update_fields)

        if 'summary' in validated_data:
            summary_serializer = SummarySerializer(data=validated_data['summary'])
            if summary_serializer.is_valid(raise_exception=True):
                summary = validated_data.get('summary')
                Summary.objects.update_or_create(
                    configuration_status=instance,
                    defaults={'reason': summary.get('reason', ''),
                              'start': summary.get('start'),
                              'end': summary.get('end'),
                              'state': summary.get('state'),
                              'time_completed': summary.get('time_completed'),
                              'events': summary.get('events', {})
                              }
                )

        if 'end' in validated_data:
            obs_end_time = validated_data['end']
            obs_end_time += timedelta(seconds=instance.observation.request.get_remaining_duration(instance.configuration.priority))
            instance.observation.update_end_time(obs_end_time)

        return instance


class ObservationTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Target
        exclude = Target.SERIALIZER_EXCLUDE

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {k: v for k, v in data.items() if v is not None}


class ObservationConfigurationSerializer(ConfigurationSerializer):
    instrument_name = serializers.CharField(required=False, write_only=True)
    guide_camera_name = serializers.CharField(required=False, write_only=True)
    target = ObservationTargetSerializer()

    def validate_instrument_type(self, value):
        # Check with ALL instrument type instead of just schedulable ones
        if not configdb.is_valid_instrument_type(value):
            raise serializers.ValidationError(_("Invalid Instrument Type {}".format(value)))
        return value

    def validate(self, data):
        # Currently don't validate configuration params for direct submissions until we add unschedulable flag to
        # generic modes in configdb
        # validated_data = super().validate(data)
        validated_data = data
        if validated_data['type'] not in ['BIAS', 'DARK', 'SKY_FLAT', 'NRES_BIAS', 'NRES_DARK']:
            target_serializer = TargetSerializer(data=validated_data['target'])
            if not target_serializer.is_valid():
                raise serializers.ValidationError(target_serializer.errors)
        return validated_data


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


class ScheduleSerializer(serializers.ModelSerializer):
    """ Used to validate direct-submitted observations """
    configuration_statuses = ConfigurationStatusSerializer(many=True, read_only=True)
    request = ObserveRequestSerializer()
    proposal = serializers.CharField(write_only=True)
    name = serializers.CharField(write_only=True)
    site = serializers.ChoiceField(choices=configdb.get_site_tuples())
    enclosure = serializers.ChoiceField(choices=configdb.get_enclosure_tuples())
    telescope = serializers.ChoiceField(choices=configdb.get_telescope_tuples())
    state = serializers.ReadOnlyField()

    class Meta:
        model = Observation
        fields = ('site', 'enclosure', 'telescope', 'start', 'end', 'state', 'configuration_statuses', 'request',
                  'proposal', 'priority', 'name', 'id', 'modified')
        read_only_fields = ('modified', 'id', 'configuration_statuses')

    def validate_end(self, value):
        if value < timezone.now():
            raise serializers.ValidationError(_("End time must be in the future"))
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
            # But only if the guide mode is set
            if (
                    configuration['guiding_config'].get('mode', GuidingConfig.OFF) != GuidingConfig.OFF or
                    configuration['acquisition_config'].get('mode', AcquisitionConfig.OFF) != AcquisitionConfig.OFF
            ):
                if not configuration.get('guide_camera_name', ''):
                    if (
                        'extra_params' in configuration
                        and 'self_guide' in configuration['extra_params']
                        and configuration['extra_params']['self_guide']
                    ):
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
            else:
                configuration['guide_camera_name'] = ''

        # Add in the request group defaults for an observation
        data['observation_type'] = RequestGroup.DIRECT
        data['operator'] = 'SINGLE'
        data['ipp_value'] = 1.0
        return data

    def create(self, validated_data):
        # separate out the observation and request_group fields
        OBS_FIELDS = ['site', 'enclosure', 'telescope', 'start', 'end', 'priority']
        obs_fields = {}
        for field in OBS_FIELDS:
            if field in validated_data:
                obs_fields[field] = validated_data[field]
                del validated_data[field]

        # pull out the instrument_names to store later
        config_instrument_names = []
        for configuration in validated_data['request']['configurations']:
            config_instrument_names.append((configuration['instrument_name'], configuration['guide_camera_name']))
            del configuration['instrument_name']
            del configuration['guide_camera_name']

        with transaction.atomic():
            rgs = ObserveRequestGroupSerializer(data=validated_data, context=self.context)
            rgs.is_valid(True)
            rg = rgs.save()

            observation = Observation.objects.create(request=rg.requests.first(), **obs_fields)

            for i, config in enumerate(rg.requests.first().configurations.all()):
                ConfigurationStatus.objects.create(
                    configuration=config,
                    observation=observation,
                    instrument_name=config_instrument_names[i][0],
                    guide_camera_name=config_instrument_names[i][1]
                )
        return observation

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Add in the indirect fields from the requestgroup parent
        data['proposal'] = instance.request.request_group.proposal.id
        data['submitter'] = instance.request.request_group.submitter.username
        data['name'] = instance.request.request_group.name
        data['ipp_value'] = instance.request.request_group.ipp_value
        data['observation_type'] = instance.request.request_group.observation_type
        data['request_group_id'] = instance.request.request_group.id

        # Move the configuration statuses inline with their corresponding configuration section
        config_statuses = data.get('configuration_statuses', [])
        config_status_by_id = {cs['configuration']: cs for cs in config_statuses}
        for config in data['request']['configurations']:
            id = config['id']
            if id in config_status_by_id:
                del config_status_by_id[id]['configuration']
                config['configuration_status'] = config_status_by_id[id]['id']
                del config_status_by_id[id]['id']
                config.update(config_status_by_id[id])
        del data['configuration_statuses']
        return data


class ObservationSerializer(serializers.ModelSerializer):
    configuration_statuses = ConfigurationStatusSerializer(many=True)

    class Meta:
        model = Observation
        fields = ('site', 'enclosure', 'telescope', 'start', 'end', 'priority', 'configuration_statuses', 'request', 'state', 'modified', 'created')
        read_only_fields = ('state', 'modified', 'created')

    def validate(self, data):
        user = self.context['request'].user
        if self.instance is not None:
            # An observation already exists, must be a patch and data won't have the request, so get request like this
            proposal = self.instance.request.request_group.proposal
        else:
            proposal = data['request'].request_group.proposal

        # If the user is not staff, check that they are allowed to perform the action
        if not user.is_staff and proposal not in user.proposal_set.filter(direct_submission=True):
            raise serializers.ValidationError(_(
                'Non staff users can only create or update observations on proposals they belong to that '
                'allow direct submission'
            ))

        if self.context.get('request').method == 'PATCH':
            # For a partial update, only validate that the 'end' field is set, and that it is > now
            if 'end' not in data:
                raise serializers.ValidationError(_('Observation update must include `end` field'))
            if data['end'] <= timezone.now():
                raise serializers.ValidationError(_('Updated end time must be in the future'))
            return data

        if data['end'] <= data['start']:
            raise serializers.ValidationError(_('End time must be after start time'))

        # Validate that the start and end times are in one of the requests windows
        in_a_window = False
        for window in data['request'].windows.all():
            if data['start'] >= window.start.replace(microsecond=0) and data['end'] <= window.end:
                in_a_window = True
                break

        if not in_a_window:
            raise serializers.ValidationError(_(
                'The start {} and end {} times do not fall within any window of the request'.format(
                    data['start'].isoformat(), data['end'].isoformat()
                )
            ))

        # Validate that the site, enclosure, and telescope match the location of the request
        if (
            data['request'].location.site and data['request'].location.site != data['site'] or
            data['request'].location.enclosure and data['request'].location.enclosure != data['enclosure'] or
            data['request'].location.telescope and data['request'].location.telescope != data['telescope'] or
            data['request'].location.telescope_class != data['telescope'][0:3]
        ):
            raise serializers.ValidationError(_('{}.{}.{} does not match the request location'.format(
                data['site'], data['enclosure'], data['telescope']
            )))

        # Validate that the site, enclosure, telescope has the appropriate instrument
        available_instruments = configdb.get_instruments_at_location(
            data['site'], data['enclosure'], data['telescope'], only_schedulable=False
        )
        for configuration in data['request'].configurations.all():
            if configuration.instrument_type.lower() not in available_instruments['types']:
                raise serializers.ValidationError(_('Instrument type {} not available at {}.{}.{}'.format(
                    configuration.instrument_type, data['site'], data['enclosure'], data['telescope']
                )))

        for configuration_status in data['configuration_statuses']:
            if configuration_status['instrument_name'].lower() not in available_instruments['names']:
                raise serializers.ValidationError(_('Instrument {} not available at {}.{}.{}'.format(
                    configuration_status['instrument_name'], data['site'], data['enclosure'], data['telescope']
                )))

        return data

    def update(self, instance, validated_data):
        return instance.update_end_time(validated_data['end'])

    def create(self, validated_data):
        configuration_statuses = validated_data.pop('configuration_statuses')
        with transaction.atomic():
            observation = Observation.objects.create(**validated_data)
            for configuration_status in configuration_statuses:
                ConfigurationStatus.objects.create(observation=observation, **configuration_status)
        return observation


class CancelObservationsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, required=False)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    site = serializers.CharField(required=False)
    enclosure = serializers.CharField(required=False)
    telescope = serializers.CharField(required=False)
    include_normal = serializers.BooleanField(required=False, default=True)
    include_rr = serializers.BooleanField(required=False, default=False)
    include_direct = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        if 'ids' not in data and ('start' not in data or 'end' not in data):
            raise serializers.ValidationError("Must include either an observation id list or a start and end time")

        return data
