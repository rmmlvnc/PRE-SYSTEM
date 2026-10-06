# Generated manually to keep the mobile API models installable on a fresh database.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0005_useraccount_profile_picture'),
    ]

    operations = [
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('alert_id', models.AutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=150)),
                ('message', models.TextField()),
                ('risk_level', models.CharField(choices=[('LOW', 'Low'), ('MODERATE', 'Moderate'), ('HIGH', 'High'), ('CRITICAL', 'Critical')], max_length=10)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('barangay', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alerts', to='monitoring.barangay')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_alerts', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CommunityReport',
            fields=[
                ('community_report_id', models.AutoField(primary_key=True, serialize=False)),
                ('observation_type', models.CharField(max_length=100)),
                ('description', models.TextField()),
                ('latitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=7, max_digits=10, null=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('VERIFIED', 'Verified'), ('REJECTED', 'Rejected')], default='PENDING', max_length=10)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('barangay', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='community_reports', to='monitoring.barangay')),
                ('purok', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='community_reports', to='monitoring.purok')),
                ('resident', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='community_reports', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='MobileAccessToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_hash', models.CharField(max_length=64, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mobile_tokens', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AlterField(
            model_name='useraccount',
            name='role',
            field=models.CharField(choices=[('CHO', 'City Health Office (CHO)'), ('CHW', 'City Health Worker (CHW)'), ('BHW', 'Barangay Health Worker (BHW)'), ('LGU', 'Local Government Unit (LGU)'), ('RESIDENT', 'Resident')], default='BHW', max_length=10),
        ),
    ]
