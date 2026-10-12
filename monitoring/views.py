# =========================================================
# DENGUEWATCH - VIEWS.PY
# =========================================================

import csv
import json
import re

from datetime import date
from pathlib import Path
from collections import Counter

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import (
    UserAccount,
    DengueCase,
    Barangay,
    Purok,
    CommunityReport,
    Alert,
    SystemNotification,
    notify_user,
    log_report_action,
)
from .ml.service import prediction_context
from .locations import ILIGAN_BARANGAYS, canonicalize_barangay


# =========================================================
# ROLE ACCESS HELPER
# =========================================================

def role_required(*allowed_roles):
    """
    Restrict a view to specific user roles.

    Example:
        @role_required('CHO')
        @role_required('CHO', 'CHW', 'BHW')
        @role_required('LGU')
    """

    def decorator(view_func):

        @login_required(login_url='login')
        def wrapper(request, *args, **kwargs):

            user_role = getattr(
                request.user,
                'role',
                None
            )

            if user_role not in allowed_roles:

                messages.error(
                    request,
                    'You are not authorized to access this page.'
                )

                return redirect('dashboard')

            return view_func(
                request,
                *args,
                **kwargs
            )

        return wrapper

    return decorator


# =========================================================
# HOME
# =========================================================

def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


# =========================================================
# REGISTER
# =========================================================

def register(request):

    if request.user.is_authenticated:

        return redirect('dashboard')

    if request.method == 'POST':

        first_name = request.POST.get(
            'first_name',
            ''
        ).strip()

        last_name = request.POST.get(
            'last_name',
            ''
        ).strip()

        username = request.POST.get(
            'username',
            ''
        ).strip()

        email = request.POST.get(
            'email',
            ''
        ).strip()

        contact_number = request.POST.get(
            'contact_number',
            ''
        ).strip()

        address = request.POST.get(
            'address',
            ''
        ).strip()

        role = request.POST.get(
            'role',
            ''
        ).strip()

        password1 = request.POST.get(
            'password1',
            ''
        )

        password2 = request.POST.get(
            'password2',
            ''
        )

        # -------------------------------------------------
        # REQUIRED FIELDS
        # -------------------------------------------------

        if not first_name or not last_name:

            messages.error(
                request,
                'Please enter your first and last name.'
            )

            return redirect('register')

        if not username:

            messages.error(
                request,
                'Username is required.'
            )

            return redirect('register')

        if not email:

            messages.error(
                request,
                'Email address is required.'
            )

            return redirect('register')

        if not role:

            messages.error(
                request,
                'Please select your role.'
            )

            return redirect('register')

        # -------------------------------------------------
        # VALID ROLE
        # -------------------------------------------------

        allowed_roles = [
            'CHO',
            'CHW',
            'BHW',
            'LGU'
        ]

        if role not in allowed_roles:

            messages.error(
                request,
                'Invalid role selected.'
            )

            return redirect('register')

        # -------------------------------------------------
        # USERNAME
        # -------------------------------------------------

        if UserAccount.objects.filter(
            username=username
        ).exists():

            messages.error(
                request,
                'Username already exists.'
            )

            return redirect('register')

        # -------------------------------------------------
        # EMAIL
        # -------------------------------------------------

        if UserAccount.objects.filter(
            email=email
        ).exists():

            messages.error(
                request,
                'Email is already registered.'
            )

            return redirect('register')

        # -------------------------------------------------
        # PASSWORD
        # -------------------------------------------------

        if len(password1) < 8:

            messages.error(
                request,
                'Password must contain at least 8 characters.'
            )

            return redirect('register')

        if password1 != password2:

            messages.error(
                request,
                'Passwords do not match.'
            )

            return redirect('register')

        # -------------------------------------------------
        # CREATE ACCOUNT
        # -------------------------------------------------

        UserAccount.objects.create(

            username=username,

            email=email,

            first_name=first_name,

            last_name=last_name,

            contact_number=contact_number,

            address=address,

            role=role,

            account_status='PENDING',

            password=make_password(
                password1
            ),

            is_active=False
        )

        messages.success(
            request,
            'Registration submitted successfully. '
            'Your account is now pending approval '
            'by the City Health Office.'
        )

        return redirect('login')

    return render(
        request,
        'register.html'
    )


# =========================================================
# LOGIN
# =========================================================

def login_view(request):

    if request.user.is_authenticated:

        return redirect('dashboard')

    if request.method == 'POST':

        username = request.POST.get(
            'username',
            ''
        ).strip()

        password = request.POST.get(
            'password',
            ''
        )

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is None:

            messages.error(
                request,
                'Invalid username or password.'
            )

            return render(
                request,
                'login.html'
            )

        # Residents use only the React Native mobile application.
        # The desktop web system is reserved for health and LGU personnel.
        if user.role == 'RESIDENT':

            messages.error(
                request,
                'Resident accounts can only sign in through the '
                'DengueWatch mobile application.'
            )

            return render(
                request,
                'login.html'
            )

        # -------------------------------------------------
        # ACCOUNT STATUS
        # -------------------------------------------------

        if user.account_status == 'PENDING':

            messages.warning(
                request,
                'Your account is still pending approval. '
                'Please wait for the City Health Office.'
            )

            return render(
                request,
                'login.html'
            )

        if user.account_status == 'REJECTED':

            messages.error(
                request,
                'Your registration request was rejected.'
            )

            return render(
                request,
                'login.html'
            )

        if user.account_status != 'APPROVED':

            messages.error(
                request,
                'Your account is not authorized to access DengueWatch.'
            )

            return render(
                request,
                'login.html'
            )

        # -------------------------------------------------
        # LOGIN
        # -------------------------------------------------

        login(
            request,
            user
        )

        return redirect('dashboard')

    return render(
        request,
        'login.html'
    )


# =========================================================
# DASHBOARD ROUTER
# =========================================================

@login_required(login_url='login')
def dashboard(request):

    role = getattr(
        request.user,
        'role',
        None
    )

    if role == 'CHO':

        return redirect(
            'cho_dashboard'
        )

    elif role == 'CHW':

        return redirect(
            'chw_dashboard'
        )

    elif role == 'BHW':

        return redirect(
            'bhw_dashboard'
        )

    elif role == 'LGU':

        return redirect(
            'lgu_dashboard'
        )

    messages.error(
        request,
        'Your account has no valid assigned role.'
    )

    logout(request)

    return redirect('login')


# =========================================================
# CHO DASHBOARD
# CHO ONLY
# =========================================================

@role_required('CHO')
def cho_dashboard(request):

    cases_data = load_dengue_cases()

    # -----------------------------------------------------
    # TOTAL CASES
    # -----------------------------------------------------

    total_cases = len(
        cases_data
    )

    # -----------------------------------------------------
    # CURRENT YEAR
    # -----------------------------------------------------

    current_year_cases = sum(
        1
        for case in cases_data
        if str(
            case.get('year', '')
        ) == str(timezone.localdate().year)
    )

    # -----------------------------------------------------
    # PENDING USERS
    # -----------------------------------------------------

    pending_users = UserAccount.objects.filter(
        account_status='PENDING'
    ).count()

    # CHW reports become official case counts only after the CHO confirms
    # them. Keep the review queue visible to the final verifier, while the
    # confirmed count makes the live-data flow explicit on this dashboard.
    pending_case_reviews = DengueCase.objects.filter(
        user_account__role='CHW',
        case_status='Pending',
    ).count()

    confirmed_web_cases = DengueCase.objects.filter(
        user_account__role='CHW',
        case_status='Confirmed',
    ).count()

    # -----------------------------------------------------
    # LOCATION COUNTS
    # -----------------------------------------------------

    location_counts = Counter()

    for case in cases_data:

        barangay = str(
            case.get(
                'barangay',
                ''
            )
        ).strip()

        purok = str(
            case.get(
                'purok',
                ''
            )
        ).strip()

        if not barangay:

            barangay = 'Unknown Barangay'

        if not purok:

            purok = (
                'Unknown Sitio / Purok / Street'
            )

        location_counts[
            (
                barangay,
                purok
            )
        ] += 1

    monitored_locations = len(
        location_counts
    )

    high_risk_count = sum(
        1
        for count in location_counts.values()
        if count >= 5
    )

    predicted_hotspots = sum(
        1
        for count in location_counts.values()
        if count >= 5
    )

    context = {

        'total_cases':
            total_cases,

        'current_year_cases':
            current_year_cases,

        'pending_users':
            pending_users,

        'pending_case_reviews':
            pending_case_reviews,

        'confirmed_web_cases':
            confirmed_web_cases,

        'hotspot_count':
            predicted_hotspots,

        'high_risk_count':
            high_risk_count,

        'monitored_locations':
            monitored_locations,
    }

    return render(
        request,
        'cho_dashboard.html',
        context
    )

# =========================================================
# CHO BARANGAY & PUROK MANAGEMENT
# CHO ONLY
# =========================================================

@role_required('CHO')
def barangay_purok(request):

    # ==========================================
    # ALL BARANGAYS
    # ==========================================

    barangay_queryset = (
        Barangay.objects
        .prefetch_related('puroks')
        .all()
        .order_by('barangay_name')
    )

    # IMPORTANT:
    # This is used by dropdowns.
    # Keep ALL barangays here.
    all_barangays = (
        Barangay.objects
        .all()
        .order_by('barangay_name')
    )

    # ==========================================
    # STATISTICS
    # ==========================================

    total_barangays = barangay_queryset.count()

    total_puroks = Purok.objects.count()

    bhw_users = UserAccount.objects.filter(
        role='BHW',
        account_status='APPROVED'
    )

    assigned_bhws = bhw_users.filter(
        assigned_barangay__isnull=False
    ).count()

    unassigned_bhws = bhw_users.filter(
        assigned_barangay__isnull=True
    ).count()

    # ==========================================
    # PAGINATION
    # 50 BARANGAYS PER PAGE
    # ==========================================

    paginator = Paginator(
        barangay_queryset,
        50
    )

    page_number = request.GET.get(
        'page'
    )

    barangays = paginator.get_page(
        page_number
    )

    # ==========================================
    # CONTEXT
    # ==========================================

    context = {

        # Paginated table
        'barangays':
            barangays,

        # ALL barangays for dropdowns
        'all_barangays':
            all_barangays,

        'total_barangays':
            total_barangays,

        'total_puroks':
            total_puroks,

        'assigned_bhws':
            assigned_bhws,

        'unassigned_bhws':
            unassigned_bhws,
    }

    return render(
        request,
        'barangay_purok.html',
        context
    )

# =========================================================
# ADD BARANGAY
# CHO ONLY
# =========================================================

@role_required('CHO')
def add_barangay(request):

    if request.method != 'POST':
        return redirect('barangay_purok')

    barangay_name = request.POST.get(
        'barangay_name',
        ''
    ).strip()

    latitude = request.POST.get(
        'latitude',
        ''
    ).strip()

    longitude = request.POST.get(
        'longitude',
        ''
    ).strip()

    if not barangay_name:

        messages.error(
            request,
            'Barangay name is required.'
        )

        return redirect('barangay_purok')

    if Barangay.objects.filter(
        barangay_name__iexact=barangay_name
    ).exists():

        messages.error(
            request,
            f'Barangay {barangay_name} already exists.'
        )

        return redirect('barangay_purok')

    Barangay.objects.create(
        barangay_name=barangay_name,
        latitude=latitude or None,
        longitude=longitude or None
    )

    messages.success(
        request,
        f'Barangay {barangay_name} was added successfully.'
    )

    return redirect('barangay_purok')


# =========================================================
# UPDATE BARANGAY
# CHO ONLY
# =========================================================

