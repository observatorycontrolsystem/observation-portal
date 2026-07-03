# -*- coding: utf-8 -*-
import csv
import io

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.generic import FormView
from django_object_actions import DjangoObjectActions, action

from observation_portal.common.admin import export_sciapps_key_data_tsv
from observation_portal.common.utils import get_queryset_field_values
from observation_portal.proposals.forms import (
    CollaborationAllocationForm,
    TimeAllocationForm,
    TimeAllocationFormSet,
)
from observation_portal.proposals.models import (
    CollaborationAllocation,
    Membership,
    Proposal,
    ProposalInvite,
    ProposalNotification,
    ScienceCollaborationAllocation,
    Semester,
    TimeAllocation,
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


class ProposalAdmin(DjangoObjectActions, admin.ModelAdmin):
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
    actions = ['activate_selected', 'deactivate_selected', 'makepublic_selected', 'rollover_selected', 'export_related_sciapp_key_data_tsv', 'export_key_data_tsv']
    changelist_actions = ['import_proposals_csv']

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

    @admin.action(description="Export related science application data as TSV")
    def export_related_sciapp_key_data_tsv(self, request, queryset):
        tsv = export_sciapps_key_data_tsv([sciapp for o in queryset for sciapp in o.scienceapplication_set.all()])

        return render(
            request,
            "admin/export_data.html",
            context={
              "export": tsv,
            }
        )

    @admin.action(description="Export key data as TSV")
    def export_key_data_tsv(self, request, queryset):
        column_getters = [
          # name, lambda o: value
          ("Proposal ID", lambda o: o.id),
          ("Rank", lambda o: o.tac_rank),
          ("Title", lambda o: o.title),
          ("PI Name", lambda o: " ".join([o.pi.first_name, o.pi.last_name])),
          ("PI Institution", lambda o: o.pi.profile.institution),
          ("PI Email", lambda o: o.pi.email),
          ("Tags", lambda o: "|".join(o.tags))
        ]

        timeallocation_semesters_start = {}
        for o in queryset:
            for tr in o.timeallocation_set.all():
                timeallocation_semesters_start[tr.semester.id] = tr.semester.start

        timeallocation_semesters = [y[0] for y in sorted(timeallocation_semesters_start.items(), key=lambda x: x[1])]

        def timeallocation_by_inst_type(o, inst_type, semester):
            for ta in o.timeallocation_set.filter(semester__id=semester):
                if ta.instrument_types != [inst_type]:
                    continue
                yield ta

        def get_queue_time(o, inst_type, semester):
            ret = 0
            for ta in timeallocation_by_inst_type(o, inst_type, semester):
                ret += ta.std_allocation
            return ret

        def get_rr_time(o, inst_type, semester):
            ret = 0
            for ta in timeallocation_by_inst_type(o, inst_type, semester):
                ret += ta.rr_allocation
            return ret

        def get_tc_time(o, inst_type, semester):
            ret = 0
            for ta in timeallocation_by_inst_type(o, inst_type, semester):
                ret += ta.tc_allocation
            return ret

        for semester in timeallocation_semesters:
            for inst_type in settings.ADMIN_EXPORT_INSTRUMENT_TYPES:
                column_getters.extend([
                  (f"{semester} {inst_type} Queue", lambda o, inst_type=inst_type, semester=semester: get_queue_time(o, inst_type, semester)),
                  (f"{semester} {inst_type} RR", lambda o, inst_type=inst_type, semester=semester: get_rr_time(o, inst_type, semester)),
                  (f"{semester} {inst_type} TC", lambda o, inst_type=inst_type, semester=semester: get_tc_time(o, inst_type, semester)),
                ])

        rows = []
        for o in queryset:
            cols = []
            for cg in column_getters:
                cols.append(str(cg[1](o)))
            rows.append("\t".join(cols))

        headers = "\t".join([cg[0] for cg in column_getters])
        tsv = "\n".join([headers, "\n".join(rows)])

        return render(
            request,
            "admin/export_data.html",
            context={
              "export": tsv,
            }
        )

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

    @action(label="Import Proposals from CSV")
    def import_proposals_csv(self, request, _queryset):
        return ImportCSVView.as_view()(request, admin=self)


def import_csv_data(csv_file, semester) -> int:
    reader = csv.DictReader(io.TextIOWrapper(csv_file))
    created = 0
    for row in reader:
        print(row)
        # TODO: Fill in/Fix the business logic here. In particular, decide what to do if
        # the PI is not found, make the SCA lookup correct

        # Create base proposal
        proposal = Proposal.objects.create(
            id=row["PropID"],
            title=row["Title"],
            abstract=row["Abstract"],
            # TODO: This should be the real SCA. Could also be a dropdown in the form.
            sca=ScienceCollaborationAllocation.objects.get_or_create(
                id="SOAR", name="SOAR"
            )[0],
        )

        # Attempt to add PI membership
        email = row["PI_email"]
        try:
            user = User.objects.get(email=email)
            Membership.objects.create(user=user, proposal=proposal, role="PI")
        except User.DoesNotExist:
            # could not find PI. Do what here? Create or no membership?
            # the name is available as row['PI_name']
            pass

        # Create a TimeAllocation
        tc = float(row["time TIME_CRITICAL"]) if row["time TIME_CRITICAL"] else 0.0
        std = float(row["time NORMAL"]) if row["time NORMAL"] else 0.0
        TimeAllocation.objects.create(
            proposal=proposal,
            semester=semester,
            tc_allocation=tc,
            std_allocation=std,
            instrument_types=row["Instrument"].replace(" ", "").split(","),
        )
        created += 1
    return created


class ImportCSVForm(forms.Form):
    csv_file = forms.FileField(label="CSV File", required=True)
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.all(), label="Semester", required=True
    )


class ImportCSVView(FormView):
    form_class = ImportCSVForm
    template_name = "admin/generic_form.html"

    # Passing the admin object to the view (see the import_propsals_csv method in the Admin)
    # So that we can call admin.message_user after the form is submitted.
    def dispatch(self, request, *args, admin, **kwargs):
        self.admin = admin
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        print(form.cleaned_data["csv_file"])
        num_imported = import_csv_data(
            form.files["csv_file"], form.cleaned_data["semester"]
        )
        self.admin.message_user(
            self.request, f"Successfully imported {num_imported} proposals."
        )
        return redirect("admin:proposals_proposal_changelist")


class MembershipAdmin(admin.ModelAdmin):
    list_display = ('proposal', 'proposal_title', 'user', 'role')
    list_filter = ('role',)
    search_fields = ['proposal__id', 'user__username', 'user__email', 'proposal__title']
    raw_id_fields = ['user', 'proposal']

    def proposal_title(self, obj):
        return obj.proposal.title


class ProposalInviteAdmin(admin.ModelAdmin):
    search_fields = ['proposal__id', 'email']
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
