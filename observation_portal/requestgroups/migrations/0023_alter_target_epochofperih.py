# Generated by Django 4.0.4 on 2023-03-28 17:54

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('requestgroups', '0022_alter_constraints_max_seeing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='target',
            name='epochofperih',
            field=models.FloatField(blank=True, help_text='Epoch of perihelion (MJD)', null=True, validators=[django.core.validators.MinValueValidator(361), django.core.validators.MaxValueValidator(240000)], verbose_name='epoch of perihelion'),
        ),
    ]