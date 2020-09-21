from rest_framework import serializers
from django.utils.translation import ugettext as _

from observation_portal.proposals.models import Proposal, TimeAllocation, Semester, ProposalInvite, Membership


class TimeAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeAllocation
        exclude = ('id',)


class ProposalSerializer(serializers.ModelSerializer):
    timeallocation_set = TimeAllocationSerializer(many=True)
    users = serializers.SerializerMethodField()
    pi = serializers.StringRelatedField()
    requestgroup_count = serializers.SerializerMethodField()

    def get_users(self, obj):
        return {mem.user.username: mem.as_dict() for mem in obj.membership_set.all()}

    def get_requestgroup_count(self, obj):
        return obj.requestgroup_set.all().count()

    class Meta:
        model = Proposal
        exclude = ('direct_submission', )


class SemesterSerialzer(serializers.ModelSerializer):
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


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ('id', 'proposal', 'role', 'user', 'time_limit')


class ProposalNotificationSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class TimeLimitSerializer(serializers.Serializer):
    time_limit_hours = serializers.FloatField()
    membership_ids = serializers.ListField(child=serializers.IntegerField())
