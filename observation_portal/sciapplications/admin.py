# -*- coding: utf-8 -*-
from datetime import datetime

from django.contrib import admin
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.conf import settings
from django.forms.models import ModelForm
from django.shortcuts import render

from .models import (
    Instrument, Call, ScienceApplication, TimeRequest, CoInvestigator,
    NoTimeAllocatedError, MultipleTimesAllocatedError, ScienceApplicationReview,
    ScienceApplicationUserReview, ReviewPanel, ReviewPanelMembership
)
from observation_portal.proposals.models import Proposal
from observation_portal.common.utils import get_queryset_field_values


class InstrumentAdmin(admin.ModelAdmin):
    list_display = ('code', 'display')


admin.site.register(Instrument, InstrumentAdmin)


class CallAdmin(admin.ModelAdmin):
    list_display = (
        'semester',
        'opens',
        'deadline',
        'proposal_type',
    )
    list_filter = ('opens', 'deadline', 'proposal_type')


admin.site.register(Call, CallAdmin)


class TimeRequestAdminInline(admin.TabularInline):
    model = TimeRequest


class CoInvestigatorInline(admin.TabularInline):
    model = CoInvestigator


class ScienceApplicationTagListFilter(admin.SimpleListFilter):
    """Filter science applications given a tag"""
    title = 'Tag'
    parameter_name = 'tag'

    def lookups(self, request, model_admin):
        sciapp_tags = get_queryset_field_values(ScienceApplication.objects.all(), 'tags')
        return ((tag, tag) for tag in sciapp_tags)

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(tags__contains=[value])
        else:
            return queryset

class AlwaysChangedModelForm(ModelForm):
    def has_changed(self):
        return True


class ScienceApplicationReviewInline(admin.StackedInline):
    model = ScienceApplicationReview
    readonly_fields = ["mean_grade"]
    autocomplete_fields = ["review_panel", "primary_reviewer", "secondary_reviewer"]
    form = AlwaysChangedModelForm
    extra = 0
    show_change_link = True


class ScienceApplicationAdmin(admin.ModelAdmin):
    inlines = [CoInvestigatorInline, TimeRequestAdminInline, ScienceApplicationReviewInline]
    list_display = (
        'title',
        'call',
        'status',
        'submitter',
        'tac_rank',
        'tags',
        'preview_link',
    )
    list_filter = (ScienceApplicationTagListFilter, 'call', 'status', 'call__proposal_type')
    actions = ['accept', 'reject', 'port', 'export_key_data_csv']
    search_fields = ['title', 'abstract', 'submitter__first_name', 'submitter__last_name', 'submitter__username']

    def preview_link(self, obj):
        urls = [{'text': 'View in API', 'url': reverse('api:scienceapplications-detail', args=(obj.id,))}]
        if settings.SCIENCE_APPLICATION_DETAIL_URL:
            urls.append(
                {'text': 'View on site', 'url': settings.SCIENCE_APPLICATION_DETAIL_URL.format(sciapp_id=obj.id)}
            )
        return format_html_join(
            ' ', '<a href="{}">{}</a>',
            ((url['url'], url['text']) for url in urls)
        )

    def accept(self, request, queryset):
        rows = queryset.filter(status=ScienceApplication.SUBMITTED).update(status=ScienceApplication.ACCEPTED)
        self.message_user(request, '{} application(s) were successfully accepted'.format(rows))

    def reject(self, request, queryset):
        rows = queryset.filter(status=ScienceApplication.SUBMITTED).update(status=ScienceApplication.REJECTED)
        self.message_user(request, '{} application(s) were successfully rejected'.format(rows))

    def port(self, request, queryset):
        apps = queryset.filter(status=ScienceApplication.ACCEPTED)
        for app in apps:
            if Proposal.objects.filter(id=app.proposal_code).exists():
                self.message_user(
                    request,
                    f'A proposal named {app.proposal_code} already exists. Check your tac rank for application '
                    f'"{app.title}"?',
                    level='ERROR'
                )
            else:
                try:
                    app.convert_to_proposal()
                except NoTimeAllocatedError:
                    self.message_user(
                        request, f'Application {app.title} has no approved Time Allocations', level='ERROR'
                    )
                    return
                except MultipleTimesAllocatedError:
                    self.message_user(
                        request,
                        f'Application {app.title} has more than one approved time request with same semester and '
                        f'instrument',
                        level='ERROR'
                    )
                    return
                self.message_user(request, f'Proposal {app.proposal} successfully created.')

                notification_sent = app.send_approved_notification()
                if not notification_sent:
                    self.message_user(
                        request,
                        f'Email notifying PI of approval of proposal {app.proposal} failed to send',
                        level='ERROR'
                    )
                    return

    @admin.action(description="Export key data as CSV")
    def export_key_data_csv(self, request, queryset):
        column_getters = [
          # name, lambda o: value
          ("Proposal ID", lambda o: o.id),
          ("Rank", lambda o: o.tac_rank),
          ("Title", lambda o: o.title),
          ("PI Name", lambda o: " ".join([o.pi_first_name, o.pi_last_name])),
          ("PI Institution", lambda o: o.pi_institution),
          ("PI Email", lambda o: o.pi),
          ("Tags", lambda o: "|".join(o.tags))
        ]

        timerequest_semesters_start = {}
        for o in queryset:
            for tr in o.timerequest_set.all():
                timerequest_semesters_start[tr.semester.id] = tr.semester.start

        timerequest_semesters = [y[0] for y in sorted(timerequest_semesters_start.items(), key=lambda x: x[1])]

        def timerequests_by_inst_type(o, inst_type, semester):
            for tr in o.timerequest_set.filter(semester__id=semester):
                if [inst.code for inst in tr.instrument_types.all()] != [inst_type]:
                    continue
                yield tr

        def get_queue_time(o, inst_type, semester):
            ret = 0
            for tr in timerequests_by_inst_type(o, inst_type, semester):
                ret += tr.std_time
            return ret

        def get_rr_time(o, inst_type, semester):
            ret = 0
            for tr in timerequests_by_inst_type(o, inst_type, semester):
                ret += tr.rr_time
            return ret

        def get_tc_time(o, inst_type, semester):
            ret = 0
            for tr in timerequests_by_inst_type(o, inst_type, semester):
                ret += tr.tc_time
            return ret

        for semester in timerequest_semesters:
            for inst_type in settings.SCI_APPS_ADMIN_EXPORT_CSV_INSTRUMENT_TYPES:
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
            rows.append(",".join(cols))

        headers = ",".join([cg[0] for cg in column_getters])
        csv = "\n".join([headers, "\n".join(rows)])
        return render(
            request,
            "admin/export_key_data_csv.html",
            context={
              "csv": csv,
            }
        )

