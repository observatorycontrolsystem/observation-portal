from rest_framework.schemas.openapi import AutoSchema

class ObservationPortalSchema(AutoSchema):
    def __init__(self, tags, operation_id_base=None, component_name=None, empty_request=False):
        super().__init__(tags=tags, operation_id_base=operation_id_base, component_name=component_name)
        self.empty_request = empty_request

    def get_operation(self, path, method):
        operations =  super().get_operation(path, method)        
        if self.empty_request:
            operations['requestBody'] = {}

        return operations
