from django.template.loader import render_to_string

from observation_portal.accounts.tasks import send_mass_mail
from django.conf import settings


def users_to_notify(requestgroup):
    all_proposal_users = set(requestgroup.proposal.users.filter(profile__notifications_enabled=True))
    single_proposal_users = set(pn.user for pn in requestgroup.proposal.proposalnotification_set.all())
    return [
        user for user in all_proposal_users.union(single_proposal_users)
        if not user.profile.notifications_on_authored_only or
        (user.profile.notifications_on_authored_only and requestgroup.submitter == user)
    ]


def request_notifications(request):
    if request.state == 'FAILURE_LIMIT_REACHED':
        message = render_to_string(
            'proposals/requestfailurelimit.txt',
            {
                'request': request,
                'detail_url': settings.REQUEST_DETAIL_URL.format(request_id=request.id),
                'max_failure_limit': settings.MAX_FAILURES_PER_REQUEST
            }
        )
        email_messages = []
        for user in users_to_notify(request.request_group):
            email_tuple = (
                f'Request #{request.id} has failed {settings.MAX_FAILURES_PER_REQUEST} times and will not be rescheduled',
                message,
                'portal@lco.global',
                [user.email]
            )
            email_messages.append(email_tuple)
        if email_messages:
            send_mass_mail.send(email_messages)


def requestgroup_notifications(requestgroup):
    if requestgroup.state == 'COMPLETED':
        message = render_to_string(
            'proposals/requestgroupcomplete.txt',
            {
                'requestgroup': requestgroup,
                'download_url': settings.REQUESTGROUP_DATA_DOWNLOAD_URL.format(requestgroup_id=requestgroup.id)
            }
        )
        email_messages = []
        for user in users_to_notify(requestgroup):
            email_tuple = (
                'Request {} has completed'.format(requestgroup.name),
                message,
                'portal@lco.global',
                [user.email]
            )
            email_messages.append(email_tuple)
        if email_messages:
            send_mass_mail.send(email_messages)
