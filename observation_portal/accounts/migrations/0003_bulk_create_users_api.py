# Generated by Django 4.0.3 on 2022-04-16 22:40

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0002_profile_terms_accepted'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='password_expiration',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='created_by',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_profiles', to=settings.AUTH_USER_MODEL),
        ),
    ]
