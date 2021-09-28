from rest_framework import serializers
from rest_framework.schemas.openapi import AutoSchema, SchemaGenerator
from rest_framework.schemas.utils import is_list_view
from rest_framework.viewsets import GenericViewSet
from setuptools_scm import get_version
from setuptools_scm.version import ScmVersion


def version_scheme(version: ScmVersion) -> str:
    """Simply return the string representation of the version object tag, which is the latest git tag.
    setuptools_scm does not provide a simple semantic versioning format without trying to guess the next release, or adding some metadata to the version.
    """
    return str(version.tag)


class ObservationPortalSchemaGenerator(SchemaGenerator):
    def get_schema(self, *args, **kwargs):
        schema = super().get_schema(*args, **kwargs)
        schema['info']['title'] = 'Observation Portal'
        schema['info']['version'] = get_version(version_scheme=version_scheme, local_scheme='no-local-version')
        return schema

    def has_view_permissions(self, path, method, view):
        # For viewsets, we'd like to be able to define actions that won't be listed in the API docs.
        if isinstance(view, GenericViewSet):
            # For each endpoint in a ViewSet, DRF generates a separate view with an action.
            if view.action in getattr(view, 'undocumented_actions', []):
                return False
        return super().has_view_permissions(path, method, view)


class ObservationPortalSchema(AutoSchema):
    def __init__(self, tags, operation_id_base=None, component_name=None, empty_request=False, is_list_view=True):
        super().__init__(tags=tags, operation_id_base=operation_id_base, component_name=component_name)
        self.empty_request = empty_request
        self.is_list_view = is_list_view

    def get_operation_id(self, path, method):
        """
        This method is used to determine the descriptive name of the endpoint displayed in the documentation.
        Allow this to be overridden in the view - a view that defines get_endpoint_name can override the default
        DRF naming scheme.
        """
        operation_id = super().get_operation_id(path, method)
        if getattr(self.view, 'get_endpoint_name', None) is not None:
            name_override = self.view.get_endpoint_name()
            # For some viewsets, we may not have specified a name for an action - guard against that
            if name_override is not None:
                operation_id = name_override

        return operation_id

    def get_operation(self, path, method):
        """
        This method is used to determine, among other things, the request and response bodies for a particular endpoint.
        We override this to support specifying our own request and response bodies. Any view that implements get_example_response
        and/or get_example_request can provide their own custom request and response bodies to display in the OpenAPI docs.
        """
        operations =  super().get_operation(path, method)
        # If the view has implemented get_example_response, then use it to present in the documentation
        if getattr(self.view, 'get_example_response', None) is not None:
            example_response = self.view.get_example_response()
            # For viewsets, not all actions may have example responses defined, so this method may return None
            if example_response is not None:
                status_code = example_response.status_code
                example_data = example_response.data
                operations['responses'] = {status_code: {'content': {'application/json': {'example': example_data}}}}

        # If the view has implemented get_example_request, then use it to present in the documentation
        if getattr(self.view, 'get_example_request', None) is not None:
            example_request = self.view.get_example_request()
            if example_request is not None:
                operations['requestBody'] = example_request

        if self.empty_request:
            operations['requestBody'] = {}

        return operations


    # The following class methods are based off a change merged to master in the DRF repository
    # that allows for the specification of separate request and response serializers for view introspection.
    # See https://github.com/encode/django-rest-framework/pull/7424

    # These overrides can be removed once a new release containing these changes is available.
    # TODO: Remove these when the next version of DRF is released

    def get_components(self, path, method):
        request_serializer = self.get_request_serializer(path, method)
        response_serializer = self.get_response_serializer(path, method)

        components = {}

        if isinstance(request_serializer, serializers.Serializer):
            component_name = self.get_component_name(request_serializer)
            content = self.map_serializer(request_serializer)
            components.setdefault(component_name, content)

        if isinstance(response_serializer, serializers.Serializer):
            component_name = self.get_component_name(response_serializer)
            content = self.map_serializer(response_serializer)
            components.setdefault(component_name, content)

        return components

    def get_request_serializer(self, path, method):
        view = self.view

        if not hasattr(view, 'get_request_serializer'):
            if not hasattr(view, 'get_serializer'):
                # If this view doesn't have a serializer, then we can't auto-document this endpoint
                return None
            else:
                return view.get_serializer()
        else:
            return view.get_request_serializer()

    def get_response_serializer(self, path, method):
        view = self.view

        if not hasattr(view, 'get_response_serializer'):
            if not hasattr(view, 'get_serializer'):
                # If this view doesn't have a serializer, then we can't auto-document this endpoint
                return None
            else:
                return view.get_serializer()
        else:
            return view.get_response_serializer()

    def get_request_body(self, path, method):
        if method not in ('PUT', 'PATCH', 'POST'):
            return {}

        self.request_media_types = self.map_parsers(path, method)

        serializer = self.get_request_serializer(path, method)

        if not isinstance(serializer, serializers.Serializer):
            item_schema = {}
        else:
            item_schema = self._get_reference(serializer)

        return {
            'content': {
                ct: {'schema': item_schema}
                for ct in self.request_media_types
            }
        }

    def get_responses(self, path, method):
        if method == 'DELETE':
            return {
                '204': {
                    'description': ''
                }
            }

        self.response_media_types = self.map_renderers(path, method)

        serializer = self.get_response_serializer(path, method)

        if not isinstance(serializer, serializers.Serializer):
            item_schema = {}
        else:
            item_schema = self._get_reference(serializer)

        if is_list_view(path, method, self.view) and self.is_list_view:
            response_schema = {
                'type': 'array',
                'items': item_schema,
            }
            paginator = self.get_paginator()
            if paginator:
                response_schema = paginator.get_paginated_response_schema(response_schema)
        else:
            response_schema = item_schema
        status_code = '201' if method == 'POST' else '200'
        return {
            status_code: {
                'content': {
                    ct: {'schema': response_schema}
                    for ct in self.response_media_types
                },
                # description is a mandatory property,
                # https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#responseObject
                # TODO: put something meaningful into it
                'description': ""
            }
        }
