from django.contrib import admin

from observation_portal.observations.models import Observation, ConfigurationStatus, Summary


class SummaryInline(admin.TabularInline):
    model = Summary
    extra = 0


class ConfigurationStatusInline(admin.TabularInline):
    model = ConfigurationStatus
    extra = 0
    raw_id_fields = ('configuration', )


class ObservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'site', 'observatory', 'telescope', 'start', 'end')
    list_filter = ('site',)
    raw_id_fields = ('request', )
    inlines = [ConfigurationStatusInline]


class ConfigurationStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'state', )
    list_filter = ('state', )
    raw_id_fields = ('observation', 'configuration')
    inlines = [SummaryInline]


class SummaryAdmin(admin.ModelAdmin):
    list_display = ('start', 'end', 'state', 'reason', 'time_completed')
    list_filter = ('state', )


admin.site.register(Observation, ObservationAdmin)
admin.site.register(ConfigurationStatus, ConfigurationStatusAdmin)
admin.site.register(Summary, SummaryAdmin)