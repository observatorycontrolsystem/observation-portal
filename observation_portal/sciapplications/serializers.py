from rest_framework import serializers

from observation_portal.sciapplications.models import Call


class CallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        fields = ('id', )
