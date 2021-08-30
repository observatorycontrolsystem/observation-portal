from rest_framework import serializers
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.schemas.utils import is_list_view

class ObservationPortalSchema(AutoSchema):
    def __init__(self, tags, operation_id_base=None, component_name=None, empty_request=False, is_list_view=True):
        super().__init__(tags=tags, operation_id_base=operation_id_base, component_name=component_name)
        self.empty_request = empty_request
        self.is_list_view = is_list_view

    def get_operation(self, path, method):
        operations =  super().get_operation(path, method)
        # If the view has implemented get_example_response, then use it to present in the documentation
        if getattr(self.view, 'get_example_response', None) is not None:
            example_response = self.view.get_example_response()
            status_code = '201' if method == 'POST' else '200'
            if example_response is not None:
                operations['responses'] = {status_code: {'content': {'application/json': {'example': example_response}}}}

        # If the view has implemented get_example_request, then use it to present in the documentation
        if getattr(self.view, 'get_example_request', None) is not None:
            example_request = self.view.get_example_request()
            if example_request is not None:
                operations['requestBody'] = example_request

        if self.empty_request:
            operations['requestBody'] = {}

        return operations

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

        if not hasattr(view, 'get_response_serializer'):
            return view.get_serializer()
        else:
            return view.get_response_serializer()

    def get_response_serializer(self, path, method):
        view = self.view

        if not hasattr(view, 'get_request_serializer'):
            return view.get_serializer()
        else:
            return view.get_request_serializer()

    def get_request_body(self, path, method):
        if method not in ('PUT', 'PATCH', 'POST'):
            return {}

        self.request_media_types = self.map_parsers(path, method)

        serializer = self.get_response_serializer(path, method)

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

        serializer = self.get_request_serializer(path, method)

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
