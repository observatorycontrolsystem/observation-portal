from rest_framework import serializers

from observation_portal.sciapplications.models import ScienceApplication, Call, TimeRequest, CoInvestigator


class CallSerializer(serializers.ModelSerializer):
    proposal_type_display = serializers.SerializerMethodField()

    class Meta:
        model = Call
        fields = (
            'id', 'semester', 'proposal_type', 'proposal_type_display', 'eligibility_short', 'deadline', 'opens'
        )

    def get_proposal_type_display(self, obj):
        return obj.get_proposal_type_display()


class CoInvestigatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoInvestigator
        fields = ('first_name', 'last_name', 'institution', 'email')


class TimeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeRequest
        fields = ('semester', 'std_time', 'rr_time', 'tc_time', 'instrument')


class ScienceApplicationSerializer(serializers.ModelSerializer):
    call = CallSerializer()
    coinvestigator_set = CoInvestigatorSerializer(many=True)
    timerequest_set = TimeRequestSerializer(many=True)
    sca = serializers.SerializerMethodField()
    submitter = serializers.SerializerMethodField()

    class Meta:
        model = ScienceApplication
        fields = (
            'id', 'title', 'abstract', 'status', 'tac_rank', 'call', 'sca', 'submitted', 'pi',
            'pi_first_name', 'pi_last_name', 'pi_institution', 'submitter', 'timerequest_set',
            'coinvestigator_set'
        )

    def get_sca(self, obj):
        return {
            'id': obj.sca.id,
            'name': obj.sca.name
        }

    def get_submitter(self, obj):
        return {
            'first_name': obj.submitter.first_name,
            'last_name': obj.submitter.last_name,
            'institution': obj.submitter.profile.institution
        }
