def current_account(request):
    """Expose the signed-in user's consistent display details to templates."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'current_user_name': 'Authorized personnel', 'current_user_role': ''}

    return {
        'current_user_name': user.get_full_name().strip() or user.username,
        'current_user_role': user.get_role_display(),
    }
