# Keeps the database schema aligned with the dataset and weather relations in models.py.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0006_alert_communityreport_mobileaccesstoken_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='integrateddenguedataset',
            name='barangay',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='integrated_datasets', to='monitoring.barangay'),
        ),
        migrations.AddField(
            model_name='integrateddenguedataset',
            name='weather',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='integrated_datasets', to='monitoring.weather'),
        ),
        migrations.AddField(
            model_name='weather',
            name='barangay',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='weather_records', to='monitoring.barangay'),
        ),
    ]
