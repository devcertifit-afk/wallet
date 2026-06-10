from django.shortcuts import render, redirect
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Company, Employee, PassTemplate, PassInstance, PassAnalytics
from .serializers import CompanySerializer, PassTemplateSerializer, PassInstanceSerializer, PassAnalyticsSerializer
from django.db import transaction
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from .utils.pass_generator import ApplePassGenerator, GoogleWalletGenerator



def landing_page(request):
    return render(request, 'landing.html')

class CompanyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

class PassTemplateViewSet(viewsets.ModelViewSet):
    queryset = PassTemplate.objects.all()
    serializer_class = PassTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Allow filtering by company
        company_id = self.request.query_params.get('company')
        if company_id:
            return self.queryset.filter(company_id=company_id)
        return self.queryset

class PassInstanceViewSet(viewsets.ModelViewSet):
    queryset = PassInstance.objects.all()
    serializer_class = PassInstanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'serial_number'

    def get_queryset(self):
        # Allow filtering by template or company
        template_id = self.request.query_params.get('template')
        company_id = self.request.query_params.get('company')
        if template_id:
            return self.queryset.filter(template_id=template_id)
        if company_id:
            return self.queryset.filter(template__company_id=company_id)
        return self.queryset


    @action(detail=True, methods=['post'])
    def redeem(self, request, serial_number=None):
        """Redeem a pass instance value (subtract from balance)."""
        pass_instance = self.get_object()
        amount = request.data.get('amount')
        
        if not amount:
            return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            amount_val = Decimal(amount)
            if amount_val <= 0:
                return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, InvalidOperation):
            return Response({'error': 'Amount must be a number'}, status=status.HTTP_400_BAD_REQUEST)

        # Loyalty specific validation
        if pass_instance.template.pass_type == 'LOYALTY':
            if amount_val % 1 != 0:
                return Response({'error': 'Points must be a whole number (no decimals)'}, status=status.HTTP_400_BAD_REQUEST)
            amount_val = Decimal(int(amount_val))

        if pass_instance.balance < amount_val:
            return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            pass_instance.balance -= amount_val
            pass_instance.save()
            
            # Log Analytics Event
            PassAnalytics.objects.create(
                company=pass_instance.template.company,
                pass_instance=pass_instance,
                event_type=PassAnalytics.EventTypes.REDEMPTION,
                value_changed=-amount_val
            )
            
            # TODO: Trigger Google/Apple Wallet API updates asynchronously
            
        return Response(PassInstanceSerializer(pass_instance).data)

    @action(detail=True, methods=['post'])
    def add_points(self, request, serial_number=None):
        """Add points or value to a pass instance balance."""
        pass_instance = self.get_object()
        amount = request.data.get('amount')
        
        if not amount:
            return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            amount_val = Decimal(amount)
            if amount_val <= 0:
                return Response({'error': 'Amount must be positive'}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, InvalidOperation):
            return Response({'error': 'Amount must be a number'}, status=status.HTTP_400_BAD_REQUEST)

        # Loyalty specific validation
        if pass_instance.template.pass_type == 'LOYALTY':
            if amount_val % 1 != 0:
                return Response({'error': 'Points must be a whole number (no decimals)'}, status=status.HTTP_400_BAD_REQUEST)
            amount_val = Decimal(int(amount_val))

        with transaction.atomic():
            pass_instance.balance += amount_val
            pass_instance.save()
            
            # Log Analytics Event
            PassAnalytics.objects.create(
                company=pass_instance.template.company,
                pass_instance=pass_instance,
                event_type=PassAnalytics.EventTypes.UPDATE,
                value_changed=amount_val
            )
            
            # TODO: Trigger Google/Apple Wallet API updates asynchronously
            
        return Response(PassInstanceSerializer(pass_instance).data)

    @action(detail=True, methods=['get'])
    def apple(self, request, serial_number=None):
        """Generate and download Apple Wallet pkpass package."""
        pass_instance = self.get_object()
        
        # Log Analytics Event
        PassAnalytics.objects.create(
            company=pass_instance.template.company,
            pass_instance=pass_instance,
            event_type=PassAnalytics.EventTypes.INSTALL,
            value_changed=0.00
        )
        
        generator = ApplePassGenerator(pass_instance)
        pkpass_bytes = generator.generate_pkpass()
        
        response = HttpResponse(pkpass_bytes, content_type='application/vnd.apple.pkpass')
        response['Content-Disposition'] = f'attachment; filename="pass_{pass_instance.serial_number}.pkpass"'
        return response

    @action(detail=True, methods=['get'])
    def google(self, request, serial_number=None):
        """Generate Save to Google Wallet JWT link."""
        pass_instance = self.get_object()
        
        # Log Analytics Event
        PassAnalytics.objects.create(
            company=pass_instance.template.company,
            pass_instance=pass_instance,
            event_type=PassAnalytics.EventTypes.INSTALL,
            value_changed=0.00
        )
        
        generator = GoogleWalletGenerator(pass_instance)
        save_url = generator.generate_save_url()
        return Response({'save_url': save_url})


class PassAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PassAnalytics.objects.all()
    serializer_class = PassAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        company_id = self.request.query_params.get('company')
        if company_id:
            return self.queryset.filter(company_id=company_id)
        return self.queryset


# ======================================================================
# MERCHANT DASHBOARD VIEWS
# ======================================================================

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils.text import slugify
from .decorators import merchant_required, roles_required
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count

def dashboard_register(request):
    """Register a new merchant company, owner user, and employee profile."""
    if request.user.is_authenticated and hasattr(request.user, 'employee'):
        return redirect('dashboard-index')

    if request.method == 'POST':
        company_name = request.POST.get('company_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        # Validations
        if not all([company_name, username, email, password]):
            messages.error(request, "All fields are required.")
            return redirect('landing')
            
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists. Please choose another one.")
            return redirect('landing')
            
        try:
            with transaction.atomic():
                # Create Company
                slug = slugify(company_name)
                # Ensure slug uniqueness
                base_slug = slug
                counter = 1
                while Company.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                
                company = Company.objects.create(name=company_name, slug=slug)
                
                # Create User
                user = User.objects.create_user(username=username, email=email, password=password)
                
                # Create Employee profile
                Employee.objects.create(
                    user=user,
                    company=company,
                    role=Employee.Roles.OWNER
                )
                
                # Log the user in
                login(request, user)
                
                messages.success(request, f"Welcome to PassFlow, {company_name}! Your account has been created.")
                return redirect('dashboard-index')
        except Exception as e:
            messages.error(request, f"Registration failed: {str(e)}")
            return redirect('landing')
            
    return redirect('landing')

def dashboard_login(request):
    """Elegantly styled login page for merchants and employees."""
    if request.user.is_authenticated and hasattr(request.user, 'employee'):
        return redirect('dashboard-index')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        next_path = request.POST.get('next', 'dashboard-index')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if hasattr(user, 'employee') or user.is_superuser:
                login(request, user)
                
                # Superuser quick fallback: link to a default company if none exists
                if user.is_superuser and not hasattr(user, 'employee'):
                    company, _ = Company.objects.get_or_create(name="Platform Admin Corp", slug="admin-corp")
                    Employee.objects.get_or_create(user=user, company=company, role=Employee.Roles.OWNER)
                
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect(next_path if next_path else 'dashboard-index')
            else:
                messages.error(request, "This account does not have merchant access.")
        else:
            messages.error(request, "Invalid username or password.")

    next_url = request.GET.get('next', 'dashboard-index')
    return render(request, 'registration/login.html', {'next': next_url})

def dashboard_logout(request):
    """Log out employee and redirect to landing page."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('landing')

@merchant_required
def dashboard_index(request):
    """Main stats and analytics dashboard for the company."""
    company = request.company
    
    # 1. Statistics Cards
    total_active_passes = PassInstance.objects.filter(template__company=company, is_active=True).count()
    total_redemptions = PassAnalytics.objects.filter(
        company=company, 
        event_type=PassAnalytics.EventTypes.REDEMPTION
    ).count()
    total_points_decimal = PassInstance.objects.filter(
        template__company=company, 
        template__pass_type=PassTemplate.PassTypes.LOYALTY, 
        is_active=True
    ).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')
    total_points = int(total_points_decimal)
    
    uninstalls = PassAnalytics.objects.filter(company=company, event_type=PassAnalytics.EventTypes.UNINSTALL).count()
    installs = PassAnalytics.objects.filter(company=company, event_type=PassAnalytics.EventTypes.INSTALL).count()
    uninstall_rate = 0.0
    if installs > 0:
        uninstall_rate = round((uninstalls / installs) * 100, 1)

    # 2. Past 30 Days Installation Graph
    today = timezone.localdate()
    thirty_days_ago = today - timedelta(days=29)
    
    installs_by_day = PassAnalytics.objects.filter(
        company=company,
        event_type=PassAnalytics.EventTypes.INSTALL,
        timestamp__date__gte=thirty_days_ago
    ).values('timestamp__date').annotate(count=Count('id')).order_by('timestamp__date')
    
    installs_map = {item['timestamp__date']: item['count'] for item in installs_by_day}
    
    trend_data = []
    current_date = thirty_days_ago
    max_val = 1
    while current_date <= today:
        cnt = installs_map.get(current_date, 0)
        trend_data.append({
            'label': current_date.strftime('%d %b'),
            'value': cnt
        })
        if cnt > max_val:
            max_val = cnt
        current_date += timedelta(days=1)

    # Compile SVG polyline coordinates (600x150 dimensions)
    svg_width = 600
    svg_height = 150
    padding = 15
    step_x = (svg_width - 2 * padding) / 29
    
    points = []
    for idx, day in enumerate(trend_data):
        x = padding + idx * step_x
        y = (svg_height - padding) - (day['value'] / max_val) * (svg_height - 2 * padding)
        points.append(f"{x:.1f},{y:.1f}")
    
    svg_points = " ".join(points)
    recent_activity = PassAnalytics.objects.filter(company=company).order_by('-timestamp')[:5]

    context = {
        'employee': request.employee,
        'company': company,
        'total_active_passes': total_active_passes,
        'total_redemptions': total_redemptions,
        'total_points': total_points,
        'uninstall_rate': uninstall_rate,
        'recent_activity': recent_activity,
        'svg_points': svg_points,
        'svg_width': svg_width,
        'svg_height': svg_height,
        'trend_data': trend_data,
    }
    return render(request, 'dashboard/index.html', context)

@merchant_required
def dashboard_templates(request):
    """View and manage company pass designs."""
    company = request.company
    
    if request.method == 'POST':
        # Restrict creation to Owner and Admin roles
        if request.employee.role not in [Employee.Roles.OWNER, Employee.Roles.ADMIN]:
            messages.error(request, "Only Owners or Admins can create templates.")
            return redirect('dashboard-templates')

        title = request.POST.get('title')
        pass_type = request.POST.get('pass_type')
        description = request.POST.get('description', '')
        bg_color = request.POST.get('background_color', '#4f46e5')
        fg_color = request.POST.get('foreground_color', '#ffffff')
        label_color = request.POST.get('label_color', '#ffffff')
        sku = request.POST.get('sku', '').strip() or None
        
        custom_metadata_str = request.POST.get('custom_metadata', '').strip()
        custom_metadata = {}
        if custom_metadata_str:
            import json
            try:
                custom_metadata = json.loads(custom_metadata_str)
                if not isinstance(custom_metadata, dict):
                    messages.error(request, "Custom metadata must be a JSON dictionary (e.g. {\"key\": \"value\"}).")
                    return redirect('dashboard-templates')
            except json.JSONDecodeError:
                messages.error(request, "Invalid JSON format in custom metadata.")
                return redirect('dashboard-templates')
        
        # Collect default template values based on pass type
        default_data = {}
        if pass_type == 'EVENT_TICKET':
            default_data = {
                'default_event_name': request.POST.get('default_event_name', '').strip(),
                'default_venue': request.POST.get('default_venue', '').strip(),
            }
        elif pass_type == 'COUPON':
            default_data = {
                'default_discount': request.POST.get('default_discount', '').strip(),
            }
        elif pass_type == 'BOARDING_PASS':
            default_data = {
                'default_carrier': request.POST.get('default_carrier', '').strip(),
                'default_origin': request.POST.get('default_origin', '').strip(),
            }
        elif pass_type == 'MEMBERSHIP':
            default_data = {
                'default_tier': request.POST.get('default_tier', '').strip(),
            }

        # Generate Class IDs (Mock default setup)
        apple_pass_id = f"pass.com.{company.slug}.{slugify(title)}"
        google_class_id = f"3388000000000000000.{company.slug}_{slugify(title)}"

        PassTemplate.objects.create(
            company=company,
            title=title,
            pass_type=pass_type,
            description=description,
            background_color=bg_color,
            foreground_color=fg_color,
            label_color=label_color,
            apple_pass_type_id=apple_pass_id,
            google_class_id=google_class_id,
            sku=sku,
            custom_metadata=custom_metadata,
            default_data=default_data
        )
        messages.success(request, "Pass template created successfully!")
        return redirect('dashboard-templates')

    templates = PassTemplate.objects.filter(company=company).order_by('-created_at')
    context = {
        'employee': request.employee,
        'company': company,
        'templates': templates,
        'pass_types': PassTemplate.PassTypes.choices,
    }
    return render(request, 'dashboard/templates.html', context)

@merchant_required
def dashboard_instances(request):
    """View and manage individual issued customer passes."""
    company = request.company
    
    if request.method == 'POST':
        # Create new pass instance
        template_id = request.POST.get('template_id')
        customer_name = request.POST.get('customer_name')
        customer_email = request.POST.get('customer_email')
        try:
            template = PassTemplate.objects.get(id=template_id, company=company)
            initial_balance_val = Decimal(request.POST.get('initial_balance', '0'))
            if template.pass_type == 'LOYALTY':
                initial_balance = Decimal(int(initial_balance_val))
            else:
                initial_balance = initial_balance_val
            
            # Collect pass specific instance parameters
            pass_data = {}
            if template.pass_type == 'EVENT_TICKET':
                pass_data = {
                    'event_name': request.POST.get('event_name', '').strip() or template.default_data.get('default_event_name', ''),
                    'venue': request.POST.get('venue', '').strip() or template.default_data.get('default_venue', ''),
                    'event_date': request.POST.get('event_date', '').strip(),
                    'seat': request.POST.get('seat', '').strip(),
                }
            elif template.pass_type == 'COUPON':
                pass_data = {
                    'discount_value': request.POST.get('discount_value', '').strip() or template.default_data.get('default_discount', ''),
                    'coupon_code': request.POST.get('coupon_code', '').strip(),
                    'expires_at': request.POST.get('expires_at', '').strip(),
                }
            elif template.pass_type == 'BOARDING_PASS':
                pass_data = {
                    'flight_number': request.POST.get('flight_number', '').strip(),
                    'origin': request.POST.get('origin', '').strip() or template.default_data.get('default_origin', ''),
                    'destination': request.POST.get('destination', '').strip(),
                    'departure_time': request.POST.get('departure_time', '').strip(),
                    'seat': request.POST.get('seat', '').strip(),
                }
            elif template.pass_type == 'MEMBERSHIP':
                pass_data = {
                    'membership_tier': request.POST.get('membership_tier', '').strip() or template.default_data.get('default_tier', 'Standard'),
                    'membership_id': request.POST.get('membership_id', '').strip(),
                    'expires_at': request.POST.get('expires_at', '').strip(),
                }
            elif template.pass_type == 'GENERIC':
                pass_data = {
                    'custom_label_1': request.POST.get('custom_label_1', '').strip(),
                    'custom_value_1': request.POST.get('custom_value_1', '').strip(),
                    'custom_label_2': request.POST.get('custom_label_2', '').strip(),
                    'custom_value_2': request.POST.get('custom_value_2', '').strip(),
                }

            with transaction.atomic():
                instance = PassInstance.objects.create(
                    template=template,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    balance=initial_balance,
                    pass_data=pass_data
                )
                
                # Log Creation Event
                PassAnalytics.objects.create(
                    company=company,
                    pass_instance=instance,
                    event_type=PassAnalytics.EventTypes.CREATE,
                    value_changed=initial_balance
                )
            
            messages.success(request, f"Pass issued successfully for {customer_name}!")
        except PassTemplate.DoesNotExist:
            messages.error(request, "Invalid template selection.")
        
        return redirect('dashboard-instances')

    instances = PassInstance.objects.filter(template__company=company).order_by('-created_at')
    templates = PassTemplate.objects.filter(company=company)
    
    context = {
        'employee': request.employee,
        'company': company,
        'instances': instances,
        'templates': templates,
    }
    return render(request, 'dashboard/instances.html', context)

@merchant_required
def dashboard_employees(request):
    """List and manage company employees."""
    company = request.company
    
    if request.method == 'POST':
        # Restrict inviting to Owners/Admins
        if request.employee.role not in [Employee.Roles.OWNER, Employee.Roles.ADMIN]:
            messages.error(request, "Only Owners or Admins can add staff.")
            return redirect('dashboard-employees')

        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role', Employee.Roles.VIEWER)

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('dashboard-employees')

        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            Employee.objects.create(
                user=user,
                company=company,
                role=role
            )
        messages.success(request, f"Employee {username} added successfully!")
        return redirect('dashboard-employees')

    employees = Employee.objects.filter(company=company).order_by('role')
    context = {
        'employee': request.employee,
        'company': company,
        'employees': employees,
        'roles': Employee.Roles.choices,
    }
    return render(request, 'dashboard/employees.html', context)