@role_required('CHO')
def update_barangay(request, barangay_id):

    if request.method != 'POST':
        return redirect('barangay_purok')

    barangay = get_object_or_404(
        Barangay,
        barangay_id=barangay_id
    )

    barangay_name = request.POST.get(
        'barangay_name',
        ''
    ).strip()

    latitude = request.POST.get(
        'latitude',
        ''
    ).strip()

    longitude = request.POST.get(
        'longitude',
        ''
    ).strip()

    if not barangay_name:

        messages.error(
            request,
            'Barangay name is required.'
        )

        return redirect('barangay_purok')

    duplicate = (
        Barangay.objects
        .filter(
            barangay_name__iexact=barangay_name
        )
        .exclude(
            barangay_id=barangay.barangay_id
        )
        .exists()
    )

    if duplicate:

        messages.error(
            request,
            'Another Barangay already uses that name.'
        )

        return redirect('barangay_purok')

    barangay.barangay_name = barangay_name
    barangay.latitude = latitude or None
    barangay.longitude = longitude or None

    barangay.save()

    messages.success(
        request,
        f'{barangay.barangay_name} was updated successfully.'
    )

    return redirect('barangay_purok')


# =========================================================
# DELETE BARANGAY
# CHO ONLY
# =========================================================

@role_required('CHO')
def delete_barangay(request, barangay_id):

    if request.method != 'POST':
        return redirect('barangay_purok')

    barangay = get_object_or_404(
        Barangay,
        barangay_id=barangay_id
    )

    barangay_name = barangay.barangay_name

    barangay.delete()

    messages.success(
        request,
        f'Barangay {barangay_name} was deleted.'
    )

    return redirect('barangay_purok')


# =========================================================
# ADD PUROK
# CHO ONLY
# =========================================================

@role_required('CHO')
def add_purok(request):

    if request.method != 'POST':
        return redirect('barangay_purok')

    barangay_id = request.POST.get(
        'barangay'
    )

    purok_name = request.POST.get(
        'purok_name',
        ''
    ).strip()

    if not barangay_id or not purok_name:

        messages.error(
            request,
            'Barangay and Purok name are required.'
        )

        return redirect('barangay_purok')

    barangay = get_object_or_404(
        Barangay,
        barangay_id=barangay_id
    )

    if Purok.objects.filter(
        barangay=barangay,
        purok_name__iexact=purok_name
    ).exists():

        messages.error(
            request,
            f'{purok_name} already exists in '
            f'{barangay.barangay_name}.'
        )

        return redirect('barangay_purok')

    Purok.objects.create(
        barangay=barangay,
        purok_name=purok_name
    )

    messages.success(
        request,
        f'{purok_name} was added to '
        f'{barangay.barangay_name}.'
    )

    return redirect('barangay_purok')


# =========================================================
# UPDATE PUROK
# CHO ONLY
# =========================================================

@role_required('CHO')
def update_purok(request, purok_id):

    if request.method != 'POST':
        return redirect('barangay_purok')

    purok = get_object_or_404(
        Purok,
        purok_id=purok_id
    )

    barangay_id = request.POST.get(
        'barangay'
    )

    purok_name = request.POST.get(
        'purok_name',
        ''
    ).strip()

    if not barangay_id or not purok_name:

        messages.error(
            request,
            'Barangay and Purok name are required.'
        )

        return redirect('barangay_purok')

    barangay = get_object_or_404(
        Barangay,
        barangay_id=barangay_id
    )

    duplicate = (
        Purok.objects
        .filter(
            barangay=barangay,
            purok_name__iexact=purok_name
        )
        .exclude(
            purok_id=purok.purok_id
        )
        .exists()
    )

    if duplicate:

        messages.error(
            request,
            f'{purok_name} already exists in '
            f'{barangay.barangay_name}.'
        )

        return redirect('barangay_purok')

    purok.barangay = barangay
    purok.purok_name = purok_name

    purok.save()

    messages.success(
        request,
        f'{purok.purok_name} was updated successfully.'
    )

    return redirect('barangay_purok')


# =========================================================
# DELETE PUROK
# CHO ONLY
# =========================================================

@role_required('CHO')
def delete_purok(request, purok_id):

    if request.method != 'POST':
        return redirect('barangay_purok')

    purok = get_object_or_404(
        Purok,
        purok_id=purok_id
    )

    purok_name = purok.purok_name

    purok.delete()

    messages.success(
        request,
        f'{purok_name} was deleted successfully.'
    )

    return redirect('barangay_purok')


# =========================================================
# DENGUE DATASET HELPER
# =========================================================

def load_dengue_cases():

    """
    Load official historical CSV cases plus CHO-confirmed web reports from:

        BASE_DIR / datasets

    Expected fields include:

        Sex
        AgeYears
        Blood Type
        Year
        DAdmit
        (Current Address) Barangay
        (Current Address) Sitio / Purok / Street Name
        (Current Address) City / Municipality
    """

    dataset_folder = (
        Path(settings.BASE_DIR)
        / 'datasets'
    )

    cases_data = []

    # Only patient-level source exports belong here. Generated ML datasets
    # (for example integrated_monthly.csv) must never be counted as cases.
    csv_files = sorted(
        dataset_folder.glob('WILBUR_DSO_dengue_*.csv')
    )

    case_id = 1

    for csv_file in csv_files:

        try:

            with open(
                csv_file,
                'r',
                encoding='utf-8-sig',
                newline=''
            ) as csvfile:

                reader = csv.DictReader(
                    csvfile
                )

                for row in reader:

                    # -----------------------------------------
                    # SEX
                    # -----------------------------------------

                    sex = (
                        row.get('Sex')
                        or row.get('sex')
                        or ''
                    ).strip()

                    # -----------------------------------------
                    # AGE
                    # -----------------------------------------

                    age = (
                        row.get('AgeYears')
                        or row.get('Age')
                        or row.get('age')
                        or ''
                    ).strip()

                    # -----------------------------------------
                    # CITY / MUNICIPALITY
                    # -----------------------------------------

                    address = (
                        row.get(
                            '(Current Address) City / Municipality'
                        )
                        or row.get(
                            'Current Address'
                        )
                        or row.get(
                            'address'
                        )
                        or ''
                    ).strip()

                    # -----------------------------------------
                    # BARANGAY
                    # -----------------------------------------

                    barangay_raw = (
                        row.get(
                            '(Current Address) Barangay'
                        )
                        or row.get(
                            'Barangay'
                        )
                        or row.get(
                            'barangay'
                        )
                        or ''
                    ).strip()
                    barangay = canonicalize_barangay(barangay_raw)
                    if barangay is None:
                        # The study scope is limited to official Iligan barangays.
                        continue

                    # -----------------------------------------
                    # PUROK
                    # -----------------------------------------

                    purok = (
                        row.get(
                            '(Current Address) Sitio / Purok / Street Name'
                        )
                        or row.get(
                            'Purok'
                        )
                        or row.get(
                            'purok'
                        )
                        or row.get(
                            'Sitio'
                        )
                        or row.get(
                            'Street'
                        )
                        or ''
                    ).strip()

                    # -----------------------------------------
                    # YEAR
                    # -----------------------------------------

                    year = (
                        row.get('Year')
                        or row.get('year')
                        or ''
                    ).strip()

                    # -----------------------------------------
                    # BLOOD TYPE
                    # -----------------------------------------

                    bloodtype = (
                        row.get('Blood Type')
                        or row.get('Bloodtype')
                        or row.get('BloodType')
                        or row.get('bloodtype')
                        or row.get('blood_type')
                        or ''
                    ).strip()

                    if not bloodtype:

                        bloodtype = 'N/A'

                    # -----------------------------------------
                    # DATE REPORTED
                    # -----------------------------------------

                    date_reported = (
                        row.get('DAdmit')
                        or row.get('Date Reported')
                        or row.get('date_reported')
                        or ''
                    ).strip()

                    if not date_reported:

                        date_reported = 'Not provided'

                    # -----------------------------------------
                    # SAVE CASE
                    # -----------------------------------------

                    cases_data.append({

                        'id':
                            case_id,

                        'sex':
                            sex,

                        'age':
                            age,

                        'blood_type':
                            bloodtype,

                        'address':
                            address,

                        'barangay':
                            barangay,

                        'purok':
                            purok,

                        'year':
                            year,

                        'date_reported':
                            date_reported,

                        'source_file':
                            csv_file.name,
                    })

                    case_id += 1

        except (
            OSError,
            csv.Error
        ):

            continue

    # CHW submissions remain private workflow records until CHO marks them
    # Confirmed. Only those CHO-confirmed records are added to the aggregate
    # views used by dashboards, maps, and resident public summaries.
    confirmed_cases = DengueCase.objects.filter(
        case_status='Confirmed',
        barangay__isnull=False,
    ).select_related('barangay', 'purok').order_by('dengue_case_id')

    for report in confirmed_cases:
        barangay = canonicalize_barangay(report.barangay.barangay_name)
        if not barangay:
            continue
        copies = max(1, int(report.case_count or 1))
        for copy_index in range(copies):
            cases_data.append({
                'id': f'confirmed-{report.dengue_case_id}-{copy_index + 1}',
                'sex': report.patient_sex,
                'age': report.patient_age,
                'blood_type': report.patient_blood_type or 'N/A',
                'address': 'Iligan City',
                'barangay': barangay,
                'purok': report.purok.purok_name if report.purok else 'Not specified',
                'year': str(report.date_reported.year),
                'date_reported': report.date_reported.isoformat(),
                'source_file': 'CHO-confirmed web record',
            })

    return cases_data


def build_report_analytics(selected_year='all'):
    """Create demographic and yearly summaries from the historical CSVs."""
    cases = load_dengue_cases()
    if selected_year and str(selected_year).lower() != 'all':
        cases = [case for case in cases if str(case.get('year')) == str(selected_year)]
    yearly = Counter()
    sex = Counter()
    blood_types = Counter()
    age_groups = Counter()
    for case in cases:
        yearly[str(case.get('year') or 'Unknown')] += 1
        sex[str(case.get('sex') or 'Not specified').title()] += 1
        blood = str(case.get('blood_type') or 'N/A').upper()
        blood_types[blood] += 1
        try:
            age = int(float(case.get('age')))
            group = '0–5' if age <= 5 else '6–12' if age <= 12 else '13–19' if age <= 19 else '20–39' if age <= 39 else '40–59' if age <= 59 else '60+'
        except (TypeError, ValueError):
            group = 'Unknown'
        age_groups[group] += 1
    return {
        'yearly_summary': sorted(yearly.items(), reverse=True),
        'sex_summary': sex.most_common(),
        'blood_type_summary': blood_types.most_common(),
        'age_group_summary': age_groups.most_common(),
    }

# =========================================================
# LGU HOTSPOT MAP
# LGU ONLY
# =========================================================

@role_required('LGU')
@require_GET
def lgu_hotspot_map(request):

    # Use EXACTLY the same hotspot processing
    # as the CHO hotspot map.

    context = build_hotspot_data(request)
    return render(
        request,
        'lgu_hotspot_map.html',
        context
    )


# =========================================================
# CHO HOTSPOT MAP
# CHO ONLY
# =========================================================

@role_required('CHO')
def hotspot_map(request):

    context = build_hotspot_data(
        request
    )
    return render(
        request,
        'hotspot_map.html',
        context
    )


# =========================================================
# AI PREDICTIONS
# CHO ONLY
# =========================================================

@role_required('CHO')
def predictions(request):
    """CHO read-only AI prediction page."""
    context = prediction_context(request)
    context['page_role'] = 'CHO'
    return render(
        request,
        'cho_ai_prediction.html',
        context,
    )


@role_required('LGU')
@require_GET
def lgu_ai_predictions(request):
    """LGU read-only AI prediction page."""
    context = prediction_context(request)
    context['page_role'] = 'LGU'
    return render(
        request,
        'lgu_ai_prediction.html',
        context,
    )


# =========================================================
# REPORTS & ANALYTICS
# CHO ONLY
# =========================================================

@role_required('CHO')
def reports(request):
    context = build_hotspot_data(request)
    context.update(build_report_analytics())
    context['report_title'] = 'CHO Reports and Analytics'
    return render(request, 'reports.html', context)


@role_required('LGU')
@require_GET
def lgu_reports(request):
    """
    LGU Reports & Analytics
    Displays dengue reports based only on LGU-accessible data.
    """

    selected_year = request.GET.get('year', 'all').strip()
    context = build_hotspot_data(request)
    context.update(build_report_analytics(selected_year))
    context['report_title'] = 'LGU Reports and Analytics'
    context['selected_year'] = selected_year
    return render(request, 'lgu_reports_analytics.html', context)


