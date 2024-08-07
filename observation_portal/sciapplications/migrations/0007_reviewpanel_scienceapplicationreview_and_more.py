# Generated by Django 4.1.13 on 2024-07-10 22:26

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sciapplications', '0006_alter_instrument_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReviewPanel',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
            ],
        ),
        migrations.CreateModel(
            name='ScienceApplicationReview',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('science_category', models.CharField(choices=[('EXPLOSIVE_TRANSIENTS', 'Explosive Transients'), ('ACTIVE_GALAXIES', 'Active Galaxies'), ('STARS_STELLAR_ACTIVITY', 'Stars and Stellar Activity'), ('SOLAR_SYSTEM_SMALL_BODIES', 'Solar System Small Bodies'), ('MISC', 'Miscellaneous'), ('EXOPLANETS', 'Exoplanets')], default='MISC', max_length=255)),
                ('technical_review', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('AWAITING_REVIEWS', 'Awaiting Reviews'), ('PANEL_DISCUSSION', 'Panel Discussion'), ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected')], default='AWAITING_REVIEWS', max_length=255)),
                ('summary', models.TextField(blank=True, default='')),
                ('mean_grade', models.DecimalField(blank=True, decimal_places=2, default=None, help_text='Mean of all user reviews. This field is automatically recalculated anytime a user review is added/updated/deleted', max_digits=4, null=True)),
                ('notify_submitter', models.BooleanField(default=False, help_text='Whether to send the application submitter notifications regarding the acceptance or rejection of this review.')),
                ('notify_submitter_additional_message', models.TextField(blank=True, default='', help_text='Additional message to embed in notifications sent to the application submitter.')),
                ('primary_reviewer', models.ForeignKey(help_text='Primary reviewer', on_delete=django.db.models.deletion.CASCADE, related_name='primary_reviewer_for', to=settings.AUTH_USER_MODEL)),
                ('review_panel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='science_application_reviews', to='sciapplications.reviewpanel')),
                ('science_application', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='review', to='sciapplications.scienceapplication')),
                ('secondary_reviewer', models.ForeignKey(help_text='Secondary reviewer', on_delete=django.db.models.deletion.CASCADE, related_name='secondary_reviewer_for', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ScienceApplicationUserReview',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('comments', models.TextField(blank=True, default='')),
                ('finished', models.BooleanField(default=False)),
                ('grade', models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=4, null=True)),
                ('reviewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sciapplication_reviews', to=settings.AUTH_USER_MODEL)),
                ('science_application_review', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_reviews', to='sciapplications.scienceapplicationreview')),
            ],
        ),
        migrations.CreateModel(
            name='ReviewPanelMembership',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('review_panel', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='sciapplications.reviewpanel')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='reviewpanel',
            name='members',
            field=models.ManyToManyField(related_name='review_panels', through='sciapplications.ReviewPanelMembership', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name='scienceapplicationuserreview',
            constraint=models.UniqueConstraint(fields=('science_application_review', 'reviewer'), name='sciapplications_scienceapplicationuserreview_primary_key'),
        ),
    ]
