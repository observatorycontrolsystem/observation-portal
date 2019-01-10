from django import template
from boto3 import client
from botocore.client import Config
from django.conf import settings

register = template.Library()


@register.simple_tag
def time_requested_by_sca(sca, semester):
    return sca.time_requested_for_semester(semester)


@register.simple_tag
def file_to_s3_url(file):
    boto_client = client('s3', settings.AWS_REGION, config=Config(signature_version='s3v4'))
    url = boto_client.generate_presigned_url('get_object',
                                             Params={
                                                 'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                                                 'Key': settings.MEDIAFILES_DIR + '/' + str(file)
                                             }
                                             )
    return url