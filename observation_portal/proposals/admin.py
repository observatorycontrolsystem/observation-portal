# -*- coding: utf-8 -*-
from django.contrib import admin
from django.shortcuts import render
from django.utils import timezone
from django.http import HttpResponseRedirect

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
    actions = ['activate_selected', 'deactivate_selected', 'makepublic_selected', 'rollover_selected']

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

    @admin.action(description='Make proposals Public')
    def makepublic_selected(self, request, queryset):
        public = queryset.update(public=True)
        self.message_user(request, 'Successfully made {} proposal(s) public'.format(public))

    @admin.action(description='Rollover time allocation for selected proposals')
    def rollover_selected(self, request, queryset):
        now = timezone.now()
        currentsemester = Semester.objects.filter(start__lte=now, end__gte=now).first()
        nextsemester = Semester.objects.filter(start__gte=currentsemester.end).order_by('start').first()
        if 'apply' in request.POST:
            for obj in queryset:
                allocations = obj.timeallocation_set.filter(semester=currentsemester)
                if obj.timeallocation_set.filter(semester=nextsemester).exists():
                    continue
                for allocation in allocations:
                    newtime = TimeAllocation.objects.create(semester=nextsemester, proposal=obj, instrument_types=allocation.instrument_types)
                    newtime.std_allocation = max(allocation.std_allocation - allocation.std_time_used,0)
                    newtime.rr_allocation = max(allocation.rr_allocation - allocation.rr_time_used,0)
                    newtime.tc_allocation = max(allocation.tc_allocation - allocation.tc_time_used,0)
                    newtime.realtime_allocation = max(allocation.realtime_allocation - allocation.realtime_time_used, 0)
                    newtime.ipp_limit = newtime.std_allocation/10
                    newtime.ipp_time_available = newtime.ipp_limit/2
                    newtime.save()

            self.message_user(request, 'Successfully rolled over time for {} proposal(s)'.format(queryset.count()))
            return HttpResponseRedirect(request.get_full_path())
  
        proposals = []
        rejects = []
        updated = []
        for obj in queryset:
            if not obj.timeallocation_set.filter(semester=currentsemester).exists():
                rejects.append(obj)
            elif obj.timeallocation_set.filter(semester=nextsemester).exists():
                updated.append(obj)
            else:
                proposals.append(obj)
        return render(request, 'admin/rollover_selected.html', context={'proposals':proposals, 'rejects':rejects, 'updated':updated, 'nextsemester':nextsemester, 'currentsemester':currentsemester})
                


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
