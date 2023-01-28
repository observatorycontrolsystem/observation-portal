from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from observation_portal.observations.models import Observation, ConfigurationStatus, Summary
from observation_portal.observations.forms import ObservationForm
from observation_portal.observations.time_accounting import refund_observation_time, refund_configuration_status_time

class SummaryInline(admin.TabularInline):
    model = Summary
    extra = 0


class ConfigurationStatusInline(admin.TabularInline):
    model = ConfigurationStatus
    extra = 0
    raw_id_fields = ('configuration', )


class ObservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'state', 'site', 'enclosure', 'telescope', 'start', 'end', 'priority')
    list_filter = ('site', 'state')
    raw_id_fields = ('request', )
    form = ObservationForm
    inlines = [ConfigurationStatusInline]
    change_form_template = "observations/observation_changeform.html"

    def response_change(self, request, obj):
        if "refund-time" in request.POST:
            refund_percent = int(request.POST['refund-percent'])
            time_refunded = refund_observation_time(obj, refund_percent / 100.0)
            messages.info(request, f"Refunded {time_refunded} hours back to the TimeAllocation")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)


class ConfigurationStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'state', 'instrument_name', 'guide_camera_name')
    list_filter = ('state', )
    raw_id_fields = ('observation', 'configuration')
    inlines = [SummaryInline]
    change_form_template = "observations/observation_changeform.html"

    def response_change(self, request, obj):
        if "refund-time" in request.POST:
            refund_percent = int(request.POST['refund-percent'])
            time_refunded = refund_configuration_status_time(obj, refund_percent / 100.0)
            messages.info(request, f"Refunded {time_refunded} hours back to the TimeAllocation")
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)


class SummaryAdmin(admin.ModelAdmin):
    list_display = ('id', 'start', 'end', 'state', 'reason', 'time_completed')
    list_filter = ('state', )
    raw_id_fields = ('configuration_status', )


admin.site.register(Observation, ObservationAdmin)
admin.site.register(ConfigurationStatus, ConfigurationStatusAdmin)
admin.site.register(Summary, SummaryAdmin)
