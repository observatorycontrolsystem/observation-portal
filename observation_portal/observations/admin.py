from django.contrib import admin

from observation_portal.observations.models import Observation, ConfigurationStatus, Summary


class ObservationAdmin(admin.ModelAdmin):
    list_display = ('site', 'observatory', 'telescope', 'start', 'end')
    list_filter = ('site',)


class ConfigurationStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'state', )
    list_filter = ('state', )


class SummaryAdmin(admin.ModelAdmin):
    list_display = ('start', 'end', 'state', 'reason', 'time_completed')
    list_filter = ('state', )


admin.site.register(Observation, ObservationAdmin)
admin.site.register(ConfigurationStatus, ConfigurationStatusAdmin)
admin.site.register(Summary, SummaryAdmin)