@role_required('LGU')
@require_GET
def lgu_dengue_reports(request):
    """Search, filter, print, and export de-identified, city-wide planning reports."""
    all_cases = load_dengue_cases()
    years = sorted(
        {str(case.get('year')) for case in all_cases if case.get('year')},
        reverse=True,
    )
    barangays = sorted(
        {str(case.get('barangay')) for case in all_cases if case.get('barangay')},
        key=str.lower,
    )

    search = request.GET.get('search', '').strip()
    selected_year = request.GET.get('year', 'all').strip()
    selected_barangay = request.GET.get('barangay', 'all').strip()
    filtered_cases = all_cases

    if selected_year.lower() != 'all':
        filtered_cases = [
            case for case in filtered_cases
            if str(case.get('year')) == selected_year
        ]
    if selected_barangay.lower() != 'all':
        filtered_cases = [
            case for case in filtered_cases
            if str(case.get('barangay', '')).lower() == selected_barangay.lower()
        ]
    if search:
        needle = search.lower()
        searchable_fields = ('barangay', 'purok', 'sex', 'age', 'blood_type', 'date_reported')
        filtered_cases = [
            case for case in filtered_cases
            if any(needle in str(case.get(field, '')).lower() for field in searchable_fields)
        ]

    filtered_cases = sorted(
        filtered_cases,
        key=lambda case: (str(case.get('year', '')), str(case.get('date_reported', ''))),
        reverse=True,
    )

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="denguewatch_lgu_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Record ID', 'Year', 'Date Reported', 'Barangay', 'Purok', 'Sex', 'Age', 'Blood Type'])
        for case in filtered_cases:
            writer.writerow([
                case.get('id'), case.get('year'), case.get('date_reported'),
                case.get('barangay'), case.get('purok'), case.get('sex'),
                case.get('age'), case.get('blood_type'),
            ])
        return response

    paginator = Paginator(filtered_cases, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    context = {
        'page_obj': page_obj,
        'years': years,
        'barangays': barangays,
        'search': search,
        'selected_year': selected_year,
        'selected_barangay': selected_barangay,
        'total_records': len(all_cases),
        'filtered_count': len(filtered_cases),
        'barangay_count': len({case.get('barangay') for case in filtered_cases if case.get('barangay')}),
    }
    return render(request, 'lgu_dengue_reports.html', context)

# =========================================================
# DENGUE CASES
# CHO / CHW / BHW ONLY
# =========================================================

@role_required(
    'CHO',
    'CHW',
)
def cases(request):

    cases_data = load_dengue_cases()

    # =====================================================
    # BHW - ONLY ASSIGNED BARANGAY
    # =====================================================

    if getattr(
        request.user,
        'role',
        None
    ) == 'BHW':

        assigned_barangay_object = getattr(
            request.user,
            'assigned_barangay',
            None
        )

        if assigned_barangay_object:

            assigned_barangay = getattr(
                assigned_barangay_object,
                'barangay_name',
                str(assigned_barangay_object)
            )

            assigned_barangay = str(
                assigned_barangay
            ).strip().lower()

            cases_data = [
                case
                for case in cases_data
                if str(
                    case.get(
                        'barangay',
                        ''
                    )
                ).strip().lower()
                == assigned_barangay
            ]

        else:

            # No assigned barangay means a BHW must not
            # receive unrestricted city-wide case records.
            cases_data = []

    # =====================================================
    # FILTERS
    # =====================================================

    search = request.GET.get(
        'search',
        ''
    ).strip().lower()

    sex_filter = request.GET.get(
        'sex',
        ''
    ).strip().lower()

    age_filter = request.GET.get(
        'age',
        ''
    ).strip()

    year_filter = request.GET.get(
        'year',
        ''
    ).strip()

    blood_filter = request.GET.get(
        'blood_type',
        ''
    ).strip().lower()

    # =====================================================
    # FILTER CASES
    # =====================================================

    filtered_cases = []

    for case in cases_data:

        # -------------------------------------------------
        # SEARCH
        # -------------------------------------------------

        if search:

            searchable = ' '.join([

                str(
                    case.get(
                        'sex',
                        ''
                    )
                ),

                str(
                    case.get(
                        'age',
                        ''
                    )
                ),

                str(
                    case.get(
                        'blood_type',
                        ''
                    )
                ),

                str(
                    case.get(
                        'address',
                        ''
                    )
                ),

                str(
                    case.get(
                        'barangay',
                        ''
                    )
                ),

                str(
                    case.get(
                        'purok',
                        ''
                    )
                ),

                str(
                    case.get(
                        'year',
                        ''
                    )
                ),

                str(
                    case.get(
                        'date_reported',
                        ''
                    )
                ),

            ]).lower()

            if search not in searchable:

                continue

        # -------------------------------------------------
        # SEX
        # -------------------------------------------------

        if sex_filter:

            if (
                case.get(
                    'sex',
                    ''
                ).lower()
                != sex_filter
            ):

                continue

        # -------------------------------------------------
        # AGE
        # -------------------------------------------------

        if age_filter:

            if str(
                case.get(
                    'age',
                    ''
                )
            ) != age_filter:

                continue

        # -------------------------------------------------
        # YEAR
        # -------------------------------------------------

        if year_filter:

            if str(
                case.get(
                    'year',
                    ''
                )
            ) != year_filter:

                continue

        # -------------------------------------------------
        # BLOOD TYPE
        # -------------------------------------------------

        if blood_filter:

            if (
                case.get(
                    'blood_type',
                    ''
                ).lower()
                != blood_filter
            ):

                continue

        filtered_cases.append(
            case
        )

    # =====================================================
    # SUMMARY
    # =====================================================

    male_cases = sum(

        1
        for case in cases_data

        if case.get(
            'sex',
            ''
        ).lower()
        == 'male'
    )

    female_cases = sum(

        1
        for case in cases_data

        if case.get(
            'sex',
            ''
        ).lower()
        == 'female'
    )

    # =====================================================
    # YEARS
    # =====================================================

    years = sorted(

        {
            str(
                case.get(
                    'year',
                    ''
                )
            )

            for case in cases_data

            if case.get(
                'year',
                ''
            )
        },

        reverse=True
    )

    # =====================================================
    # CURRENT YEAR
    # =====================================================

    current_year_cases = sum(

        1
        for case in cases_data

        if str(
            case.get(
                'year',
                ''
            )
        ) == '2026'
    )

    # =====================================================
    # PAGINATION
    # =====================================================

    paginator = Paginator(
        filtered_cases,
        50
    )

    page_number = request.GET.get(
        'page'
    )

    page_obj = paginator.get_page(
        page_number
    )

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        'cases':
            page_obj,

        'page_obj':
            page_obj,

        'paginator':
            paginator,

        'total_cases':
            len(
                filtered_cases
            ),

        'male_cases':
            male_cases,

        'female_cases':
            female_cases,

        'current_year_cases':
            current_year_cases,

        'years':
            years,
    }

    return render(
        request,
        'cases.html',
        context
    )


# =========================================================
# BHW DENGUE CASE MONITORING
# BHW ONLY
# =========================================================

@role_required('BHW')
def dengue_case_bhw(request):

    assigned_barangay = request.user.assigned_barangay
    assigned_purok = request.user.assigned_purok

    # -----------------------------------------
    # ALL CASES IN ASSIGNED BARANGAY
    # -----------------------------------------

    # Suspected/draft reports belong to the CHW -> CHO verification flow and
    # are not disclosed in the BHW view. BHW sees only recorded outcomes in
    # the assigned area.
    area_cases = DengueCase.objects.filter(
        barangay=assigned_barangay,
        case_status__in=['Confirmed', 'Active', 'Recovered'],
    )

    # If BHW monitoring should only cover
    # their assigned purok
    if assigned_purok:

        area_cases = area_cases.filter(
            purok=assigned_purok
        )

    # -----------------------------------------
    # CURRENT / ACTIVE CASES
    # -----------------------------------------

    active_cases = area_cases.filter(
        case_status='Active'
    ).count()

    confirmed_cases = area_cases.filter(
        case_status='Confirmed'
    ).count()

    pending_cases = 0

    recovered_cases = area_cases.filter(
        case_status='Recovered'
    ).count()

    # Current cases can include Confirmed + Active
    current_cases = (
        active_cases +
        confirmed_cases
    )

    # BHWs have view-only access to confirmed/active case information in
    # their assigned area. CHO remains the final authority for case records.
    area_cases = area_cases.order_by(
        '-date_reported',
        '-dengue_case_id'
    )

    context = {

        'dengue_cases': area_cases,

        'assigned_barangay':
            assigned_barangay,

        'assigned_purok':
            assigned_purok,

        'current_cases':
            current_cases,

        'active_cases':
            active_cases,

        'confirmed_cases':
            confirmed_cases,

        'pending_cases':
            pending_cases,

        'recovered_cases':
            recovered_cases,

        'total_area_cases':
            area_cases.count(),
    }

    return render(
        request,
        'dengue_case_bhw.html',
        context
    )

# =========================================================
# SHARED HOTSPOT DATA
# USED BY BOTH CHO AND LGU
# =========================================================