admin.site.register(ScienceApplication, ScienceApplicationAdmin)


class ScienceApplicationUserReviewInline(admin.TabularInline):
    model = ScienceApplicationUserReview
    fk_name = "science_application_review"
    fields = ["reviewer", "finished", "grade"]
    autocomplete_fields = ["reviewer"]
    extra = 0
    show_change_link = True


@admin.register(ScienceApplicationReview)
class ScienceApplicationReviewAdmin(admin.ModelAdmin):
    inlines = [
        ScienceApplicationUserReviewInline,
    ]
    readonly_fields = ["mean_grade"]

    list_display = ["science_application", "review_panel", "science_category", "status", "mean_grade", "submitter_notified"]
    list_filter = ["status", "science_category", ("submitter_notified", admin.EmptyFieldListFilter)]
    search_fields = ["science_application__title"]
    autocomplete_fields = ["science_application", "review_panel", "primary_reviewer", "secondary_reviewer"]
    actions = ["notify_submitter"]

    @admin.action(description="Send accepted or rejected email to submitter")
    def notify_submitter(self, request, queryset):
      for x in queryset:
        try:
          x.send_review_accepted_or_rejected_email_to_submitter()
        except Exception as e:
          self.message_user(request, f"Failed to send notification for {x.science_application.title}: {e}", level="error")
        else:
          x.submitter_notified = datetime.now()
          x.save()
          self.message_user(request, f"Notification sent for {x.science_application.title}", level="info")

@admin.register(ScienceApplicationUserReview)
class ScienceApplicationUserReviewAdmin(admin.ModelAdmin):
    list_display = ["get_science_application", "reviewer", "finished", "grade"]
    list_filter = ["finished",]
    autocomplete_fields = ["science_application_review", "reviewer"]

    @admin.display(description="Application")
    def get_science_application(self, obj):
        return obj.science_application_review.science_application


class ReviewPanelMembershipInline(admin.TabularInline):
    model = ReviewPanelMembership
    extra = 1
    autocomplete_fields = ["user"]

class ReviewPanelScienceAppReviewInline(admin.TabularInline):
    model = ScienceApplicationReview
    extra = 0
    fields = ("title", "category",)
    readonly_fields = ("title", "category",)
    can_delete = False

    def has_add_permission(self, request, inst):
        return False

    @admin.display(description="Category")
    def category(self, inst):
        return inst.get_science_category_display()

    @admin.display(description="Title")
    def title(self, inst):
        return mark_safe('<a href="{}">{}</a>'.format(
            reverse("admin:sciapplications_scienceapplicationreview_change", args=(inst.pk,)),
            inst.science_application.title
        ))

@admin.register(ReviewPanel)
class ReviewPanelAdmin(admin.ModelAdmin):
    inlines = [ReviewPanelMembershipInline, ReviewPanelScienceAppReviewInline]
    list_display = ["name", "is_admin"]
    list_filter = ["is_admin"]
    search_fields = ["name"]
    actions = ["send_review_requested_emails"]

    @admin.action(description="Send review requested email to all panelists")
    def send_review_requested_emails(self, request, queryset):
      for x in queryset:
        try:
          x.send_review_requested_emails()
        except Exception as e:
          self.message_user(request, f"Failed to send emails for {x.name}: {e}", level="error")
        else:
          self.message_user(request, f"Emails sent for {x.name}", level="info")
