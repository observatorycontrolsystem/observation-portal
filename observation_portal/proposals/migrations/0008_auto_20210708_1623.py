# Generated by Django 2.2.23 on 2021-07-08 16:23

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('proposals', '0007_remove_timeallocation_instrument_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='proposal',
            name='tags',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=255), blank=True, default=list, help_text='List of strings tagging this proposal', size=None),
        ),
        migrations.AlterField(
            model_name='timeallocation',
            name='instrument_types',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=200), default=list, help_text='One or more instrument_types to share this time allocation', size=None),
        ),
    ]