def build_hotspot_data(request):
    """
    Build the exact same hotspot data for CHO and LGU.

    Both roles use:
        datasets/WILBUR_DSO_dengue_*.csv

    Risk thresholds:
        1 - 5       = Low
        6 - 50      = Moderate
        51 - 100    = High
        101+        = Critical

    These are DengueWatch display thresholds and are
    NOT official DOH outbreak classifications.
    """

    dataset_dir = (
        Path(settings.BASE_DIR)
        / 'datasets'
    )

    # =====================================================
    # USE THE SAME DATASETS AS CHO HOTSPOT MAP
    # =====================================================

    dataset_files = sorted(
        dataset_dir.glob(
            'WILBUR_DSO_dengue_*.csv'
        )
    )

    # Fallback if dataset filenames are different
    if not dataset_files:
        dataset_files = sorted(
            dataset_dir.glob('*.csv')
        )

    # =====================================================
    # FILTERS
    # =====================================================

    selected_year = request.GET.get(
        'year',
        'all'
    ).strip()

    selected_risk = request.GET.get(
        'risk',
        'all'
    ).strip().lower()

    # =====================================================
    # STORAGE
    # =====================================================

    barangays = {}

    all_years = set()

    total_dataset_cases = 0

    # =====================================================
    # NORMALIZE BARANGAY
    # =====================================================

    def normalize_name(value):

        value = str(
            value or ''
        ).strip()

        value = re.sub(
            r'[-]+',
            ' ',
            value
        )

        value = re.sub(
            r'\s+',
            ' ',
            value
        )

        return value.lower().strip()

    # =====================================================
    # RISK LEVEL
    # =====================================================

    def get_risk(case_count):

        if case_count >= 101:
            return 'Critical'

        elif case_count >= 51:
            return 'High'

        elif case_count >= 6:
            return 'Moderate'

        elif case_count >= 1:
            return 'Low'

        return 'None'

    # =====================================================
    # RISK COLOR
    # =====================================================

    def get_risk_color(risk_level):

        if risk_level == 'Critical':
            return '#dc2626'

        elif risk_level == 'High':
            return '#f97316'

        elif risk_level == 'Moderate':
            return '#facc15'

        elif risk_level == 'Low':
            return '#22c55e'

        return '#9ca3af'

    # =====================================================
    # READ DATASETS
    # =====================================================

    for dataset_path in dataset_files:

        try:

            with open(
                dataset_path,
                'r',
                encoding='utf-8-sig',
                newline=''
            ) as csvfile:

                reader = csv.DictReader(
                    csvfile
                )

                for row in reader:

                    total_dataset_cases += 1

                    # =============================================
                    # YEAR
                    # =============================================

                    year = (
                        row.get('Year')
                        or row.get('year')
                        or ''
                    ).strip()

                    if year:
                        year = str(year)
                        all_years.add(year)

                    # =============================================
                    # BARANGAY
                    # =============================================

                    barangay_raw = (
                        row.get(
                            '(Current Address) Barangay'
                        )
                        or row.get('Barangay')
                        or row.get('barangay')
                        or ''
                    ).strip()
                    barangay = canonicalize_barangay(barangay_raw)
                    if not barangay:
                        # Keep all CHO/LGU/BHW analyses within the official
                        # City of Iligan 44-barangay study scope.
                        continue

                    # =============================================
                    # PUROK / SITIO / STREET
                    # =============================================

                    purok = (
                        row.get(
                            '(Current Address) Sitio / Purok / Street Name'
                        )
                        or row.get('Purok')
                        or row.get('purok')
                        or row.get('Sitio')
                        or row.get('Street')
                        or ''
                    ).strip()

                    if not purok:
                        purok = 'Not specified'

                    # =============================================
                    # CITY
                    # =============================================

                    city = (
                        row.get(
                            '(Current Address) City / Municipality'
                        )
                        or row.get('City')
                        or row.get('city')
                        or ''
                    ).strip()

                    if not city:
                        city = 'Iligan City'

                    # =============================================
                    # NORMALIZED BARANGAY KEY
                    # =============================================

                    barangay_key = normalize_name(
                        barangay
                    )

                    # =============================================
                    # CREATE BARANGAY
                    # =============================================

                    if barangay_key not in barangays:

                        barangays[barangay_key] = {
                            'barangay': barangay,
                            'city': city,
                            'cases': 0,
                            'puroks': Counter(),
                            'years': Counter(),
                        }

                    # =============================================
                    # CASE COUNT
                    # =============================================

                    barangays[
                        barangay_key
                    ]['cases'] += 1

                    # =============================================
                    # PUROK COUNT
                    # =============================================

                    barangays[
                        barangay_key
                    ]['puroks'][
                        purok
                    ] += 1

                    # =============================================
                    # YEAR COUNT
                    # =============================================

                    if year:

                        barangays[
                            barangay_key
                        ]['years'][
                            year
                        ] += 1

        except (
            OSError,
            csv.Error
        ) as e:

            print(
                f'Error reading '
                f'{dataset_path.name}: '
                f'{e}'
            )

    # Add only CHO-confirmed workflow cases to the live aggregate. Pending,
    # draft, and rejected reports must never alter official totals or maps.
    confirmed_web_cases = list(
        DengueCase.objects.filter(
            case_status='Confirmed',
            barangay__isnull=False,
        ).select_related('barangay', 'purok')
    )
    for report in confirmed_web_cases:
        barangay = canonicalize_barangay(report.barangay.barangay_name)
        if not barangay:
            continue
        year = str(report.date_reported.year)
        purok = report.purok.purok_name if report.purok else 'Not specified'
        case_units = max(1, int(report.case_count or 1))
        barangay_key = normalize_name(barangay)
        all_years.add(year)
        total_dataset_cases += case_units
        if barangay_key not in barangays:
            barangays[barangay_key] = {
                'barangay': barangay,
                'city': 'Iligan City',
                'cases': 0,
                'puroks': Counter(),
                'years': Counter(),
            }
        barangays[barangay_key]['cases'] += case_units
        barangays[barangay_key]['puroks'][purok] += case_units
        barangays[barangay_key]['years'][year] += case_units

    # Do not silently render an arbitrary, empty future year as a historical
    # map. The selected value must exist in the loaded historical dataset.
    if selected_year.lower() != 'all' and selected_year not in all_years:
        selected_year = 'all'

    # =====================================================
    # FILTER BY YEAR
    # =====================================================

    if (
        selected_year
        and selected_year.lower() != 'all'
    ):

        filtered_barangays = {}

        for key, area in barangays.items():

            year_count = area[
                'years'
            ].get(
                selected_year,
                0
            )

            if year_count > 0:

                filtered_barangays[key] = {
                    'barangay':
                        area['barangay'],

                    'city':
                        area['city'],

                    'cases':
                        year_count,

                    'puroks':
                        Counter(),

                    'years':
                        area['years'],
                }

                # Only include puroks from selected year.
                #
                # Read datasets again to get the exact
                # selected-year purok counts.

        # Rebuild purok counts for selected year
        for dataset_path in dataset_files:

            try:

                with open(
                    dataset_path,
                    'r',
                    encoding='utf-8-sig',
                    newline=''
                ) as csvfile:

                    reader = csv.DictReader(
                        csvfile
                    )

                    for row in reader:

                        year = (
                            row.get('Year')
                            or row.get('year')
                            or ''
                        ).strip()

                        if str(year) != str(
                            selected_year
                        ):
                            continue

                        barangay_raw = (
                            row.get(
                                '(Current Address) Barangay'
                            )
                            or row.get('Barangay')
                            or row.get('barangay')
                            or ''
                        ).strip()
                        barangay = canonicalize_barangay(barangay_raw)
                        if not barangay:
                            continue

                        barangay_key = normalize_name(
                            barangay
                        )

                        if barangay_key not in filtered_barangays:
                            continue

                        purok = (
                            row.get(
                                '(Current Address) Sitio / Purok / Street Name'
                            )
                            or row.get('Purok')
                            or row.get('purok')
                            or row.get('Sitio')
                            or row.get('Street')
                            or ''
                        ).strip()

                        if not purok:
                            purok = 'Not specified'

                        filtered_barangays[
                            barangay_key
                        ]['puroks'][
                            purok
                        ] += 1

            except (
                OSError,
                csv.Error
            ) as e:

                print(
                    f'Error reading {dataset_path.name}: {e}'
                )

        # The CSV loop above only contains imported historical records. Add
        # confirmed web records for the selected year so popup purok counts
        # agree with the polygon's displayed case total.
        for report in confirmed_web_cases:
            if str(report.date_reported.year) != str(selected_year):
                continue
            barangay = canonicalize_barangay(report.barangay.barangay_name)
            if not barangay:
                continue
            barangay_key = normalize_name(barangay)
            if barangay_key not in filtered_barangays:
                continue
            purok = report.purok.purok_name if report.purok else 'Not specified'
            filtered_barangays[barangay_key]['puroks'][purok] += max(
                1,
                int(report.case_count or 1),
            )

        barangays = filtered_barangays

    # Include all official areas on every role's hotspot map, even when a
    # selected period has zero recorded cases.
    for official_name in ILIGAN_BARANGAYS:
        key = normalize_name(official_name)
        barangays.setdefault(key, {
            'barangay': official_name,
            'city': 'Iligan City',
            'cases': 0,
            'puroks': Counter(),
            'years': Counter(),
        })

    # =====================================================
    # CREATE HOTSPOT DATA
    # =====================================================

    hotspot_data = []

    for key, area in barangays.items():

        case_count = area[
            'cases'
        ]

        risk_level = get_risk(
            case_count
        )

        # =============================================
        # PUROK DATA
        # =============================================

        purok_data = []

        for purok_name, count in sorted(
            area['puroks'].items(),
            key=lambda item: (
                -item[1],
                item[0].lower()
            )
        ):

            purok_data.append({
                'name':
                    purok_name,

                'purok':
                    purok_name,

                'cases':
                    count,

                'case_count':
                    count,

                'risk_level':
                    get_risk(count),
            })

        # =============================================
        # YEAR DATA
        # =============================================

        year_data = []

        for year, count in sorted(
            area['years'].items(),
            key=lambda item:
                str(item[0]),
            reverse=True
        ):

            year_data.append({
                'year':
                    str(year),

                'cases':
                    count,

                'case_count':
                    count,
            })

        # =============================================
        # BARANGAY DATA
        # =============================================

        hotspot_data.append({

            'barangay':
                area['barangay'],

            'city':
                area['city'],

            'cases':
                case_count,

            'case_count':
                case_count,

            'risk':
                risk_level,

            'risk_level':
                risk_level,

            'risk_color':
                get_risk_color(
                    risk_level
                ),

            'puroks':
                purok_data,

            'years':
                year_data,

            'normalized_name':
                key,
        })

    # =====================================================
    # SORT
    # =====================================================

    hotspot_data.sort(
        key=lambda item:
            item['case_count'],
        reverse=True
    )

    # =====================================================
    # SUMMARY
    # =====================================================

    total_cases = sum(
        item['case_count']
        for item in hotspot_data
    )

    monitored_barangays = len(
        hotspot_data
    )

    # This is intentionally separate from the number of barangays shown on
    # the historical map. A barangay is BHW-covered only when an approved
    # BHW account has been assigned to it by the CHO.
    assigned_bhws = UserAccount.objects.filter(
        role='BHW',
        account_status='APPROVED',
        assigned_barangay__isnull=False,
    )

    bhw_covered_barangays = assigned_bhws.values(
        'assigned_barangay_id'
    ).distinct().count()

    assigned_bhw_workers = assigned_bhws.count()

    high_risk_areas = sum(
        1
        for item in hotspot_data
        if item['risk_level']
        in [
            'High',
            'Critical'
        ]
    )

    critical_areas = sum(
        1
        for item in hotspot_data
        if item['risk_level']
        == 'Critical'
    )

    predicted_hotspots = sum(
        1
        for item in hotspot_data
        if item['risk_level']
        in [
            'High',
            'Critical'
        ]
    )

    # =====================================================
    # MAP DATA
    # =====================================================

    map_data = []

    for item in hotspot_data:

        map_data.append({

            'barangay':
                item['barangay'],

            'city':
                item['city'],

            'case_count':
                item['case_count'],

            'risk_level':
                item['risk_level'],

            'risk_color':
                item['risk_color'],

            'puroks':
                item['puroks'],

            'years':
                item['years'],

            # A boundary service may use a display label that differs from
            # the official dataset label. PSA calls the Saray polygon
            # "Saray-Tibanga" and supplies a separate Tibanga polygon.
            'boundary_names': (
                ['Saray', 'Saray-Tibanga']
                if item['barangay'] == 'Saray'
                else [item['barangay']]
            ),
        })

    # =====================================================
    # CONTEXT
    # =====================================================

    ordered_years = sorted(all_years, reverse=True)
    chronological_years = sorted(all_years, key=lambda value: int(value) if str(value).isdigit() else str(value))
    historical_case_period = (
        f'{chronological_years[0]}–{chronological_years[-1]}'
        if len(chronological_years) > 1 else (chronological_years[0] if chronological_years else 'No historical records')
    )
    selected_year_label = (
        'All available historical years'
        if selected_year.lower() == 'all' else f'Historical year {selected_year}'
    )

    return {

        'hotspot_data':
            hotspot_data,

        'hotspots':
            hotspot_data,

        'top_hotspots':
            hotspot_data[:10],

        'total_cases':
            total_cases,

        'monitored_barangays':
            monitored_barangays,

        'total_barangays':
            monitored_barangays,

        'bhw_covered_barangays':
            bhw_covered_barangays,

        'assigned_bhw_workers':
            assigned_bhw_workers,

        'high_risk_areas':
            high_risk_areas,

        'high_critical':
            high_risk_areas,

        'critical_areas':
            critical_areas,

        'predicted_hotspots':
            predicted_hotspots,

        'years': ordered_years,

        'available_years': ordered_years,

        'selected_year':
            selected_year,

        'selected_risk':
            selected_risk,

        # Historical map metadata: never use the forecast period here.
        'map_data_source': 'Historical dengue case records',
        'historical_case_period': historical_case_period,
        'selected_year_label': selected_year_label,

        'dataset_count':
            len(dataset_files),

        'map_locations_json':
            json.dumps(
                map_data,
                ensure_ascii=False
            ),

        'hotspot_data_json':
            json.dumps(
                hotspot_data,
                ensure_ascii=False
            ),
    }


# =========================================================
# CHW DASHBOARD
# CHW ONLY
# =========================================================

@role_required('CHW')
def chw_dashboard(request):

    return render(
        request,
        'chw_dashboard.html',
        {
            'total_cases': DengueCase.objects.filter(user_account=request.user).count(),
            'pending_cases': DengueCase.objects.filter(user_account=request.user, case_status='Pending').count(),
            'recent_cases': DengueCase.objects.filter(user_account=request.user).select_related('barangay', 'purok').order_by('-date_reported')[:5],
        }
    )


