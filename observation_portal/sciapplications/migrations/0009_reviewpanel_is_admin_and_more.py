# Generated by Django 4.1.13 on 2024-11-21 22:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sciapplications', '0008_scienceapplicationreview_pdf'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewpanel',
            name='is_admin',
            field=models.BooleanField(default=False, help_text='All members of an admin panel will have access to all reviews'),
        ),
        migrations.AddConstraint(
            model_name='reviewpanel',
            constraint=models.UniqueConstraint(condition=models.Q(('is_admin', True)), fields=('is_admin',), name='sciapplications_reviewpanel_is_admin', violation_error_message='Only one review panel can be designated as an admin panel'),
        ),
    ]