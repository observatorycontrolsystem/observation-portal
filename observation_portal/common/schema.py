from rest_framework.schemas.openapi import AutoSchema

class ObservationPortalSchema(AutoSchema):
    def __init__(self, tags, operation_id_base=None, component_name=None, empty_request=False, is_list_view=True):
        super().__init__(tags=tags, operation_id_base=operation_id_base, component_name=component_name)
        self.empty_request = empty_request
        self.is_list_view = is_list_view

    def get_operation(self, path, method):
        operations =  super().get_operation(path, method)        
        if self.empty_request:
            operations['requestBody'] = {}

        return operations

    def get_responses(self, path, method):
        responses = super().get_responses(path, method)
        if not self.is_list_view:
            list_items = responses['200']['content']['application/json']['schema'].pop('items')
            del responses['200']['content']['application/json']['schema']['type']
            responses['200']['content']['application/json']['schema'] = list_items

        return responses
