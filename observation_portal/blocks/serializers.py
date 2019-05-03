from rest_framework import serializers


class CancelSerializer(serializers.Serializer):
    blocks = serializers.ListField(child=serializers.IntegerField(), min_length=1, required=False)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    cancel_reason = serializers.CharField(required=True)
    site = serializers.CharField(required=False)
    observatory = serializers.CharField(required=False)
    telescope = serializers.CharField(required=False)
    is_too = serializers.BooleanField(required=False)
    include_nonscheduled = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        if 'blocks' not in data and ('start' not in data or 'end' not in data):
            raise serializers.ValidationError("Must include either a blocks id list or a start and end time")

        return data
