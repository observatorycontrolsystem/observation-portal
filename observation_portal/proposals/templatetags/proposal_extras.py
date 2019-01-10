from django import template

register = template.Library()


@register.simple_tag
def time_used_by_user(user, proposal):
    return user.profile.time_used_in_proposal(proposal) / 3600
