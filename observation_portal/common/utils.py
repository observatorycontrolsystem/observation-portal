"""
utils.py - Common utility functions
"""

def get_queryset_field_values(queryset, field):
    """Get all the values for a field in a given queryset"""
    all_values = queryset.values_list(field, flat=True)
    values_set = set()
    for values in all_values:
        if values:
            values_set.update(values)
    return values_set
