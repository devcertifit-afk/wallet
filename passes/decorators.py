from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from functools import wraps

def merchant_required(view_func):
    """Decorator to ensure user is authenticated and belongs to a merchant company."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Save the target URL to redirect back after login
            return redirect(f"/login/?next={request.path}")
        
        if not hasattr(request.user, 'employee'):
            messages.error(request, "This account is not associated with a merchant company.")
            return redirect("/login/")
        
        # Inject employee and company context into the request object
        request.employee = request.user.employee
        request.company = request.user.employee.company
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def roles_required(allowed_roles):
    """Decorator to restrict access to specific employee roles."""
    def decorator(view_func):
        @wraps(view_func)
        @merchant_required
        def _wrapped_view(request, *args, **kwargs):
            if request.employee.role not in allowed_roles:
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
