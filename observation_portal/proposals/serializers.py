from observation_portal.common.utils import get_queryset_field_values
from rest_framework import serializers
from django.utils.translation import ugettext as _
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
    message = serializers.CharField(read_only=True, default='5 Co Investigator(s) invited')

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
    enabled = serializers.BooleanField(write_only=True)
    message = serializers.CharField(read_only=True, default='Preferences saved')


class TimeLimitSerializer(serializers.Serializer):
    time_limit_hours = serializers.FloatField(write_only=True)
    message = serializers.CharField(read_only=True, default='All CI time limits set to 20 hours')

    def validate(self, data):
        membership = self.context.get('membership')
        if membership and membership.role == Membership.PI:
            raise serializers.ValidationError(_('You cannot set the limit on a PI membership'))
        return data


class ProposalTagsSerializer(serializers.Serializer):
    tags = serializers.SerializerMethodField()

    def get_tags(self, obj):
        return get_queryset_field_values(obj, 'tags')


class SemesterProposalSerializer(serializers.ModelSerializer):
    semesters = serializers.SerializerMethodField()
    allocation = serializers.SerializerMethodField()
    pis = serializers.SerializerMethodField()
    sca_name = serializers.SerializerMethodField()
    sca_id = serializers.SerializerMethodField()
    class Meta:
        model = Proposal
        fields = ('id', 'title', 'abstract', 'allocation', 'semesters', 'pis', 'sca_id', 'sca_name')
        read_only_fields = fields

    def get_pis(self, obj):
        return [
            {
                'first_name': mem.user.first_name,
                'last_name': mem.user.last_name,
                'institution': mem.user.profile.institution
            } for mem in obj.membership_set.all() if mem.role == Membership.PI
        ]
    
    def get_sca_name(self, obj):
        return obj.sca.name
    
    def get_sca_id(self, obj):
        return obj.sca.id

    def get_allocation(self, obj):
        return obj.allocation(semester=self.context.get('semester'))

    def get_semesters(self, obj):
        return obj.semester_set.distinct().values_list('id', flat=True)


class ProposalTimeAllocationProposalDictSerializer(serializers.Serializer):
    notes = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    tac_priority = serializers.SerializerMethodField()
    num_users = serializers.SerializerMethodField()
    pis = serializers.SerializerMethodField()

    def get_notes(self, obj):
        return obj.proposal.notes

    def get_id(self, obj):
        return obj.proposal.id

    def get_tac_priority(self, obj):
        return obj.proposal.tac_priority

    def get_num_users(self, obj):
        return obj.proposal.membership_set.count()

    def get_pis(self, obj):
        return [
            {
                'first_name': mem.user.first_name,
                'last_name': mem.user.last_name
            } for mem in obj.proposal.membership_set.all() if mem.role == Membership.PI
        ]

    
class SemesterTimeAllocationSerializer(serializers.Serializer):
    proposal = serializers.SerializerMethodField(read_only=True)
    timeallocation_dict = serializers.SerializerMethodField(read_only=True)

    # return the list of time allocations without the JSON field name
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['timeallocation_dict']['proposal'] = representation['proposal']
        del representation['proposal']
        return representation['timeallocation_dict']

    def get_proposal(self, obj):
        return ProposalTimeAllocationProposalDictSerializer(obj).data

    # TODO: Need to figure out how to get the JSON structure from as_dict()
    def get_timeallocation_dict(self, obj):
        return obj.as_dict(exclude=['proposal', 'semester'])    
