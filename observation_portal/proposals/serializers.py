from rest_framework import serializers

from observation_portal.proposals.models import Proposal, TimeAllocation, Semester, Membership


class TimeAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeAllocation
        exclude = ('id',)


class ProposalSerializer(serializers.ModelSerializer):
    timeallocation_set = TimeAllocationSerializer(many=True)
    users = serializers.SerializerMethodField()
    pi = serializers.StringRelatedField()

    def get_users(self, obj):
        return {mem.user.username: mem.as_dict() for mem in obj.membership_set.all()}

    class Meta:
        model = Proposal
        exclude = ('direct_submission', )


class SemesterSerialzer(serializers.ModelSerializer):
    class Meta:
        model = Semester
        fields = ('id', 'start', 'end')


class ProposalNotificationSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class TimeLimitSerializer(serializers.Serializer):
    time_limit_hours = serializers.FloatField()
    usernames = serializers.ListField(child=serializers.CharField())
