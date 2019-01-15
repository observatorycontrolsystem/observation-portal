from django import template
from observation_portal.common.configdb import configdb

register = template.Library()


@register.filter
def state_to_bs(value):
    state_map = {
        'PENDING': 'warning',
        'SCHEDULED': 'info',
        'COMPLETED': 'success',
        'WINDOW_EXPIRED': 'danger',
        'CANCELED': 'danger',
    }
    return state_map[value]


@register.filter
def state_to_icon(value):
    state_map = {
        'PENDING': 'refresh',
        'SCHEDULED': 'refresh',
        'COMPLETED': 'check',
        'WINDOW_EXPIRED': 'times',
        'CANCELED': 'times',
    }
    return state_map[value]


@register.filter
def request_state_count(requestgroup, state):
    return requestgroup.requests.filter(state=state).count()


@register.filter
def instrument_code_to_name(instrument_code):
    return configdb.get_instrument_name(instrument_code)
