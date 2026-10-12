# Generated manually for report audit trails.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0011_systemnotification'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReportAuditLog',
            fields=[
                ('audit_id', models.AutoField(primary_key=True, serialize=False)),
                ('action', models.CharField(choices=[('CREATED', 'Created'), ('EDITED', 'Edited'), ('SUBMITTED', 'Submitted to CHO'), ('FORWARDED', 'Verified and forwarded'), ('VERIFIED', 'Verified'), ('REJECTED', 'Rejected')], max_length=20)),
                ('details', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='report_audit_actions', to=settings.AUTH_USER_MODEL)),
                ('community_report', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audit_logs', to='monitoring.communityreport')),
                ('dengue_case', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audit_logs', to='monitoring.denguecase')),
            ],
            options={'ordering': ['created_at', 'audit_id']},
        ),
    ]
