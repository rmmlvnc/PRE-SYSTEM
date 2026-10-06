from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import hashlib
import secrets
from datetime import timedelta


class Barangay(models.Model):
    barangay_id = models.AutoField(primary_key=True)
    barangay_name = models.CharField(max_length=100)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    def __str__(self):
        return self.barangay_name


class Purok(models.Model):
    purok_id = models.AutoField(primary_key=True)

    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.CASCADE,
        related_name="puroks"
    )

    purok_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.purok_name} - {self.barangay.barangay_name}"


class UserAccount(AbstractUser):

    ROLE_CHOICES = [
        ('CHO', 'City Health Office (CHO)'),
        ('CHW', 'City Health Worker (CHW)'),
        ('BHW', 'Barangay Health Worker (BHW)'),
        ('LGU', 'Local Government Unit (LGU)'),
        ('RESIDENT', 'Resident'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    assigned_barangay = models.ForeignKey(
        Barangay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_bhws'
    )

    assigned_purok = models.ForeignKey(
        Purok,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_bhws'
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='BHW'
    )

    account_status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    profile_picture = models.ImageField(
        upload_to='profile_pictures/',
        blank=True,
        null=True
    )

    contact_number = models.CharField(
        max_length=20,
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    def __str__(self):
        return f"{self.username} - {self.role}"

class DengueCase(models.Model):

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Active', 'Active'),
        ('Recovered', 'Recovered'),
        ('Rejected', 'Rejected'),
    ]

    dengue_case_id = models.AutoField(primary_key=True)

    user_account = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name="dengue_cases"
    )

    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dengue_cases"
    )

    purok = models.ForeignKey(
        Purok,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dengue_cases"
    )

    patient_age = models.IntegerField()

    patient_sex = models.CharField(
        max_length=20
    )

    patient_blood_type = models.CharField(
        max_length=5,
        blank=True
    )

    date_reported = models.DateField()

    case_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending'
    )

    remarks = models.TextField(
        blank=True
    )

    case_count = models.IntegerField(
        default=1
    )

    def __str__(self):
        return f"Dengue Case #{self.dengue_case_id}"

class IntegratedDengueDataset(models.Model):
    integrated_dengue_dataset_id = models.AutoField(primary_key=True)

    dengue_case = models.ForeignKey(
        DengueCase,
        on_delete=models.CASCADE,
        related_name="integrated_datasets"
    )

    weather = models.ForeignKey(
        'Weather',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="integrated_datasets"
    )

    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="integrated_datasets"
    )

    processed_date = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Dataset #{self.integrated_dengue_dataset_id}"


class HotspotPrediction(models.Model):
    hotspot_prediction_id = models.AutoField(primary_key=True)

    integrated_dengue_dataset = models.ForeignKey(
        IntegratedDengueDataset,
        on_delete=models.CASCADE,
        related_name="predictions"
    )

    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.CASCADE,
        related_name="hotspot_predictions"
    )

    prediction_date = models.DateField()

    risk_score = models.FloatField(
        null=True,
        blank=True
    )

    hotspot_level = models.CharField(
        max_length=50,
        blank=True
    )

    forecast_result = models.TextField(
        blank=True
    )

    analysis_remarks = models.TextField(
        blank=True
    )

    risk_level = models.CharField(
        max_length=50,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.barangay} - {self.risk_level}"


class Weather(models.Model):
    report_id = models.AutoField(primary_key=True)

    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="weather_records"
    )

    temperature = models.FloatField()
    rainfall = models.FloatField()
    humidity = models.FloatField()
    date = models.DateField()

    def __str__(self):
        return f"Weather - {self.date}"


class Report(models.Model):
    report_id = models.AutoField(primary_key=True)

    hotspot_prediction = models.ForeignKey(
        HotspotPrediction,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    report_type = models.CharField(
        max_length=100
    )

    recommendation = models.TextField(
        blank=True
    )

    generated_date = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.report_type


class CommunityReport(models.Model):
    """Resident observation; it is not counted as a confirmed dengue case."""

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
    ]

    community_report_id = models.AutoField(primary_key=True)
    resident = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name='community_reports'
    )
    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.CASCADE,
        related_name='community_reports'
    )
    purok = models.ForeignKey(
        Purok,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='community_reports'
    )
    observation_type = models.CharField(max_length=100)
    description = models.TextField()
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    staff_response = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_community_reports',
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class Alert(models.Model):
    RISK_CHOICES = [
        ('LOW', 'Low'),
        ('MODERATE', 'Moderate'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]

    alert_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=150)
    message = models.TextField()
    risk_level = models.CharField(max_length=10, choices=RISK_CHOICES)
    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts'
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_alerts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)


class MobileAccessToken(models.Model):
    """Hashed bearer token used by the React Native application."""

    user = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name='mobile_tokens')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user, days=30):
        raw_token = secrets.token_urlsafe(32)
        cls.objects.create(
            user=user,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(days=days),
        )
        return raw_token

    @classmethod
    def authenticate(cls, raw_token):
        if not raw_token:
            return None
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        token = cls.objects.select_related('user').filter(
            token_hash=token_hash,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
            user__is_active=True,
        ).first()
        return token.user if token else None
