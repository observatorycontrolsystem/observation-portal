# Generated by Django 4.0.2 on 2022-04-05 23:26

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0006_alter_summary_events'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='configurationstatus',
            unique_together=set(),
        ),
    ]