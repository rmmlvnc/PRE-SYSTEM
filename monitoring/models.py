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
        ('Draft', 'Draft'),
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

    symptoms = models.TextField(
        blank=True,
        help_text='Observed symptoms reported or assessed by the CHW.'
    )

    location_details = models.TextField(
        blank=True,
        help_text='Street, landmark, or other location details for follow-up.'
    )

    reviewed_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_dengue_cases'
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    cho_review_note = models.TextField(
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
        ('FORWARDED', 'Forwarded to CHO'),
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
    bhw_review_note = models.TextField(blank=True)
    bhw_reviewed_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bhw_reviewed_community_reports',
    )
    bhw_reviewed_at = models.DateTimeField(null=True, blank=True)
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


class SystemNotification(models.Model):
    """An in-app notification owned by one DengueWatch user."""

    TYPE_CHOICES = [
        ('REPORT', 'Community report'),
        ('REPLY', 'CHO reply'),
        ('ASSIGNMENT', 'Area assignment'),
        ('CASE', 'Case review'),
    ]

    notification_id = models.AutoField(primary_key=True)
    recipient = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    created_by = models.ForeignKey(
        UserAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
    )
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=150)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class ReportAuditLog(models.Model):
    """Append-only record of actions taken on a community or suspected-case report."""

    ACTION_CHOICES = [
        ('CREATED', 'Created'),
        ('EDITED', 'Edited'),
        ('SUBMITTED', 'Submitted to CHO'),
        ('FORWARDED', 'Verified and forwarded'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
    ]

    audit_id = models.AutoField(primary_key=True)
    community_report = models.ForeignKey(
        CommunityReport, on_delete=models.CASCADE, null=True, blank=True,
        related_name='audit_logs',
    )
    dengue_case = models.ForeignKey(
        DengueCase, on_delete=models.CASCADE, null=True, blank=True,
        related_name='audit_logs',
    )
    actor = models.ForeignKey(
        UserAccount, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='report_audit_actions',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'audit_id']


def log_report_action(*, actor, action, details='', community_report=None, dengue_case=None):
    """Record a report state change; callers never update or delete audit rows."""
    return ReportAuditLog.objects.create(
        actor=actor,
        action=action,
        details=details,
        community_report=community_report,
        dengue_case=dengue_case,
    )


def notify_user(recipient, notification_type, title, message, *, created_by=None, link=''):
    """Store a notification. This is intentionally in-app, not a medical emergency channel."""
    return SystemNotification.objects.create(
        recipient=recipient,
        created_by=created_by,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link,
    )


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
