# -*- coding: utf-8 -*-
from django.contrib import admin

from observation_portal.proposals.forms import TimeAllocationForm, TimeAllocationFormSet, CollaborationAllocationForm
from observation_portal.common.utils import get_queryset_field_values
from observation_portal.proposals.models import (
    Semester,
    ScienceCollaborationAllocation,
    CollaborationAllocation,
    Proposal,
    TimeAllocation,
    Membership,
    ProposalInvite,
    ProposalNotification
)


class SemesterAdmin(admin.ModelAdmin):
    list_display = ('id', 'start', 'end')
    list_filter = ('start', 'end')
    raw_id_fields = ('proposals',)
    search_fields = ['id']


class CollaborationAllocationAdminInline(admin.TabularInline):
    model = CollaborationAllocation
    form = CollaborationAllocationForm
    extra = 0


class ScienceCollaborationAllocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    raw_id_fields = ['admin']
    inlines = [CollaborationAllocationAdminInline]

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('id',)
        return self.readonly_fields


class TimeAllocationAdminInline(admin.TabularInline):
    model = TimeAllocation
    form = TimeAllocationForm
    formset = TimeAllocationFormSet
    extra = 0
    show_change_link = True


class ProposalTagListFilter(admin.SimpleListFilter):
    """Filter proposals given a proposal tag"""
    title = 'Tag'
    parameter_name = 'tag'

    def lookups(self, request, model_admin):
        proposal_tags = get_queryset_field_values(Proposal.objects.all(), 'tags')
        return ((tag, tag) for tag in proposal_tags)

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(tags__contains=[value])
        else:
            return queryset


class ProposalAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'active',
        'title',
        'tac_priority',
        'sca',
        'public',
        'semesters',
        'pi',
        'tags',
        'created',
        'modified'
    )
    list_filter = ('active', ProposalTagListFilter, 'sca', 'public')
    raw_id_fields = ('users',)
    inlines = [TimeAllocationAdminInline]
    search_fields = ['id', 'title', 'abstract']
    readonly_fields = []
    actions = ['activate_selected', 'deactivate_selected']

    def semesters(self, obj):
        return [semester.id for semester in obj.semester_set.all().distinct()]
    semesters.ordering = ''

    def activate_selected(self, request, queryset):
        activated = queryset.filter(active=False).update(active=True)
        self.message_user(request, 'Successfully activated {} proposal(s)'.format(activated))
    activate_selected.short_description = 'Activate selected inactive proposals'

    @admin.action(description='Deactivate selected proposals')
    def deactivate_selected(self, request, queryset):
        deactivated = queryset.update(active=False)
        self.message_user(request, 'Successfully deactivated {} proposal(s)'.format(deactivated))

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ['id']
        else:
            return self.readonly_fields

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


class MembershipAdmin(admin.ModelAdmin):
    list_display = ('proposal', 'proposal_title', 'user', 'role')
    list_filter = ('role',)
    search_fields = ['proposal__id', 'user__username', 'user__email', 'proposal__title']
    raw_id_fields = ['user', 'proposal']

    def proposal_title(self, obj):
        return obj.proposal.title


class ProposalInviteAdmin(admin.ModelAdmin):
    model = ProposalInvite
    raw_id_fields = ['proposal']


class ProposalNotificationAdmin(admin.ModelAdmin):
    search_fields = ['proposal__id', 'user__username', 'user__email']
    model = ProposalNotification
    raw_id_fields = ['proposal', 'user']


class TimeAllocationInstrumentTypesFilter(admin.SimpleListFilter):
    title = "Instrument Type"
    parameter_name = "instrument_type"

    def lookups(self, request, model_admin):
        inst_types = TimeAllocation.objects.values_list("instrument_types", flat=True)
        inst_types = [(inst, inst) for sublist in inst_types for inst in sublist if inst]
        return sorted(set(inst_types))

    def queryset(self, request, queryset):
        lookup_value = self.value()
        if lookup_value:
            queryset = queryset.filter(instrument_types__contains=[lookup_value])
        return queryset

class TimeAllocationAdmin(admin.ModelAdmin):
    list_display = ['semester', 'proposal', 'instrument_types']
    list_filter = [TimeAllocationInstrumentTypesFilter, 'semester', 'proposal']
    autocomplete_fields = ['semester', 'proposal']

    form = TimeAllocationForm

admin.site.register(Semester, SemesterAdmin)
admin.site.register(ScienceCollaborationAllocation, ScienceCollaborationAllocationAdmin)
admin.site.register(Proposal, ProposalAdmin)
admin.site.register(Membership, MembershipAdmin)
admin.site.register(ProposalInvite, ProposalInviteAdmin)
admin.site.register(ProposalNotification, ProposalNotificationAdmin)
admin.site.register(TimeAllocation, TimeAllocationAdmin)
