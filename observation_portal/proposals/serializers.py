from rest_framework import serializers

from observation_portal.proposals.models import Proposal, TimeAllocation, Semester


class TimeAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeAllocation
        exclude = ('id',)


class ProposalSerializer(serializers.ModelSerializer):
    timeallocation_set = TimeAllocationSerializer(many=True)
    users = serializers.SerializerMethodField()
    pi = serializers.StringRelatedField()

    def get_users(self, obj):
        return {
            mem.user.username: {
                'first_name': mem.user.first_name,
                'last_name': mem.user.last_name,
                'time_limit': mem.time_limit
            } for mem in obj.membership_set.all()
        }

    class Meta:
        model = Proposal
        fields = '__all__'


class SemesterSerialzer(serializers.ModelSerializer):
    class Meta:
        model = Semester
        fields = ('id', 'start', 'end')
