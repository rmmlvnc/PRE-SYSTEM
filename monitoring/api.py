import json
from functools import wraps
from pathlib import Path

from django.contrib.auth import authenticate
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    Alert,
    Barangay,
    CommunityReport,
    HotspotPrediction,
    MobileAccessToken,
    Purok,
    SystemNotification,
    UserAccount,
    notify_user,
    log_report_action,
)
from .ml.service import BLOOD_TYPE_FEATURE_NOTICE, prediction_context
from .locations import ILIGAN_BARANGAYS, canonicalize_barangay
from .views import build_hotspot_data


def _body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None


def _error(message, status=400, fields=None):
    data = {"success": False, "message": message}
    if fields:
        data["errors"] = fields
    return JsonResponse(data, status=status)


def _map_key(value):
    """Match display labels to the official boundary GeoJSON labels."""
    return " ".join(str(value or "").lower().replace("-", " ").replace(".", " ").split())


def _official_barangay_centers():
    """Return one display coordinate per official barangay boundary.

    Historical case records do not contain coordinates. Deriving these points
    from the bundled boundary geometry keeps the resident hotspot map visible
    without inventing a location or using an external map service.
    """
    boundary_path = Path(settings.BASE_DIR) / "static" / "data" / "iligan_barangays.geojson"
    try:
        features = json.loads(boundary_path.read_text(encoding="utf-8")).get("features", [])
    except (OSError, json.JSONDecodeError):
        return {}

    def pairs(value):
        if isinstance(value, list) and len(value) >= 2 and all(isinstance(v, (int, float)) for v in value[:2]):
            return [(float(value[0]), float(value[1]))]
        if isinstance(value, list):
            return [pair for child in value for pair in pairs(child)]
        return []

    centers = {}
    for feature in features:
        name = feature.get("properties", {}).get("brgy_name")
        coordinates = pairs(feature.get("geometry", {}).get("coordinates", []))
        if name and coordinates:
            longitude = sum(pair[0] for pair in coordinates) / len(coordinates)
            latitude = sum(pair[1] for pair in coordinates) / len(coordinates)
            centers[_map_key(name)] = (latitude, longitude)
    return centers


def _historical_map_item(index, item, centers):
    latitude, longitude = centers.get(_map_key(item["barangay"]), (None, None))
    return {
        "id": index,
        "barangay_id": None,
        "barangay": item["barangay"],
        "current_cases": item["case_count"],
        "predicted_cases": item["case_count"],
        "risk_level": item["risk_level"],
        "trend": "Historical case total",
        "latitude": latitude,
        "longitude": longitude,
    }


def _user_data(user):
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "contact_number": user.contact_number,
        "address": user.address,
        "profile_picture": user.profile_picture.url if user.profile_picture else None,
        "role": user.role,
        "account_status": user.account_status,
        "barangay": (
            {"id": user.assigned_barangay_id, "name": user.assigned_barangay.barangay_name}
            if user.assigned_barangay_id else None
        ),
    }


