# -*- coding: utf-8 -*-
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse


from .models import (
    Instrument, Call, ScienceApplication, TimeRequest, CoInvestigator,
    NoTimeAllocatedError, MultipleTimesAllocatedError
)
from observation_portal.proposals.models import Proposal


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


class ScienceApplicationAdmin(admin.ModelAdmin):
    inlines = [CoInvestigatorInline, TimeRequestAdminInline]
    list_display = (
        'title',
        'call',
        'status',
        'submitter',
        'tac_rank',
        'preview_link',
    )
    list_filter = ('call', 'status', 'call__proposal_type')
    actions = ['accept', 'reject', 'port']
    search_fields = ['title', 'abstract', 'submitter__first_name', 'submitter__last_name', 'submitter__username']

    def preview_link(self, obj):
        return format_html(
            '<a href="{}">View on site</a>',
            reverse('api:scienceapplications-detail', kwargs={'pk': obj.id})
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

admin.site.register(ScienceApplication, ScienceApplicationAdmin)