def _render_chw_case_reports(request, form_case=None, form_data=None):
    reports = DengueCase.objects.filter(
        user_account=request.user,
    ).select_related('barangay', 'purok', 'reviewed_by').prefetch_related('audit_logs__actor').order_by('-date_reported', '-dengue_case_id')
    form_values = {
        'patient_age': '', 'patient_sex': '', 'patient_blood_type': '',
        'date_reported': '', 'barangay_id': '', 'purok_id': '',
        'location_details': '', 'symptoms': '', 'remarks': '',
    }
    if form_case:
        form_values.update({
            'patient_age': form_case.patient_age,
            'patient_sex': form_case.patient_sex,
            'patient_blood_type': form_case.patient_blood_type,
            'date_reported': form_case.date_reported.isoformat(),
            'barangay_id': form_case.barangay_id or '',
            'purok_id': form_case.purok_id or '',
            'location_details': form_case.location_details,
            'symptoms': form_case.symptoms,
            'remarks': form_case.remarks,
        })
    if form_data:
        form_values.update({key: form_data.get(key, value) for key, value in form_values.items()})
    return render(request, 'chw_case_reports.html', {
        'reports': reports,
        'barangays': Barangay.objects.order_by('barangay_name'),
        'puroks': Purok.objects.select_related('barangay').order_by('barangay__barangay_name', 'purok_name'),
        'form_case': form_case,
        'form_values': form_values,
    })


def _save_chw_case(request, case=None):
    """Save a CHW draft or send a complete suspected case to CHO."""
    action = request.POST.get('action')
    if action not in {'draft', 'submit'}:
        return None, 'Choose whether to save a draft or send the report to CHO.'

    barangay = get_object_or_404(Barangay, pk=request.POST.get('barangay_id'))
    purok_id = request.POST.get('purok_id')
    purok = Purok.objects.filter(pk=purok_id, barangay=barangay).first() if purok_id else None
    if purok_id and purok is None:
        return None, 'Choose a purok that belongs to the selected barangay.'

    try:
        patient_age = int(request.POST.get('patient_age', ''))
        reported_on = date.fromisoformat(request.POST.get('date_reported', ''))
    except (TypeError, ValueError):
        return None, 'Enter a valid patient age and report date.'
    if patient_age < 0 or patient_age > 130:
        return None, 'Patient age must be between 0 and 130.'

    patient_sex = request.POST.get('patient_sex', '').strip()
    symptoms = request.POST.get('symptoms', '').strip()
    location_details = request.POST.get('location_details', '').strip()
    if not patient_sex:
        return None, 'Select the patient sex.'
    if action == 'submit' and (not symptoms or not location_details):
        return None, 'Symptoms and exact location details are required before sending to CHO.'

    is_new = case is None
    report = case or DengueCase(user_account=request.user)
    report.barangay = barangay
    report.purok = purok
    report.patient_age = patient_age
    report.patient_sex = patient_sex[:20]
    report.patient_blood_type = request.POST.get('patient_blood_type', '').strip().upper()[:5]
    report.date_reported = reported_on
    report.symptoms = symptoms
    report.location_details = location_details
    report.remarks = request.POST.get('remarks', '').strip()
    report.case_status = 'Pending' if action == 'submit' else 'Draft'
    report.reviewed_by = None
    report.reviewed_at = None
    report.cho_review_note = ''
    report.save()
    audit_action = 'CREATED' if is_new else 'EDITED'
    if action == 'submit':
        audit_action = 'SUBMITTED'
    log_report_action(
        actor=request.user,
        dengue_case=report,
        action=audit_action,
        details='CHW submitted the suspected case to CHO.' if action == 'submit' else 'CHW saved a suspected-case draft.',
    )
    return report, None


@role_required('CHW')
def chw_case_reports(request):
    if request.method == 'POST':
        report, error = _save_chw_case(request)
        if error:
            messages.error(request, error)
            return _render_chw_case_reports(request, form_data=request.POST)
        if report.case_status == 'Pending':
            messages.success(request, 'Suspected case validated and sent to CHO for final verification.')
        else:
            messages.success(request, 'Suspected case saved as a draft. Review it before sending to CHO.')
        return redirect('chw_case_reports')

    editing_case = None
    edit_id = request.GET.get('edit')
    if edit_id:
        editing_case = get_object_or_404(DengueCase, pk=edit_id, user_account=request.user, case_status='Draft')
    return _render_chw_case_reports(request, form_case=editing_case)


@role_required('CHW')
def update_chw_case_report(request, case_id):
    if request.method != 'POST':
        return redirect('chw_case_reports')
    report = get_object_or_404(DengueCase, pk=case_id, user_account=request.user, case_status='Draft')
    saved, error = _save_chw_case(request, case=report)
    if error:
        messages.error(request, error)
        return _render_chw_case_reports(request, form_case=report, form_data=request.POST)
    if saved.case_status == 'Pending':
        messages.success(request, 'Suspected case validated and sent to CHO for final verification.')
    else:
        messages.success(request, 'Draft updated.')
    return redirect('chw_case_reports')


@role_required('CHO')
def cho_suspected_case_reviews(request):
    reports = DengueCase.objects.filter(
        user_account__role='CHW',
        case_status='Pending',
    ).select_related('user_account', 'barangay', 'purok').prefetch_related('audit_logs__actor').order_by('date_reported', 'dengue_case_id')
    return render(request, 'cho_suspected_case_reviews.html', {'reports': reports})


@role_required('CHO')
def review_chw_case_report(request, case_id):
    if request.method != 'POST':
        return redirect('cho_suspected_case_reviews')
    report = get_object_or_404(DengueCase, pk=case_id, user_account__role='CHW', case_status='Pending')
    decision = request.POST.get('decision')
    note = request.POST.get('cho_review_note', '').strip()
    if decision not in {'Confirmed', 'Rejected'} or not note:
        messages.error(request, 'Choose Confirmed or Rejected and provide a CHO review note.')
        return redirect('cho_suspected_case_reviews')
    report.case_status = decision
    report.cho_review_note = note
    report.reviewed_by = request.user
    report.reviewed_at = timezone.now()
    report.save(update_fields=['case_status', 'cho_review_note', 'reviewed_by', 'reviewed_at'])
    log_report_action(
        actor=request.user,
        dengue_case=report,
        action='VERIFIED' if decision == 'Confirmed' else 'REJECTED',
        details=note,
    )
    notify_user(
        report.user_account,
        'CASE',
        f'Suspected case #{report.dengue_case_id} {decision.lower()}',
        f'CHO review: {note}',
        created_by=request.user,
        link='/chw/suspected-cases/',
    )
    if decision == 'Confirmed':
        messages.success(
            request,
            f'Suspected case #{report.dengue_case_id} was confirmed by CHO and is now included in live dashboard and hotspot-map totals.'
        )
    else:
        messages.success(request, f'Suspected case #{report.dengue_case_id} was rejected by CHO.')
    return redirect('cho_suspected_case_reviews')


# =========================================================
# BHW DASHBOARD
# BHW ONLY
# =========================================================

@role_required('BHW')
def bhw_dashboard(request):

    """
    Barangay Health Worker dashboard.

    BHW access is limited to the assigned barangay.
    Hotspot information uses the same calculations as
    the CHO/LGU hotspot map.
    """

    # =====================================================
    # HELPERS
    # =====================================================

    def assignment_name(
        value,
        possible_fields
    ):

        if not value:

            return ''

        for field_name in possible_fields:

            field_value = getattr(
                value,
                field_name,
                None
            )

            if field_value:

                return str(
                    field_value
                ).strip()

        return str(
            value
        ).strip()


    def normalize(value):

        return re.sub(
            r'\s+',
            ' ',
            str(
                value or ''
            ).strip().lower()
        )


    # =====================================================
    # ASSIGNED BARANGAY
    # =====================================================

    assigned_barangay_object = getattr(
        request.user,
        'assigned_barangay',
        None
    )


    if not assigned_barangay_object:

        assigned_barangay_object = getattr(
            request.user,
            'barangay',
            None
        )


    assigned_barangay = assignment_name(
        assigned_barangay_object,
        [
            'barangay_name',
            'name',
        ]
    )


    # =====================================================
    # ASSIGNED PUROK
    # =====================================================

    assigned_purok_object = getattr(
        request.user,
        'assigned_purok',
        None
    )


    if not assigned_purok_object:

        assigned_purok_object = getattr(
            request.user,
            'purok',
            None
        )


    assigned_purok = assignment_name(
        assigned_purok_object,
        [
            'purok_name',
            'name',
        ]
    )


    assignment_configured = bool(
        assigned_barangay
    )


    # =====================================================
    # GET SAME HOTSPOT DATA AS CHO/LGU
    # =====================================================

    hotspot_context = build_hotspot_data(
        request
    )


    hotspot_data = hotspot_context.get(
        'hotspot_data',
        []
    )


    assigned_hotspot = None


    # =====================================================
    # FIND ASSIGNED BARANGAY
    # =====================================================

    if assigned_barangay:

        target_name = normalize(
            assigned_barangay
        )


        for area in hotspot_data:

            area_name = normalize(
                area.get(
                    'barangay',
                    ''
                )
            )


            if area_name == target_name:

                assigned_hotspot = area

                break


    # =====================================================
    # ASSIGNED AREA SUMMARY
    # =====================================================

    if assigned_hotspot:

        total_cases = int(
            assigned_hotspot.get(
                'case_count',
                0
            )
            or 0
        )


        current_risk = (
            assigned_hotspot.get(
                'risk_level',
                'None'
            )
            or 'None'
        )


        assigned_purok_data = (
            assigned_hotspot.get(
                'puroks',
                []
            )
            or []
        )


    else:

        total_cases = 0


        if assignment_configured:

            current_risk = 'None'

        else:

            current_risk = 'N/A'


        assigned_purok_data = []


    # =====================================================
    # NUMBER OF RECORDED PUROKS / LOCATIONS
    # =====================================================

    monitored_puroks = len(
        assigned_purok_data
    )


    # =====================================================
    # RESIDENT ENVIRONMENTAL REPORTS IN THIS BHW'S ASSIGNED AREA
    #
    # BHWs do not create, confirm, or reject dengue case records. They
    # verify resident environmental concerns in their assigned service area
    # and forward verified concerns to the CHO for the final decision.
    # =====================================================

    area_environmental_reports = _bhw_environmental_report_queryset(
        request.user
    ).select_related(
        'resident', 'barangay', 'purok', 'bhw_reviewed_by'
    )

    pending_environmental_reports = area_environmental_reports.filter(
        status='PENDING'
    ).count()

    forwarded_environmental_reports = area_environmental_reports.filter(
        status='FORWARDED'
    ).count()

    recent_environmental_reports = area_environmental_reports.order_by(
        '-submitted_at'
    )[:5]


    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        'assigned_barangay':
            assigned_barangay,

        'assigned_purok':
            assigned_purok,

        'assignment_configured':
            assignment_configured,

        'total_cases':
            total_cases,

        'pending_environmental_reports':
            pending_environmental_reports,

        'forwarded_environmental_reports':
            forwarded_environmental_reports,

        'current_risk':
            current_risk,

        'monitored_puroks':
            monitored_puroks,

        'assigned_purok_data':
            assigned_purok_data,

        'recent_environmental_reports':
            recent_environmental_reports,

        'assigned_hotspot':
            assigned_hotspot,

    }


    return render(
        request,
        'bhw_dashboard.html',
        context
    )

# =========================================================
# BHW HOTSPOT INFORMATION
# BHW ONLY
# =========================================================