def mobile_auth(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        header = request.headers.get("Authorization", "")
        raw_token = header[7:].strip() if header.startswith("Bearer ") else ""
        user = MobileAccessToken.authenticate(raw_token)
        if not user:
            return _error("Valid mobile access token is required.", status=401)
        request.mobile_user = user
        request.mobile_raw_token = raw_token
        return view(request, *args, **kwargs)

    return wrapped


@require_http_methods(["GET"])
def health(request):
    return JsonResponse({"success": True, "service": "DengueWatch Mobile API", "version": "1.0"})


@csrf_exempt
@require_http_methods(["POST"])
def register_resident(request):
    data = _body(request)
    if data is None:
        return _error("Invalid JSON body.")

    required = ["first_name", "last_name", "email", "password"]
    missing = {name: "This field is required." for name in required if not str(data.get(name, "")).strip()}
    # Mobile may use its bundled official barangay list before the locations
    # endpoint is reachable. In that case the canonical barangay name is the
    # stable identifier; a database-specific primary key is not required.
    if not data.get("barangay_id") and not str(data.get("barangay_name", "")).strip():
        missing["barangay"] = "Please select a barangay."
    if missing:
        return _error("Please complete the required fields.", fields=missing)
    if len(data["password"]) < 8:
        return _error("Password must contain at least 8 characters.", fields={"password": "Too short."})

    barangay = Barangay.objects.filter(pk=data.get("barangay_id")).first()
    if not barangay:
        barangay_name = canonicalize_barangay(data.get("barangay_name", ""))
        barangay = Barangay.objects.filter(barangay_name=barangay_name).first()
    if not barangay:
        return _error("Selected barangay was not found.", fields={"barangay_id": "Invalid barangay."})
    purok = None
    if data.get("purok_id"):
        purok = Purok.objects.filter(pk=data["purok_id"], barangay=barangay).first()
        if not purok:
            return _error("Selected purok does not belong to the barangay.")

    email = data["email"].strip().lower()
    username = email
    try:
        user = UserAccount.objects.create_user(
            username=username,
            email=email,
            password=data["password"],
            first_name=data["first_name"].strip(),
            last_name=data["last_name"].strip(),
            contact_number=str(data.get("contact_number", "")).strip(),
            address=str(data.get("address", "")).strip(),
            role="RESIDENT",
            account_status="APPROVED",
            assigned_barangay=barangay,
            assigned_purok=purok,
        )
    except IntegrityError:
        return _error("An account with this email already exists.", status=409)

    token = MobileAccessToken.issue(user)
    return JsonResponse({"success": True, "token": token, "user": _user_data(user)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def login_mobile(request):
    data = _body(request)
    if data is None:
        return _error("Invalid JSON body.")
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = authenticate(request, username=email, password=password)
    if not user:
        return _error("Incorrect email or password.", status=401)
    if user.role != "RESIDENT":
        return _error(
            "Staff accounts must sign in through the DengueWatch desktop web system.",
            status=403,
        )
    if user.account_status != "APPROVED":
        return _error("This account is not yet approved.", status=403)
    token = MobileAccessToken.issue(user)
    return JsonResponse({"success": True, "token": token, "user": _user_data(user)})


@csrf_exempt
@mobile_auth
@require_http_methods(["POST"])
def logout_mobile(request):
    import hashlib
    token_hash = hashlib.sha256(request.mobile_raw_token.encode()).hexdigest()
    MobileAccessToken.objects.filter(token_hash=token_hash).update(revoked_at=timezone.now())
    return JsonResponse({"success": True, "message": "Logged out successfully."})


@mobile_auth
@require_http_methods(["GET"])
def me(request):
    return JsonResponse({"success": True, "user": _user_data(request.mobile_user)})


@csrf_exempt
@mobile_auth
@require_http_methods(["POST"])
def update_profile(request):
    """Allow a resident to update only their permitted account details."""
    user = request.mobile_user
    email = str(request.POST.get("email", "")).strip().lower()
    contact_number = str(request.POST.get("contact_number", "")).strip()
    address = str(request.POST.get("address", "")).strip()

    if not email:
        return _error("Email address is required.", fields={"email": "Required."})
    if len(contact_number) > 20:
        return _error("Mobile number must contain at most 20 characters.")
    if UserAccount.objects.exclude(pk=user.pk).filter(
        Q(email__iexact=email) | Q(username__iexact=email)
    ).exists():
        return _error("An account with this email already exists.", status=409)

    picture = request.FILES.get("profile_picture")
    if picture:
        if not (picture.content_type or "").startswith("image/"):
            return _error("Profile picture must be an image file.")
        if picture.size > 5 * 1024 * 1024:
            return _error("Profile picture must be 5 MB or smaller.")
        user.profile_picture = picture

    # Deliberately do not accept name, role, assigned area, status, or password
    # in this resident self-service endpoint.
    user.email = email
    user.username = email
    user.contact_number = contact_number
    user.address = address
    update_fields = ["email", "username", "contact_number", "address"]
    if picture:
        update_fields.append("profile_picture")
    user.save(update_fields=update_fields)
    return JsonResponse({"success": True, "user": _user_data(user)})


@require_http_methods(["GET"])
def locations(request):
    """Return a lightweight barangay list for the mobile registration form."""
    barangays = Barangay.objects.filter(
        barangay_name__in=ILIGAN_BARANGAYS
    ).order_by("barangay_name")
    items = [{
        "id": b.pk,
        "name": b.barangay_name,
        "latitude": float(b.latitude) if b.latitude is not None else None,
        "longitude": float(b.longitude) if b.longitude is not None else None,
        "puroks": [],
    } for b in barangays]
    return JsonResponse({"success": True, "barangays": items})


@require_http_methods(["GET"])
def barangay_puroks(request, barangay_id):
    """Return only the Purok/Sitio records for one selected barangay."""
    barangay = Barangay.objects.filter(pk=barangay_id).first()
    if not barangay:
        return _error("Selected barangay was not found.", status=404)
    puroks = Purok.objects.filter(barangay=barangay).order_by("purok_name")
    return JsonResponse({
        "success": True,
        "barangay_id": barangay.pk,
        "puroks": [{"id": p.pk, "name": p.purok_name} for p in puroks],
    })


@require_http_methods(["GET"])
def iligan_barangay_boundaries(request):
    """Local, token-free GeoJSON used by both the web and Expo maps."""
    path = Path(settings.BASE_DIR) / "static" / "data" / "iligan_barangays.geojson"
    try:
        return JsonResponse(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return _error("The local Iligan boundary map is unavailable.", status=503)


@mobile_auth
@require_http_methods(["GET"])
def hotspots(request):
    # Residents see the same historical case-volume classifications as the
    # CHO/LGU heat map. Forecasts remain available to staff as planning data,
    # but must not replace the historical map view on the mobile app.
    if request.GET.get('source') == 'historical':
        historical = build_hotspot_data(request)
        centers = _official_barangay_centers()
        items = [
            _historical_map_item(index, item, centers)
            for index, item in enumerate(historical['hotspot_data'], start=1)
        ]
        return JsonResponse({
            "success": True,
            "source": "historical_dataset",
            "case_data_period": historical['historical_case_period'],
            "historical_case_period": historical['historical_case_period'],
            "selected_year": historical['selected_year'],
            "selected_year_label": historical['selected_year_label'],
            "map_data_source": historical['map_data_source'],
            "hotspots": items,
        })

    context = prediction_context(request)
    if context.get("model_ready"):
        coordinates = {
            item.barangay_name: item
            for item in Barangay.objects.filter(barangay_name__in=ILIGAN_BARANGAYS)
        }
        items = []
        for index, forecast in enumerate(context["forecasts"], start=1):
            name = canonicalize_barangay(forecast["barangay"])
            if not name:
                continue
            barangay = coordinates.get(name)
            items.append({
                "id": index,
                "barangay_id": barangay.pk if barangay else None,
                "barangay": name,
                "forecast_period": context["forecast_period"],
                "case_data_period": context["case_data_period"],
                "predicted_cases": forecast["predicted_cases"],
                "current_cases": forecast["current_cases"],
                "case_change": forecast["case_change"],
                "trend": forecast["trend"],
                "risk_level": forecast["risk_level"],
                "rainfall_mm": forecast["rainfall_mm"],
                "temperature_c": forecast["temperature_c"],
                "humidity_pct": forecast["humidity_pct"],
                "recommendation": forecast["recommendation"],
                # Aggregate historical context only—never an individual risk
                # score, diagnosis, or personally identifiable record.
                "historical_aggregate_common_blood_type": forecast.get(
                    "historical_common_blood_type",
                ),
                "blood_type_feature_notice": BLOOD_TYPE_FEATURE_NOTICE,
                "latitude": float(barangay.latitude) if barangay and barangay.latitude is not None else None,
                "longitude": float(barangay.longitude) if barangay and barangay.longitude is not None else None,
            })
        return JsonResponse({
            "success": True,
            "source": "random_forest_model",
            "forecast_period": context["forecast_period"],
            "case_data_period": context["case_data_period"],
            "weather": context.get("weather", {}),
            "blood_type_by_year": context.get("blood_type_by_year", []),
            "blood_type_feature_notice": BLOOD_TYPE_FEATURE_NOTICE,
            "hotspots": items,
        })

    # When the ML artifact is unavailable, keep the map usable with the same
    # official 44-barangay, historical-data view used by the CHO and LGU web
    # hotspot pages. This is deliberately labeled as historical, not AI output.
    historical = build_hotspot_data(request)
    if historical['hotspot_data']:
        centers = _official_barangay_centers()
        items = [
            _historical_map_item(index, item, centers)
            for index, item in enumerate(historical['hotspot_data'], start=1)
        ]
        return JsonResponse({
            "success": True,
            "source": "historical_dataset",
            "case_data_period": historical['historical_case_period'],
            "historical_case_period": historical['historical_case_period'],
            "selected_year": historical['selected_year'],
            "selected_year_label": historical['selected_year_label'],
            "map_data_source": historical['map_data_source'],
            "warning": context.get("prediction_error", ""),
            "hotspots": items,
        })

    # Database fallback supports manually saved predictions when no source
    # dataset is available.
    latest_ids = []
    for barangay_id in Barangay.objects.filter(
        barangay_name__in=ILIGAN_BARANGAYS
    ).values_list("pk", flat=True):
        latest = HotspotPrediction.objects.filter(barangay_id=barangay_id).order_by("-prediction_date", "-pk").first()
        if latest:
            latest_ids.append(latest.pk)
    predictions = HotspotPrediction.objects.filter(pk__in=latest_ids).select_related("barangay")
    items = [{
        "id": item.pk,
        "barangay_id": item.barangay_id,
        "barangay": item.barangay.barangay_name,
        "prediction_date": item.prediction_date.isoformat(),
        "risk_score": item.risk_score,
        "risk_level": item.risk_level or item.hotspot_level,
        "forecast_result": item.forecast_result,
        "analysis_remarks": item.analysis_remarks,
        "latitude": float(item.latitude) if item.latitude is not None else None,
        "longitude": float(item.longitude) if item.longitude is not None else None,
    } for item in predictions]
    return JsonResponse({
        "success": True,
        "source": "saved_predictions",
        "warning": context.get("prediction_error", ""),
        "hotspots": items,
    })


@mobile_auth
@require_http_methods(["GET"])
def alerts(request):
    user = request.mobile_user
    now = timezone.now()
    queryset = Alert.objects.filter(is_active=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).filter(Q(barangay__isnull=True) | Q(barangay_id=user.assigned_barangay_id)).select_related("barangay")
    items = [{
        "id": item.pk,
        "title": item.title,
        "message": item.message,
        "risk_level": item.risk_level,
        "barangay": item.barangay.barangay_name if item.barangay else "All Iligan City",
        "created_at": item.created_at.isoformat(),
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
    } for item in queryset.order_by("-created_at")[:100]]
    return JsonResponse({"success": True, "alerts": items})


@csrf_exempt
@mobile_auth
@require_http_methods(["GET", "POST"])
def notifications(request):
    """Resident in-app notifications, including replies from CHO."""
    user = request.mobile_user
    if request.method == "POST":
        data = _body(request)
        if data is None:
            return _error("Invalid JSON body.")
        ids = data.get("ids", [])
        if not isinstance(ids, list):
            return _error("Notification ids must be a list.")
        SystemNotification.objects.filter(
            recipient=user, notification_id__in=ids, is_read=False,
        ).update(is_read=True, read_at=timezone.now())
        return JsonResponse({"success": True})

    items = [{
        "id": item.notification_id,
        "type": item.notification_type,
        "title": item.title,
        "message": item.message,
        "link": item.link,
        "is_read": item.is_read,
        "created_at": item.created_at.isoformat(),
    } for item in SystemNotification.objects.filter(recipient=user)[:100]]
    return JsonResponse({"success": True, "notifications": items})


@csrf_exempt
@mobile_auth
@require_http_methods(["GET", "POST"])
def community_reports(request):
    user = request.mobile_user
    if request.method == "GET":
        reports = CommunityReport.objects.filter(resident=user).select_related("barangay", "purok").prefetch_related("audit_logs__actor")
        items = [{
            "id": item.pk,
            "observation_type": item.observation_type,
            "description": item.description,
            "barangay": item.barangay.barangay_name,
            "purok": item.purok.purok_name if item.purok else None,
            "status": item.status,
            "staff_response": item.staff_response,
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
            "submitted_at": item.submitted_at.isoformat(),
            "audit_trail": [{
                "action": audit.action,
                "details": audit.details,
                "actor": audit.actor.get_full_name() or audit.actor.username if audit.actor else "System",
                "created_at": audit.created_at.isoformat(),
            } for audit in item.audit_logs.all()],
        } for item in reports.order_by("-submitted_at")]
        return JsonResponse({"success": True, "reports": items})

    data = _body(request)
    if data is None:
        return _error("Invalid JSON body.")
    observation_type = str(data.get("observation_type", "")).strip()
    description = str(data.get("description", "")).strip()
    if not observation_type or not description:
        return _error("Observation type and description are required.")
    barangay = Barangay.objects.filter(pk=data.get("barangay_id") or user.assigned_barangay_id).first()
    if not barangay:
        return _error("A valid barangay is required.")
    purok = None
    if data.get("purok_id"):
        purok = Purok.objects.filter(pk=data["purok_id"], barangay=barangay).first()
        if not purok:
            return _error("Selected purok does not belong to the barangay.")
    report = CommunityReport.objects.create(
        resident=user,
        barangay=barangay,
        purok=purok,
        observation_type=observation_type,
        description=description,
        latitude=data.get("latitude") or None,
        longitude=data.get("longitude") or None,
    )
    log_report_action(
        actor=user,
        community_report=report,
        action='CREATED',
        details='Resident submitted a community report.',
    )
    for cho in UserAccount.objects.filter(role='CHO', account_status='APPROVED'):
        notify_user(
            cho,
            'REPORT',
            f'New resident {observation_type} report',
            f'{barangay.barangay_name}: {description[:160]}',
            created_by=user,
            link='/cho/community-reports/',
        )
    return JsonResponse({"success": True, "message": "Community report submitted for verification.", "id": report.pk}, status=201)
