from django_filters import fields, IsoDateTimeFilter
from django.contrib.auth.mixins import UserPassesTestMixin
from django.forms import DateTimeField
from rest_framework.response import Response


class ListAsDictMixin(object):
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        json_models = [model.as_dict() for model in page]
        return self.get_paginated_response(json_models)


class DetailAsDictMixin:
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(instance.as_dict())


# from https://stackoverflow.com/questions/14666199/how-do-i-create-multiple-model-instances-with-django-rest-framework
class CreateListModelMixin(object):
    def get_serializer(self, *args, **kwargs):
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super().get_serializer(*args, **kwargs)


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


# Use the CustomIsoDateTimeFilterMixin in a FilterSet. Makes all IsoDateTimeFilters within the FilterSet able to parse
# ISO 8601 datetimes, as well as all the other usual formats that the DateTimeFilter can do.
# https://django-filter.readthedocs.io/en/master/ref/fields.html#isodatetimefield
class CustomIsoDateTimeField(fields.IsoDateTimeField):
    input_formats = [fields.IsoDateTimeField.ISO_8601] + list(DateTimeField.input_formats)


class CustomIsoDateTimeFilterMixin(object):
    @classmethod
    def get_filters(cls):
        filters = super().get_filters()
        for f in filters.values():
            if isinstance(f, IsoDateTimeFilter):
                f.field_class = CustomIsoDateTimeField
        return filters


class ExtraParamsFormatter(object):
    """ This should be mixed in with Serializers that have extra_params JSON fields, to ensure the float values are
        stored as float values in the db instead of as strings
    """
    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        for field, value in data.get('extra_params', {}).items():
            try:
                data['extra_params'][field] = float(value)
            except (ValueError, TypeError):
                pass
        return data