@role_required('BHW')
def bhw_hotspot_information(request):

    assigned_barangay = request.user.assigned_barangay
    assigned_purok = request.user.assigned_purok

    # -----------------------------------------------------
    # DEFAULT VALUES
    # -----------------------------------------------------

    barangay_name = None
    total_cases = 0
    risk_level = 'N/A'

    location_data = []

    low_locations = 0
    moderate_locations = 0
    high_locations = 0
    critical_locations = 0

    # -----------------------------------------------------
    # ONLY PROCESS DATA WHEN BHW HAS ASSIGNMENT
    # -----------------------------------------------------

    if assigned_barangay:

        barangay_name = (
            assigned_barangay.barangay_name
        )

        # Load your historical dengue dataset
        dataset_cases = load_dengue_cases()

        # -------------------------------------------------
        # FILTER CASES TO ASSIGNED BARANGAY
        # -------------------------------------------------

        barangay_cases = []

        for case in dataset_cases:

            case_barangay = str(
                case.get('barangay', '')
            ).strip()

            if (
                case_barangay.lower()
                == barangay_name.strip().lower()
            ):
                barangay_cases.append(case)

        total_cases = len(barangay_cases)

        # -------------------------------------------------
        # BARANGAY RISK CLASSIFICATION
        #
        # 1-5    = Low
        # 6-50   = Moderate
        # 51-100 = High
        # 101+   = Critical
        # -------------------------------------------------

        if total_cases <= 5:
            risk_level = 'Low'

        elif total_cases <= 50:
            risk_level = 'Moderate'

        elif total_cases <= 100:
            risk_level = 'High'

        else:
            risk_level = 'Critical'

        # -------------------------------------------------
        # GROUP BY PUROK / SITIO / STREET
        # -------------------------------------------------

        location_counts = {}

        for case in barangay_cases:

            location_name = str(
                case.get('purok', '')
            ).strip()

            if not location_name:
                location_name = 'Not specified'

            # If BHW has specific Purok assignment,
            # only show that Purok.
            if assigned_purok:

                assigned_purok_name = (
                    assigned_purok.purok_name
                    .strip()
                    .lower()
                )

                if (
                    location_name.strip().lower()
                    != assigned_purok_name
                ):
                    continue

            if location_name not in location_counts:
                location_counts[location_name] = 0

            location_counts[location_name] += 1

        # -------------------------------------------------
        # BUILD LOCATION DATA
        # -------------------------------------------------

        for location_name, case_count in location_counts.items():

            if case_count <= 5:
                location_risk = 'Low'
                low_locations += 1

            elif case_count <= 50:
                location_risk = 'Moderate'
                moderate_locations += 1

            elif case_count <= 100:
                location_risk = 'High'
                high_locations += 1

            else:
                location_risk = 'Critical'
                critical_locations += 1

            location_data.append({
                'name': location_name,
                'cases': case_count,
                'risk_level': location_risk,
            })

        # Highest case count first
        location_data.sort(
            key=lambda item: item['cases'],
            reverse=True
        )

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    search = request.GET.get(
        'search',
        ''
    ).strip()

    selected_risk = request.GET.get(
        'risk',
        ''
    ).strip()

    if search:

        location_data = [
            item
            for item in location_data
            if search.lower() in item['name'].lower()
        ]

    if selected_risk:

        location_data = [
            item
            for item in location_data
            if (
                item['risk_level'].lower()
                == selected_risk.lower()
            )
        ]

    # -----------------------------------------------------
    # CONTEXT
    # -----------------------------------------------------

    context = {

        'assigned_barangay':
            assigned_barangay,

        'assigned_purok':
            assigned_purok,

        'assignment_configured':
            bool(assigned_barangay),

        'barangay_name':
            barangay_name,

        'total_cases':
            total_cases,

        'risk_level':
            risk_level,

        'location_data':
            location_data,

        'location_count':
            len(location_data),

        'low_locations':
            low_locations,

        'moderate_locations':
            moderate_locations,

        'high_locations':
            high_locations,

        'critical_locations':
            critical_locations,

        'search':
            search,

        'selected_risk':
            selected_risk,
    }

    return render(
        request,
        'bhw_hotspot_information.html',
        context
    )


# =========================================================
# LGU DASHBOARD
# LGU ONLY
# =========================================================

@role_required('LGU')
@require_GET
def lgu_dashboard(request):

    cases_data = load_dengue_cases()

    # -----------------------------------------------------
    # CITY-WIDE SUMMARY
    # -----------------------------------------------------

    total_cases = len(
        cases_data
    )

    barangays = set()

    years = set()

    for case in cases_data:

        barangay = str(
            case.get(
                'barangay',
                ''
            )
        ).strip()

        year = str(
            case.get(
                'year',
                ''
            )
        ).strip()

        if barangay:

            barangays.add(
                barangay
            )

        if year:

            years.add(
                year
            )

    context = {

        'total_cases':
            total_cases,

        'monitored_barangays':
            len(
                barangays
            ),

        'years':
            sorted(
                years,
                reverse=True
            ),

    }

    return render(
        request,
        'lgu_dashboard.html',
        context
    )

# =========================================================
# LGU PROFILE
# LGU ONLY
# =========================================================

@role_required('LGU')
def lgu_profile(request):

    """
    LGU Profile

    Allows an authenticated LGU user to:
    - View account information
    - Update first name
    - Update last name
    - Update email
    - Update contact number
    - Update office address

    Username and role cannot be changed here.
    """

    user = request.user


    # =====================================================
    # DEFAULT FORM DATA
    # =====================================================

    form_data = {
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'email': user.email or '',
        'contact_number': user.contact_number or '',
        'address': user.address or '',
    }


    # =====================================================
    # UPDATE PROFILE
    # =====================================================

    if request.method == 'POST':

        first_name = request.POST.get(
            'first_name',
            ''
        ).strip()

        last_name = request.POST.get(
            'last_name',
            ''
        ).strip()

        email = request.POST.get(
            'email',
            ''
        ).strip()

        contact_number = request.POST.get(
            'contact_number',
            ''
        ).strip()

        address = request.POST.get(
            'address',
            ''
        ).strip()


        # =================================================
        # KEEP FORM DATA WHEN ERROR OCCURS
        # =================================================

        form_data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'contact_number': contact_number,
            'address': address,
        }


        # =================================================
        # REQUIRED FIELDS
        # =================================================

        if not first_name:

            messages.error(
                request,
                'First name is required.'
            )

            return render(
                request,
                'lgu_profile.html',
                {
                    'form_data': form_data
                }
            )


        if not last_name:

            messages.error(
                request,
                'Last name is required.'
            )

            return render(
                request,
                'lgu_profile.html',
                {
                    'form_data': form_data
                }
            )


        if not email:

            messages.error(
                request,
                'Email address is required.'
            )

            return render(
                request,
                'lgu_profile.html',
                {
                    'form_data': form_data
                }
            )


        # =================================================
        # CHECK EMAIL
        # =================================================

        email_exists = UserAccount.objects.filter(
            email__iexact=email
        ).exclude(
            pk=user.pk
        ).exists()


        if email_exists:

            messages.error(
                request,
                'This email address is already being used '
                'by another account.'
            )

            return render(
                request,
                'lgu_profile.html',
                {
                    'form_data': form_data
                }
            )


        # =================================================
        # UPDATE USER
        # =================================================

        user.first_name = first_name

        user.last_name = last_name

        user.email = email

        user.contact_number = contact_number

        user.address = address

        user.save(
            update_fields=[
                'first_name',
                'last_name',
                'email',
                'contact_number',
                'address',
            ]
        )


        # =================================================
        # SUCCESS
        # =================================================

        messages.success(
            request,
            'Your LGU profile has been updated successfully.'
        )

        return redirect(
            'lgu_profile'
        )


    # =====================================================
    # DISPLAY PROFILE
    # =====================================================

    return render(
        request,
        'lgu_profile.html',
        {
            'form_data': form_data
        }
    )

# =========================================================
# LGU RISK LEVELS
# LGU ONLY
# =========================================================

@role_required('LGU')
@require_GET
def lgu_risk_levels(request):

    """
    LGU read-only dengue risk level monitoring.

    Uses the SAME hotspot data and SAME risk classification
    as the CHO/LGU hotspot map.

    Risk thresholds:
        Low       = 1 - 5
        Moderate  = 6 - 50
        High      = 51 - 100
        Critical  = 101+
    """

    # =====================================================
    # GET SAME DATA USED BY HOTSPOT MAP
    # =====================================================

    context = build_hotspot_data(request)

    hotspot_data = context.get(
        'hotspot_data',
        []
    )


    # =====================================================
    # COUNT EACH RISK LEVEL
    # =====================================================

    low_count = sum(

        1

        for area in hotspot_data

        if area.get(
            'risk_level'
        ) == 'Low'

    )


    moderate_count = sum(

        1

        for area in hotspot_data

        if area.get(
            'risk_level'
        ) == 'Moderate'

    )


    high_count = sum(

        1

        for area in hotspot_data

        if area.get(
            'risk_level'
        ) == 'High'

    )


    critical_count = sum(

        1

        for area in hotspot_data

        if area.get(
            'risk_level'
        ) == 'Critical'

    )


    # =====================================================
    # HIGH + CRITICAL PRIORITY AREAS
    # =====================================================

    priority_areas = [

        area

        for area in hotspot_data

        if area.get(
            'risk_level'
        ) in [
            'High',
            'Critical'
        ]

    ]


    # =====================================================
    # CHART
    # =====================================================

    risk_chart_labels = [

        'Low',
        'Moderate',
        'High',
        'Critical',

    ]


    risk_chart_values = [

        low_count,
        moderate_count,
        high_count,
        critical_count,

    ]


    # =====================================================
    # ADD TO EXISTING HOTSPOT CONTEXT
    # =====================================================

    context.update({

        'low_count':
            low_count,

        'moderate_count':
            moderate_count,

        'high_count':
            high_count,

        'critical_count':
            critical_count,

        'priority_areas':
            priority_areas,

        'risk_chart_labels_json':
            json.dumps(
                risk_chart_labels
            ),

        'risk_chart_values_json':
            json.dumps(
                risk_chart_values
            ),

    })


    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        'lgu_risk_levels.html',
        context
    )


# =========================================================
# LGU CITY-WIDE MONITORING
# LGU ONLY
# =========================================================

# =========================================================
# LGU CITY-WIDE MONITORING
# LGU ONLY
# =========================================================

