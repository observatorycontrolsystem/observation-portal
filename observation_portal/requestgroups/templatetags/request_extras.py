from django import template
from observation_portal.common.configdb import configdb

register = template.Library()


@register.filter
def state_to_bs(value):
    state_map = {
        'PENDING': 'neutral',
        'SCHEDULED': 'info',
        'COMPLETED': 'success',
        'WINDOW_EXPIRED': 'danger',
        'CANCELED': 'danger',
    }
    return state_map[value]


@register.filter
def state_to_icon(value):
    state_map = {
        'PENDING': 'sync',
        'SCHEDULED': 'sync',
        'COMPLETED': 'check',
        'WINDOW_EXPIRED': 'times',
        'CANCELED': 'times',
    }
    return state_map[value]


@register.filter
def request_state_count(requestgroup, state):
    return requestgroup.requests.filter(state=state).count()


@register.filter
def instrument_type_to_full_name(instrument_code):
    return configdb.get_instrument_type_full_name(instrument_code)
