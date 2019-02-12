from rest_framework import serializers
from django.contrib.auth.models import User

from observation_portal.accounts.models import Profile


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = (
            'education_user', 'notifications_enabled', 'notifications_on_authored_only',
            'simple_interface', 'view_authored_requests_only', 'staff_view', 'title',
            'institution', 'api_quota'
        )


class UserSerializer(serializers.ModelSerializer):
    proposals = serializers.SerializerMethodField()
    profile = ProfileSerializer()
    available_instrument_types = serializers.SerializerMethodField()
    tokens = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('username', 'email', 'profile', 'proposals', 'available_instrument_types', 'tokens')

    def get_proposals(self, obj):
        return [
            {'id': proposal.id, 'title': proposal.title, 'current': proposal in obj.profile.current_proposals}
            for proposal in obj.proposal_set.all()
        ]

    def get_available_instrument_types(self, obj):
        instrument_types = set()
        for proposal in obj.proposal_set.filter(active=True):
            for timeallocation in proposal.timeallocation_set.all():
                if timeallocation.instrument_class:
                    instrument_types.add(timeallocation.instrument_class)
        return list(instrument_types)

    def get_tokens(self, obj):
        return {'archive': obj.profile.archive_bearer_token}
