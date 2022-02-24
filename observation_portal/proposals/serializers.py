from rest_framework import serializers
from django.utils.translation import gettext as _
from django.utils.module_loading import import_string
from django.conf import settings

from observation_portal.proposals.models import Proposal, TimeAllocation, Semester, ProposalInvite, Membership


class TimeAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeAllocation
        exclude = ('id',)


class ProposalSerializer(serializers.ModelSerializer):
    timeallocation_set = import_string(settings.SERIALIZERS['proposals']['TimeAllocation'])(many=True)
    pi = serializers.StringRelatedField()

    class Meta:
        model = Proposal
        exclude = ('direct_submission', )


class SemesterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Semester
        fields = ('id', 'start', 'end')


class ProposalInviteSerializer(serializers.ModelSerializer):
    emails = serializers.ListField(child=serializers.EmailField(), write_only=True)

    class Meta:
        model = ProposalInvite
        fields = ('id', 'role', 'email', 'sent', 'used', 'proposal', 'emails')
        read_only_fields = ('role', 'email', 'proposal')

    def validate_emails(self, emails):
        user = self.context.get('user')
        proposal = self.context.get('proposal')
        for email in emails:
            if email.lower() == user.email.lower():
                raise serializers.ValidationError(_(f'You cannot invite yourself ({email}) to be a Co-Investigator'))
            if Membership.objects.filter(proposal=proposal, user__email__iexact=email).exists():
                raise serializers.ValidationError(_(f'User with email {email} is already a member of this proposal'))
        return emails


class ProposalInviteResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default='Co Investigator(s) invited')


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ('id', 'proposal', 'role', 'user', 'time_limit')


class ProposalNotificationSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class ProposalNotificationResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default='Preferences saved')


class TimeLimitSerializer(serializers.Serializer):
    time_limit_hours = serializers.FloatField()

    def validate(self, data):
        membership = self.context.get('membership')
        if membership and membership.role == Membership.PI:
            raise serializers.ValidationError(_('You cannot set the limit on a PI membership'))
        return data


class TimeLimitResponseSerializer(serializers.Serializer):
    message = serializers.CharField(default='All CI time limits set')
