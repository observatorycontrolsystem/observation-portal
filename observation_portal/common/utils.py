"""
utils.py - Common utility functions
"""
import json
import hashlib
from functools import wraps
from django.core.serializers.json import DjangoJSONEncoder
from django.core.cache import caches


def get_queryset_field_values(queryset, field):
    """Get all the values for a field in a given queryset"""
    all_values = queryset.values_list(field, flat=True)
    values_set = set()
    for values in all_values:
        if values:
            values_set.update(values)
    return values_set

# Decorator to cache the value of the function - defaults to the locmem cache for 5 minutes
def cache_function(cache_name='locmem', duration=300):
    def cache_decorator(method):
        @wraps(method)
        def inner_funcion(*args, **kwargs):
            cache_key = method.__name__
            for arg in args:
                if isinstance(arg, dict):
                    cache_key += '_' + hashlib.sha1(json.dumps(arg, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()
                elif isinstance(arg, (int, float, bool, str, list, set)):
                    cache_key += '_' + str(arg)
            for kwarg in kwargs.values():
                if isinstance(kwarg, dict):
                    cache_key += '_' + hashlib.sha1(json.dumps(kwarg, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()
                elif isinstance(kwarg, (int, float, bool, str, list, set)):
                    cache_key += '_' + str(kwarg)
            cached_output = caches[cache_name].get(cache_key, None)
            if cached_output:
                return cached_output
            output = method(*args, **kwargs)
            caches[cache_name].set(cache_key, output, duration)
            return output
        return inner_funcion
    return cache_decorator
