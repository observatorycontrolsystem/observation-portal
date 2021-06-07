# Generated by Django 2.2.18 on 2021-06-04 21:55

from django.db import migrations


def forward(apps, schema_editor):
    # Fill in the instrument_types of TimeRequests based on the current instrument field
    TimeRequest = apps.get_model('sciapplications', 'TimeRequest')
    for time_request in TimeRequest.objects.all():
        time_request.instrument_types.add(time_request.instrument)
        time_request.save()


class Migration(migrations.Migration):

    dependencies = [
        ('sciapplications', '0002_timerequest_instrument_types'),
    ]

    operations = [
        migrations.RunPython(forward)
    ]