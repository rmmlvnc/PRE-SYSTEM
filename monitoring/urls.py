from django.urls import path
from . import views
from . import api


urlpatterns = [

    # =====================================================
    # MOBILE APPLICATION API (React Native / Expo)
    # =====================================================
    path("api/mobile/health/", api.health, name="api_mobile_health"),
    path("api/mobile/locations/", api.locations, name="api_mobile_locations"),
    path("api/mobile/boundaries/", api.iligan_barangay_boundaries, name="api_iligan_barangay_boundaries"),
    path("api/mobile/auth/register/", api.register_resident, name="api_mobile_register"),
    path("api/mobile/auth/login/", api.login_mobile, name="api_mobile_login"),
    path("api/mobile/auth/logout/", api.logout_mobile, name="api_mobile_logout"),
    path("api/mobile/me/", api.me, name="api_mobile_me"),
    path("api/mobile/hotspots/", api.hotspots, name="api_mobile_hotspots"),
    path("api/mobile/alerts/", api.alerts, name="api_mobile_alerts"),
    path("api/mobile/community-reports/", api.community_reports, name="api_mobile_community_reports"),

    # =====================================================
    # HOME
    # =====================================================

    path(
        "",
        views.home,
        name="home"
    ),


    # =====================================================
    # AUTHENTICATION
    # =====================================================

    path(
        "login/",
        views.login_view,
        name="login"
    ),

    path(
        "register/",
        views.register,
        name="register"
    ),

    path(
        "logout/",
        views.logout_view,
        name="logout"
    ),


    # =====================================================
    # GENERAL DASHBOARD
    # =====================================================

    path(
        "dashboard/",
        views.dashboard,
        name="dashboard"
    ),


    # =====================================================
    # CHO DASHBOARD
    # =====================================================

    path(
        "dashboard/cho/",
        views.cho_dashboard,
        name="cho_dashboard"
    ),


    # =====================================================
    # CHO - DENGUE CASES
    # =====================================================

    path(
        "cases/",
        views.cases,
        name="cases"
    ),


    # =====================================================
    # CHO - HOTSPOT MAP
    # =====================================================

    path(
        "hotspot-map/",
        views.hotspot_map,
        name="hotspot_map"
    ),


    # =====================================================
    # CHO - AI PREDICTIONS
    # =====================================================

    path(
        "predictions/",
        views.predictions,
        name="predictions"
    ),


    # =====================================================
    # LGU - AI PREDICTIONS
    # =====================================================

    path(
        "lgu/ai-predictions/",
        views.lgu_ai_predictions,
        name="lgu_ai_predictions"
    ),


    # =====================================================
    # CHO - REPORTS
    # =====================================================

    path(
        "reports/",
        views.reports,
        name="reports"
    ),


    # =====================================================
    # CHO - BARANGAY & PUROK
    # =====================================================

    path(
        "cho/barangay-purok/",
        views.barangay_purok,
        name="barangay_purok"
    ),

    path(
        "cho/barangay/add/",
        views.add_barangay,
        name="add_barangay"
    ),

    path(
        "cho/barangay/<int:barangay_id>/update/",
        views.update_barangay,
        name="update_barangay"
    ),

    path(
        "cho/barangay/<int:barangay_id>/delete/",
        views.delete_barangay,
        name="delete_barangay"
    ),

    path(
        "cho/purok/add/",
        views.add_purok,
        name="add_purok"
    ),

    path(
        "cho/purok/<int:purok_id>/update/",
        views.update_purok,
        name="update_purok"
    ),

    path(
        "cho/purok/<int:purok_id>/delete/",
        views.delete_purok,
        name="delete_purok"
    ),


    # =====================================================
    # CHO - PENDING REQUESTS
    # =====================================================

    path(
        "cho/pending-requests/",
        views.pending_requests,
        name="pending_requests"
    ),


    # =====================================================
    # CHO - BHW ASSIGNMENTS
    # =====================================================

    path(
        "cho/bhw-assignments/",
        views.bhw_assignments,
        name="bhw_assignments"
    ),

    path(
        "cho/community-reports/",
        views.community_reports_review,
        name="community_reports_review"
    ),
    path(
        "cho/community-reports/<int:report_id>/review/",
        views.review_community_report,
        name="review_community_report"
    ),

    path(
        "cho/bhw-assignments/<int:user_id>/assign/",
        views.assign_bhw_area,
        name="assign_bhw_area"
    ),

    path(
        "cho/bhw-assignments/<int:user_id>/remove/",
        views.remove_bhw_assignment,
        name="remove_bhw_assignment"
    ),


    # =====================================================
    # CHO - USER MANAGEMENT
    # =====================================================

    path(
        "user-management/",
        views.user_management,
        name="user_management"
    ),

    path(
        "user-management/approve/<int:user_id>/",
        views.approve_user,
        name="approve_user"
    ),

    path(
        "user-management/reject/<int:user_id>/",
        views.reject_user,
        name="reject_user"
    ),


    # =====================================================
    # LGU DASHBOARD
    # =====================================================

    path(
        "lgu-dashboard/",
        views.lgu_dashboard,
        name="lgu_dashboard"
    ),


    # =====================================================
    # LGU - CITY-WIDE MONITORING
    # =====================================================

    path(
        "city-wide-monitoring/",
        views.city_wide_monitoring,
        name="city_wide_monitoring"
    ),


    # =====================================================
    # LGU - HOTSPOT MAP
    # =====================================================

    path(
        "lgu-hotspot-map/",
        views.lgu_hotspot_map,
        name="lgu_hotspot_map"
    ),


    # =====================================================
    # LGU - RISK LEVELS
    # =====================================================

    path(
        "lgu-risk-levels/",
        views.lgu_risk_levels,
        name="lgu_risk_levels"
    ),


    # =====================================================
    # LGU - AI PREDICTIONS
    # =====================================================

    path(
        "lgu/ai-predictions/",
        views.lgu_ai_predictions,
        name="lgu_ai_predictions"
    ),


    # =====================================================
    # LGU - REPORTS & ANALYTICS
    # =====================================================

    path(
        "lgu-reports/",
        views.lgu_reports,
        name="lgu_reports"
    ),


    # =====================================================
    # LGU - DENGUE REPORTS
    # =====================================================

    path(
        "lgu-dengue-reports/",
        views.lgu_dengue_reports,
        name="lgu_dengue_reports"
    ),


    # =====================================================
    # LGU - PROFILE
    # =====================================================

    path(
        "lgu-profile/",
        views.lgu_profile,
        name="lgu_profile"
    ),


    # =====================================================
    # CHW DASHBOARD
    # =====================================================

    path(
        "dashboard/chw/",
        views.chw_dashboard,
        name="chw_dashboard"
    ),


    # =====================================================
    # BHW DASHBOARD
    # =====================================================

    path(
        "dashboard/bhw/",
        views.bhw_dashboard,
        name="bhw_dashboard"
    ),


    # =====================================================
    # BHW - DENGUE CASE
    # =====================================================

    path(
        "bhw/dengue-cases/",
        views.dengue_case_bhw,
        name="dengue_case_bhw"
    ),

    path(
        'profile/',
        views.profile,
        name='profile'
    ),

    # =====================================================
    # BHW - HOTSPOT INFORMATION
    # =====================================================

    path(
        "bhw/hotspot-information/",
        views.bhw_hotspot_information,
        name="bhw_hotspot_information"
    ),
]
