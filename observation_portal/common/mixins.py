from django_filters import fields, IsoDateTimeFilter
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils import formats


class ListAsDictMixin(object):
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        json_models = [model.as_dict() for model in page]
        return self.get_paginated_response(json_models)


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
    input_formats = [fields.IsoDateTimeField.ISO_8601] + list(formats.get_format_lazy('DATETIME_INPUT_FORMATS'))


class CustomIsoDateTimeFilterMixin(object):
    @classmethod
    def get_filters(cls):
        filters = super().get_filters()
        for f in filters.values():
            if isinstance(f, IsoDateTimeFilter):
                f.field_class = CustomIsoDateTimeField
        return filters