@role_required('LGU')
@require_GET
def city_wide_monitoring(request):

    """
    LGU City-Wide Dengue Monitoring

    Features:
    - Iligan City records only
    - Year filtering
    - Barangay case summary
    - Risk classification
    - Yearly dengue trend
    - Top barangays
    - Sex distribution
    - Age distribution
    - High/Critical risk monitoring
    """

    # =====================================================
    # LOAD DENGUE DATA
    # =====================================================

    cases_data = load_dengue_cases()


    # =====================================================
    # HELPER: NORMALIZE TEXT
    # =====================================================

    def normalize_text(value):

        return re.sub(
            r'\s+',
            ' ',
            str(value or '').strip().lower()
        )


    # =====================================================
    # HELPER: CHECK ILIGAN CITY
    # =====================================================

    def is_iligan_city(value):

        city = normalize_text(value)

        return city in {
            'city of iligan',
            'iligan city',
            'iligan',
        }


    # =====================================================
    # ONLY USE ILIGAN CITY RECORDS
    # =====================================================

    iligan_cases = [

        case

        for case in cases_data

        if is_iligan_city(
            case.get(
                'address',
                ''
            )
        )

    ]


    # =====================================================
    # AVAILABLE YEARS
    # =====================================================

    years = sorted(

        {

            str(
                case.get(
                    'year',
                    ''
                )
            ).strip()

            for case in iligan_cases

            if str(
                case.get(
                    'year',
                    ''
                )
            ).strip()

        },

        reverse=True

    )


    # =====================================================
    # YEAR FILTER
    # =====================================================

    selected_year = request.GET.get(
        'year',
        'all'
    ).strip()


    # Invalid year -> go back to all
    if (
        selected_year != 'all'
        and selected_year not in years
    ):

        selected_year = 'all'


    if selected_year == 'all':

        filtered_cases = iligan_cases

    else:

        filtered_cases = [

            case

            for case in iligan_cases

            if str(
                case.get(
                    'year',
                    ''
                )
            ).strip() == selected_year

        ]


    # =====================================================
    # DATASET COUNT
    # =====================================================

    dataset_dir = (
        Path(settings.BASE_DIR)
        / 'datasets'
    )


    dataset_count = len(

        list(
            dataset_dir.glob(
                '*.csv'
            )
        )

    )


    # =====================================================
    # RISK CLASSIFICATION
    #
    # SAME AS HOTSPOT MAP
    #
    # LOW       = 1 - 5
    # MODERATE  = 6 - 50
    # HIGH      = 51 - 100
    # CRITICAL  = 101+
    # =====================================================

    def get_risk(case_count):

        if case_count >= 101:

            return 'critical'

        elif case_count >= 51:

            return 'high'

        elif case_count >= 6:

            return 'moderate'

        elif case_count >= 1:

            return 'low'

        return 'none'


    # =====================================================
    # BARANGAY COUNTS
    # =====================================================

    barangay_counts = Counter()

    barangay_puroks = {}

    unassigned_location_cases = 0


    for case in filtered_cases:

        barangay = str(
            case.get(
                'barangay',
                ''
            )
        ).strip()


        purok = str(
            case.get(
                'purok',
                ''
            )
        ).strip()


        # =============================================
        # NO BARANGAY
        # =============================================

        if not barangay:

            unassigned_location_cases += 1

            continue


        # =============================================
        # COUNT BARANGAY CASE
        # =============================================

        barangay_counts[
            barangay
        ] += 1


        # =============================================
        # SAVE UNIQUE PUROK / SITIO / STREET
        # =============================================

        if barangay not in barangay_puroks:

            barangay_puroks[
                barangay
            ] = set()


        if purok:

            barangay_puroks[
                barangay
            ].add(
                purok
            )


    # =====================================================
    # BUILD BARANGAY LIST
    # =====================================================

    barangay_list = []


    for barangay, count in sorted(

        barangay_counts.items(),

        key=lambda item:
            item[1],

        reverse=True

    ):

        barangay_list.append({

            'barangay':
                barangay,

            'cases':
                count,

            'puroks':
                len(
                    barangay_puroks.get(
                        barangay,
                        set()
                    )
                ),

            'risk':
                get_risk(
                    count
                ),

        })


    # =====================================================
    # SUMMARY CARDS
    # =====================================================

    total_cases = len(
        filtered_cases
    )


    total_barangays = len(
        barangay_list
    )


    high_risk_barangays = [

        area

        for area in barangay_list

        if area[
            'risk'
        ] in {
            'high',
            'critical'
        }

    ]


    high_risk_count = len(
        high_risk_barangays
    )


    critical_count = sum(

        1

        for area in barangay_list

        if area[
            'risk'
        ] == 'critical'

    )


    # =====================================================
    # YEARLY DENGUE TREND
    #
    # Always uses all available Iligan City years.
    # =====================================================

    year_counts = Counter()


    for case in iligan_cases:

        year = str(
            case.get(
                'year',
                ''
            )
        ).strip()


        if year:

            year_counts[
                year
            ] += 1


    trend_years = sorted(
        year_counts.keys()
    )


    year_labels = trend_years


    year_values = [

        year_counts[
            year
        ]

        for year in trend_years

    ]


    # =====================================================
    # TOP 10 BARANGAYS
    # =====================================================

    top_barangays = barangay_list[:10]


    barangay_labels = [

        item[
            'barangay'
        ]

        for item in top_barangays

    ]


    barangay_values = [

        item[
            'cases'
        ]

        for item in top_barangays

    ]


    # =====================================================
    # RISK DISTRIBUTION
    # =====================================================

    risk_order = [

        'low',
        'moderate',
        'high',
        'critical',

    ]


    risk_counts = Counter(

        item[
            'risk'
        ]

        for item in barangay_list

    )


    risk_labels = [

        'Low',
        'Moderate',
        'High',
        'Critical',

    ]


    risk_values = [

        risk_counts[
            risk
        ]

        for risk in risk_order

    ]


    # =====================================================
    # SEX DISTRIBUTION
    # =====================================================

    sex_counts = Counter()


    for case in filtered_cases:

        sex = normalize_text(

            case.get(
                'sex',
                ''
            )

        )


        if sex == 'male':

            sex_counts[
                'Male'
            ] += 1


        elif sex == 'female':

            sex_counts[
                'Female'
            ] += 1


        else:

            sex_counts[
                'Not specified'
            ] += 1


    sex_labels = [

        label

        for label in [

            'Male',
            'Female',
            'Not specified',

        ]

        if sex_counts[
            label
        ] > 0

    ]


    sex_values = [

        sex_counts[
            label
        ]

        for label in sex_labels

    ]


    # =====================================================
    # AGE GROUP DISTRIBUTION
    # =====================================================

    age_counts = Counter({

        '0-4':
            0,

        '5-14':
            0,

        '15-24':
            0,

        '25-44':
            0,

        '45-64':
            0,

        '65+':
            0,

        'Not specified':
            0,

    })


    for case in filtered_cases:

        raw_age = str(
            case.get(
                'age',
                ''
            )
        ).strip()


        try:

            age = int(
                float(
                    raw_age
                )
            )


        except (
            TypeError,
            ValueError
        ):

            age_counts[
                'Not specified'
            ] += 1

            continue


        if age <= 4:

            age_counts[
                '0-4'
            ] += 1


        elif age <= 14:

            age_counts[
                '5-14'
            ] += 1


        elif age <= 24:

            age_counts[
                '15-24'
            ] += 1


        elif age <= 44:

            age_counts[
                '25-44'
            ] += 1


        elif age <= 64:

            age_counts[
                '45-64'
            ] += 1


        else:

            age_counts[
                '65+'
            ] += 1


    age_labels = [

        '0-4',
        '5-14',
        '15-24',
        '25-44',
        '45-64',
        '65+',

    ]


    if age_counts[
        'Not specified'
    ] > 0:

        age_labels.append(
            'Not specified'
        )


    age_values = [

        age_counts[
            label
        ]

        for label in age_labels

    ]


    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        # -------------------------
        # SUMMARY
        # -------------------------

        'total_cases':
            total_cases,

        'total_barangays':
            total_barangays,

        'high_risk_count':
            high_risk_count,

        'critical_count':
            critical_count,

        'dataset_count':
            dataset_count,


        # -------------------------
        # DATA QUALITY
        # -------------------------

        'unassigned_location_cases':
            unassigned_location_cases,


        # -------------------------
        # FILTER
        # -------------------------

        'years':
            years,

        'selected_year':
            selected_year,


        # -------------------------
        # BARANGAY DATA
        # -------------------------

        'barangay_list':
            barangay_list,

        'high_risk_barangays':
            high_risk_barangays,


        # -------------------------
        # YEAR CHART
        # -------------------------

        'year_labels_json':
            json.dumps(
                year_labels
            ),

        'year_values_json':
            json.dumps(
                year_values
            ),


        # -------------------------
        # BARANGAY CHART
        # -------------------------

        'barangay_labels_json':
            json.dumps(
                barangay_labels
            ),

        'barangay_values_json':
            json.dumps(
                barangay_values
            ),


        # -------------------------
        # RISK CHART
        # -------------------------

        'risk_labels_json':
            json.dumps(
                risk_labels
            ),

        'risk_values_json':
            json.dumps(
                risk_values
            ),


        # -------------------------
        # SEX CHART
        # -------------------------

        'sex_labels_json':
            json.dumps(
                sex_labels
            ),

        'sex_values_json':
            json.dumps(
                sex_values
            ),


        # -------------------------
        # AGE CHART
        # -------------------------

        'age_labels_json':
            json.dumps(
                age_labels
            ),

        'age_values_json':
            json.dumps(
                age_values
            ),

    }


    # =====================================================
    # RENDER PAGE
    # =====================================================

    return render(
        request,
        'city_wide_monitoring.html',
        context
    )


# =========================================================
# CHO PENDING USER REQUESTS
# CHO ONLY
# =========================================================

# =========================================================
# CHO PENDING REQUESTS
# CHO ONLY
# =========================================================

@role_required('CHO')
def pending_requests(request):

    pending_users = (
        UserAccount.objects
        .filter(
            account_status='PENDING'
        )
        .order_by('-date_joined')
    )

    context = {

        'pending_users':
            pending_users,

        'pending_count':
            pending_users.count(),

        'bhw_pending':
            pending_users.filter(
                role='BHW'
            ).count(),

        'chw_pending':
            pending_users.filter(
                role='CHW'
            ).count(),

        'lgu_pending':
            pending_users.filter(
                role='LGU'
            ).count(),
    }

    return render(
        request,
        'pending_requests.html',
        context
    )


# =========================================================
# NOTIFICATION CENTER
# =========================================================

@login_required(login_url='login')
def notification_center(request):
    notifications = SystemNotification.objects.filter(recipient=request.user)
    if request.method == 'POST':
        notifications.filter(is_read=False).update(is_read=True, read_at=timezone.now())
        messages.success(request, 'Notifications marked as read.')
        return redirect('notification_center')
    return render(request, 'notification_center.html', {
        'notifications': notifications[:100],
        'unread_count': notifications.filter(is_read=False).count(),
    })


# =========================================================
# CHO USER MANAGEMENT
# CHO ONLY
# =========================================================

@role_required('CHO')
def user_management(request):

    users = UserAccount.objects.all().order_by(
        '-date_joined'
    )

    return render(
        request,
        'user_management.html',
        {
            'users':
                users
        }
    )


# =========================================================
# BHW AREA ASSIGNMENTS
# CHO ONLY
# =========================================================

@role_required('CHO')
def community_reports_review(request):
    """Final CHO queue for resident reports verified and forwarded by BHWs."""
    reports = CommunityReport.objects.select_related(
        'resident', 'barangay', 'purok', 'reviewed_by', 'bhw_reviewed_by'
    ).prefetch_related('audit_logs__actor').filter(status='FORWARDED').order_by('-bhw_reviewed_at', '-submitted_at')
    return render(request, 'community_reports_review.html', {'reports': reports})


@role_required('CHO')
def review_community_report(request, report_id):
    if request.method != 'POST':
        return redirect('community_reports_review')

    report = get_object_or_404(CommunityReport, pk=report_id, status='FORWARDED')
    status = request.POST.get('status', '').upper()
    response = request.POST.get('staff_response', '').strip()
    if status not in {'VERIFIED', 'REJECTED'} or not response:
        messages.error(request, 'Choose Verified or Rejected and provide a response for the resident.')
        return redirect('community_reports_review')

    report.status = status
    report.staff_response = response
    report.reviewed_by = request.user
    report.reviewed_at = timezone.now()
    report.save(update_fields=['status', 'staff_response', 'reviewed_by', 'reviewed_at'])
    log_report_action(
        actor=request.user,
        community_report=report,
        action=status,
        details=response,
    )
    notify_user(
        report.resident,
        'REPLY',
        f'CHO replied to your {report.observation_type} report',
        response,
        created_by=request.user,
        link='/(tabs)/report',
    )
    messages.success(request, 'Resident report reviewed and response saved.')
    return redirect('community_reports_review')


# =========================================================
# CHO ALERT AUTHORITY
# =========================================================

@role_required('CHO')
def alert_management(request):
    """CHO is the only role that can publish, withdraw, or re-activate alerts."""
    alerts = Alert.objects.select_related('barangay', 'created_by').order_by(
        '-is_active', '-created_at'
    )
    barangays = Barangay.objects.order_by('barangay_name')
    return render(request, 'alert_management.html', {
        'alerts': alerts,
        'barangays': barangays,
        'risk_choices': Alert.RISK_CHOICES,
    })


@role_required('CHO')
def create_alert(request):
    if request.method != 'POST':
        return redirect('alert_management')

    title = request.POST.get('title', '').strip()
    message = request.POST.get('message', '').strip()
    risk_level = request.POST.get('risk_level', '').upper()
    barangay_id = request.POST.get('barangay_id', '').strip()
    valid_levels = {value for value, _label in Alert.RISK_CHOICES}
    if not title or not message or risk_level not in valid_levels:
        messages.error(request, 'Provide an alert title, message, and valid risk level.')
        return redirect('alert_management')

    barangay = None
    if barangay_id:
        barangay = get_object_or_404(Barangay, pk=barangay_id)
    Alert.objects.create(
        title=title,
        message=message,
        risk_level=risk_level,
        barangay=barangay,
        created_by=request.user,
    )
    messages.success(request, 'Alert published for resident mobile users.')
    return redirect('alert_management')


