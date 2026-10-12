# Generated manually for resident barangay health-alert notifications.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0012_reportauditlog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='systemnotification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('REPORT', 'Community report'),
                    ('REPLY', 'CHO reply'),
                    ('ALERT', 'Barangay health alert'),
                    ('ASSIGNMENT', 'Area assignment'),
                    ('CASE', 'Case review'),
                ],
                max_length=20,
            ),
        ),
    ]
