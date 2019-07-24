from django.contrib import admin
from django.urls import reverse

from observation_portal.requestgroups.models import (RequestGroup, Request, Location, Target, Window, Configuration,
                                                     Constraints, InstrumentConfig, AcquisitionConfig, GuidingConfig)
from observation_portal.requestgroups.forms import LocationForm


class ConfigurationInline(admin.TabularInline):
    model = Configuration
    extra = 0


class LocationInline(admin.TabularInline):
    model = Location
    extra = 0
    forms = LocationForm


class TargetInline(admin.TabularInline):
    model = Target
    extra = 0


class WindowInline(admin.TabularInline):
    model = Window
    extra = 0


class ConstraintsInline(admin.TabularInline):
    model = Constraints
    extra = 0


class AcquisitionConfigInline(admin.TabularInline):
    model = AcquisitionConfig
    extra = 0


class GuidingConfigInline(admin.TabularInline):
    model = GuidingConfig
    extra = 0


class InstrumentConfigInline(admin.TabularInline):
    model = InstrumentConfig
    extra = 0


class RequestGroupAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'submitter',
        'proposal',
        'name',
        'observation_type',
        'operator',
        'ipp_value',
        'created',
        'state',
        'modified',
        'requests_count',
    )
    list_filter = ('state', 'created', 'modified')
    search_fields = ('name',)
    readonly_fields = ('requests', 'requests_count')
    raw_id_fields = ('proposal', 'submitter')

    def requests_count(self, obj):
        return obj.requests.count()

    def requests(self, obj):
        html = ''
        for request in obj.requests.all():
            html += '<a href="{0}">{1}</a></p>'.format(
                reverse('admin:requestgroups_request_change', args=(request.id,)),
                request.id
            )
        return html
    requests.allow_tags = True


class RequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'request_group',
        'observation_note',
        'state',
        'modified',
        'created',
    )
    raw_id_fields = (
        'request_group',
    )
    list_filter = ('state', 'modified', 'created')
    inlines = [ConfigurationInline, WindowInline, LocationInline]


class LocationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'request',
        'telescope_class',
        'site',
        'enclosure',
        'telescope',
    )
    form = LocationForm
    list_filter = ('telescope_class',)
    raw_id_fields = ('request',)


class TargetAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'configuration',
        'type',
        'hour_angle',
        'ra',
        'dec',
        'altitude',
        'azimuth',
        'proper_motion_ra',
        'proper_motion_dec',
        'epoch',
        'parallax',
        'diff_altitude_rate',
        'diff_azimuth_rate',
        'diff_epoch',
        'diff_altitude_acceleration',
        'diff_azimuth_acceleration',
        'scheme',
        'epochofel',
        'orbinc',
        'longascnode',
        'longofperih',
        'argofperih',
        'meandist',
        'perihdist',
        'eccentricity',
        'meanlong',
        'meananom',
        'dailymot',
        'epochofperih',
    )
    raw_id_fields = ('configuration', )
    list_filter = ('type',)
    search_fields = ('name',)


class WindowAdmin(admin.ModelAdmin):
    list_display = ('id', 'request', 'start', 'end')
    list_filter = ('start', 'end')
    raw_id_fields = (
        'request',
    )


class ConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'request',
        'type',
        'priority',
    )
    raw_id_fields = (
        'request',
    )
    list_filter = ('type',)
    inlines = [InstrumentConfigInline, ConstraintsInline, TargetInline, AcquisitionConfigInline, GuidingConfigInline]


class ConstraintsAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'configuration',
        'max_airmass',
        'min_lunar_distance',
        'max_lunar_phase',
        'max_seeing',
        'min_transparency',
    )
    raw_id_fields = ('configuration',)


class AcquisitionConfigAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'configuration',
        'mode',
    )
    raw_id_fields = ('configuration',)


class GuidingConfigAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'configuration',
        'optional',
        'mode',
        'exposure_time'
    )
    raw_id_fields = ('configuration',)


admin.site.register(Constraints, ConstraintsAdmin)
admin.site.register(AcquisitionConfig, AcquisitionConfigAdmin)
admin.site.register(GuidingConfig, GuidingConfigAdmin)
admin.site.register(Configuration, ConfigurationAdmin)
admin.site.register(Window, WindowAdmin)
admin.site.register(Target, TargetAdmin)
admin.site.register(RequestGroup, RequestGroupAdmin)
admin.site.register(Location, LocationAdmin)
admin.site.register(Request, RequestAdmin)