@role_required('CHO')
def toggle_alert(request, alert_id):
    if request.method != 'POST':
        return redirect('alert_management')
    alert = get_object_or_404(Alert, pk=alert_id)
    alert.is_active = not alert.is_active
    alert.save(update_fields=['is_active'])
    messages.success(request, 'Alert activated.' if alert.is_active else 'Alert withdrawn.')
    return redirect('alert_management')


def _bhw_environmental_report_queryset(user):
    """Return only reports inside the BHW's explicitly assigned service area."""
    assigned_barangay = getattr(user, 'assigned_barangay', None)
    if not assigned_barangay:
        return CommunityReport.objects.none()
    reports = CommunityReport.objects.filter(barangay=assigned_barangay)
    assigned_purok = getattr(user, 'assigned_purok', None)
    if assigned_purok:
        reports = reports.filter(purok=assigned_purok)
    return reports


@role_required('BHW')
def bhw_environmental_reports(request):
    reports = _bhw_environmental_report_queryset(request.user).select_related(
        'resident', 'barangay', 'purok', 'bhw_reviewed_by'
    ).prefetch_related('audit_logs__actor').filter(status__in=['PENDING', 'FORWARDED']).order_by('status', '-submitted_at')
    return render(request, 'bhw_environmental_reports.html', {
        'reports': reports,
        'assigned_barangay': request.user.assigned_barangay,
        'assigned_purok': request.user.assigned_purok,
    })


@role_required('BHW')
def forward_environmental_report(request, report_id):
    if request.method != 'POST':
        return redirect('bhw_environmental_reports')
    report = get_object_or_404(
        _bhw_environmental_report_queryset(request.user),
        pk=report_id,
        status='PENDING',
    )
    note = request.POST.get('bhw_review_note', '').strip()
    if not note:
        messages.error(request, 'Provide a BHW verification note before forwarding the concern to CHO.')
        return redirect('bhw_environmental_reports')
    report.status = 'FORWARDED'
    report.bhw_review_note = note
    report.bhw_reviewed_by = request.user
    report.bhw_reviewed_at = timezone.now()
    report.save(update_fields=[
        'status', 'bhw_review_note', 'bhw_reviewed_by', 'bhw_reviewed_at',
    ])
    log_report_action(
        actor=request.user,
        community_report=report,
        action='FORWARDED',
        details=note,
    )
    for cho in UserAccount.objects.filter(role='CHO', account_status='APPROVED'):
        notify_user(
            cho,
            'REPORT',
            f'BHW forwarded a {report.observation_type} concern',
            f'{report.barangay.barangay_name}: {note}',
            created_by=request.user,
            link='/cho/community-reports/',
        )
    messages.success(request, 'Environmental concern verified and forwarded to CHO for final review.')
    return redirect('bhw_environmental_reports')


@role_required('CHO')
def bhw_assignments(request):
    """
    Allows the City Health Office to assign approved
    Barangay Health Workers to a Barangay and optional Purok.
    """

    # -----------------------------------------------------
    # APPROVED BHW ACCOUNTS
    # -----------------------------------------------------

    bhw_users = (
        UserAccount.objects
        .filter(
            role__in=['BHW', 'CHW'],
            account_status='APPROVED'
        )
        .select_related(
            'assigned_barangay',
            'assigned_purok'
        )
        .order_by(
            'first_name',
            'last_name',
            'username'
        )
    )

    # -----------------------------------------------------
    # BARANGAYS
    # -----------------------------------------------------

    barangays = (
        Barangay.objects
        .all()
        .order_by('barangay_name')
    )

    # -----------------------------------------------------
    # PUROKS
    # -----------------------------------------------------

    puroks = (
        Purok.objects
        .select_related('barangay')
        .all()
        .order_by(
            'barangay__barangay_name',
            'purok_name'
        )
    )

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    total_bhw = bhw_users.count()

    assigned_bhw = bhw_users.filter(
        assigned_barangay__isnull=False
    ).count()

    unassigned_bhw = bhw_users.filter(
        assigned_barangay__isnull=True
    ).count()

    barangay_count = barangays.count()

    # -----------------------------------------------------
    # CONTEXT
    # -----------------------------------------------------

    context = {
        'bhw_users': bhw_users,
        'barangays': barangays,
        'puroks': puroks,

        'total_bhw': total_bhw,
        'assigned_bhw': assigned_bhw,
        'unassigned_bhw': unassigned_bhw,
        'barangay_count': barangay_count,
    }

    return render(
        request,
        'bhw_assignments.html',
        context
    )


# =========================================================
# ASSIGN / UPDATE BHW AREA
# CHO ONLY
# =========================================================

@role_required('CHO')
def assign_bhw_area(request, user_id):
    """
    Assign or update the Barangay and optional Purok
    of an approved BHW account.
    """

    if request.method != 'POST':

        messages.error(
            request,
            'Invalid request method.'
        )

        return redirect(
            'bhw_assignments'
        )

    # -----------------------------------------------------
    # GET BHW
    # -----------------------------------------------------

    bhw = get_object_or_404(
        UserAccount,
        id=user_id,
        role__in=['BHW', 'CHW']
    )

    # -----------------------------------------------------
    # ONLY APPROVED BHW
    # -----------------------------------------------------

    if bhw.account_status != 'APPROVED':

        messages.error(
            request,
            'Only approved BHW accounts can be assigned '
            'to a monitoring area.'
        )

        return redirect(
            'bhw_assignments'
        )

    # -----------------------------------------------------
    # GET FORM VALUES
    # -----------------------------------------------------

    barangay_id = request.POST.get(
        'barangay',
        ''
    ).strip()

    purok_id = request.POST.get(
        'purok',
        ''
    ).strip()

    # -----------------------------------------------------
    # BARANGAY REQUIRED
    # -----------------------------------------------------

    if not barangay_id:

        messages.error(
            request,
            'Please select a Barangay.'
        )

        return redirect(
            'bhw_assignments'
        )

    # -----------------------------------------------------
    # GET BARANGAY
    # -----------------------------------------------------

    barangay = get_object_or_404(
        Barangay,
        barangay_id=barangay_id
    )

    # -----------------------------------------------------
    # GET PUROK
    # -----------------------------------------------------

    purok = None

    if purok_id:

        try:

            purok = Purok.objects.get(
                purok_id=purok_id,
                barangay=barangay
            )

        except Purok.DoesNotExist:

            messages.error(
                request,
                'The selected Purok does not belong '
                'to the selected Barangay.'
            )

            return redirect(
                'bhw_assignments'
            )

    # -----------------------------------------------------
    # SAVE ASSIGNMENT
    # -----------------------------------------------------

    bhw.assigned_barangay = barangay
    bhw.assigned_purok = purok

    bhw.save(
        update_fields=[
            'assigned_barangay',
            'assigned_purok',
        ]
    )

    assigned_area = barangay.barangay_name
    if purok:
        assigned_area = f'{assigned_area} — {purok.purok_name}'
    notify_user(
        bhw,
        'ASSIGNMENT',
        'New monitoring-area assignment',
        f'CHO assigned you to {assigned_area}.',
        created_by=request.user,
        link='/dashboard/',
    )

    # -----------------------------------------------------
    # SUCCESS MESSAGE
    # -----------------------------------------------------

    if purok:

        messages.success(
            request,
            f'{bhw.username} was assigned to '
            f'{barangay.barangay_name} - '
            f'{purok.purok_name}.'
        )

    else:

        messages.success(
            request,
            f'{bhw.username} was assigned to '
            f'{barangay.barangay_name} '
            f'for barangay-wide monitoring.'
        )

    return redirect(
        'bhw_assignments'
    )


# =========================================================
# REMOVE BHW AREA ASSIGNMENT
# CHO ONLY
# =========================================================

@role_required('CHO')
def remove_bhw_assignment(request, user_id):
    """
    Remove the Barangay and Purok assignment
    from a BHW account.
    """

    if request.method != 'POST':

        messages.error(
            request,
            'Invalid request method.'
        )

        return redirect(
            'bhw_assignments'
        )

    # -----------------------------------------------------
    # GET BHW
    # -----------------------------------------------------

    bhw = get_object_or_404(
        UserAccount,
        id=user_id,
        role__in=['BHW', 'CHW']
    )

    # -----------------------------------------------------
    # REMOVE ASSIGNMENT
    # -----------------------------------------------------

    bhw.assigned_barangay = None
    bhw.assigned_purok = None

    bhw.save(
        update_fields=[
            'assigned_barangay',
            'assigned_purok',
        ]
    )

    notify_user(
        bhw,
        'ASSIGNMENT',
        'Monitoring-area assignment removed',
        'CHO removed your assigned barangay/purok monitoring area.',
        created_by=request.user,
        link='/dashboard/',
    )

    messages.success(
        request,
        f'Area assignment for {bhw.username} '
        f'has been removed.'
    )

    return redirect(
        'bhw_assignments'
    )

# =========================================================
# APPROVE USER
# CHO ONLY
# =========================================================

@role_required('CHO')
def approve_user(request, user_id):

    user = get_object_or_404(
        UserAccount,
        id=user_id
    )

    user.account_status = 'APPROVED'
    user.is_active = True

    user.save(
        update_fields=[
            'account_status',
            'is_active',
        ]
    )

    # -----------------------------------------------------
    # SPECIAL MESSAGE FOR BHW
    # -----------------------------------------------------

    if user.role == 'BHW':

        messages.success(
            request,
            f'{user.username} has been approved. '
            f'You can now assign this BHW to a Barangay '
            f'under BHW Assignments.'
        )

    else:

        messages.success(
            request,
            f'{user.username} has been approved.'
        )

    return redirect(
        'user_management'
    )

# =========================================================
# REJECT USER
# CHO ONLY
# =========================================================

@role_required('CHO')
def reject_user(
    request,
    user_id
):

    try:

        user = UserAccount.objects.get(
            id=user_id
        )

        user.account_status = 'REJECTED'

        user.is_active = False

        user.save()

        messages.success(
            request,
            f'{user.username} has been rejected.'
        )

    except UserAccount.DoesNotExist:

        messages.error(
            request,
            'User account not found.'
        )

    return redirect(
        'user_management'
    )


# =========================================================
# PROFILE
# =========================================================

@login_required(login_url='login')
def profile(request):

    user = request.user

    if request.method == 'POST':

        first_name = request.POST.get(
            'first_name',
            ''
        ).strip()

        middle_name = request.POST.get(
            'middle_name',
            ''
        ).strip()

        last_name = request.POST.get(
            'last_name',
            ''
        ).strip()

        email = request.POST.get(
            'email',
            ''
        ).strip()

        contact_number = request.POST.get(
            'contact_number',
            ''
        ).strip()

        address = request.POST.get(
            'address',
            ''
        ).strip()

        profile_picture = request.FILES.get(
            'profile_picture'
        )

        # =========================================
        # CLEAR PROFILE PICTURE
        # =========================================

        if request.POST.get("clear_profile_picture") == "1":

            if user.profile_picture:

                user.profile_picture.delete(
                    save=False
                )

                user.profile_picture = None

                user.save(
                    update_fields=["profile_picture"]
                )

            messages.success(
                request,
                "Profile picture has been cleared."
            )

            return redirect("profile")


        # ---------------------------------------------
        # UPDATE PERSONAL INFORMATION
        # ---------------------------------------------

        user.first_name = first_name

        user.middle_name = middle_name

        user.last_name = last_name

        user.email = email

        user.contact_number = contact_number

        user.address = address

        # ---------------------------------------------
        # UPDATE PROFILE PICTURE
        # ---------------------------------------------

        if profile_picture:

            user.profile_picture = profile_picture

        user.save()

        messages.success(
            request,
            'Your profile has been successfully updated.'
        )

        return redirect('profile')

    context = {
        'user': user,
    }

    return render(
        request,
        'profile.html',
        context
    )

# =========================================================
# LOGOUT
# =========================================================

@login_required(login_url='login')
def logout_view(request):

    logout(request)

    messages.success(
        request,
        'You have successfully logged out.'
    )

    return redirect(
        'login'
    )
