from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
import uuid

class Company(models.Model):
    VERTICAL_CHOICES = [
        ('TICKETING', _('Ticketing')),
        ('GYM', _('Gym')),
        ('CAFE', _('Cafe')),
    ]
    name = models.CharField(_("Company Name"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=255, unique=True)
    vertical = models.CharField(_("Vertical"), max_length=20, choices=VERTICAL_CHOICES, default='TICKETING')
    custom_domain = models.CharField(_("Custom Domain"), max_length=255, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")

    def __str__(self):
        return self.name

class Location(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='locations')
    name = models.CharField(_("Location Name"), max_length=255)
    address = models.TextField(_("Address"))
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")

    def __str__(self):
        return f"{self.name} - {self.company.name}"

class Employee(models.Model):
    class Roles(models.TextChoices):
        OWNER = 'OWNER', _('Owner')
        ADMIN = 'ADMIN', _('Admin')
        STAFF = 'STAFF', _('Staff')
        VIEWER = 'VIEWER', _('Viewer')

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees')
    role = models.CharField(_("Role"), max_length=20, choices=Roles.choices, default=Roles.VIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Employee")
        verbose_name_plural = _("Employees")

    def __str__(self):
        return f"{self.user.username} - {self.company.name} ({self.get_role_display()})"

class PassTemplate(models.Model):
    class PassTypes(models.TextChoices):
        LOYALTY = 'LOYALTY', _('Loyalty Card')
        GIFT_CARD = 'GIFT_CARD', _('Gift Card')
        MEMBERSHIP = 'MEMBERSHIP', _('Membership Card')
        COUPON = 'COUPON', _('Coupon / Offer')
        EVENT_TICKET = 'EVENT_TICKET', _('Event Ticket')
        BOARDING_PASS = 'BOARDING_PASS', _('Boarding Pass')
        GENERIC = 'GENERIC', _('Generic Pass')

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='templates')
    pass_type = models.CharField(_("Pass Type"), max_length=20, choices=PassTypes.choices)
    title = models.CharField(_("Title"), max_length=100)
    description = models.TextField(_("Description"), blank=True)
    
    # Customization Options
    logo = models.ImageField(_("Logo Image"), upload_to='pass_logos/', blank=True, null=True)
    background_color = models.CharField(_("Background Color (Hex)"), max_length=7, default='#4f46e5')
    foreground_color = models.CharField(_("Foreground Color (Hex)"), max_length=7, default='#ffffff')
    label_color = models.CharField(_("Label Color (Hex)"), max_length=7, default='#ffffff')
    
    # Wallet Identifiers (Shared model by default)
    apple_pass_type_id = models.CharField(_("Apple Pass Type ID"), max_length=100, blank=True)
    google_class_id = models.CharField(_("Google Wallet Class ID"), max_length=255, blank=True)
    
    # Custom Payloads
    sku = models.CharField(_("SKU Code"), max_length=100, blank=True, null=True, help_text=_("Optional product/service SKU code."))
    custom_metadata = models.JSONField(_("Custom Metadata"), default=dict, blank=True, help_text=_("Optional custom developer JSON metadata."))
    default_data = models.JSONField(_("Default Template Data"), default=dict, blank=True, help_text=_("Default key-value dictionary for this card design."))
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Pass Template")
        verbose_name_plural = _("Pass Templates")

    def __str__(self):
        return f"{self.title} ({self.get_pass_type_display()})"

class PassInstance(models.Model):
    VERTICAL_CHOICES = [
        ('TICKETING', _('Ticketing')),
        ('GYM', _('Gym')),
        ('CAFE', _('Cafe')),
    ]
    template = models.ForeignKey(PassTemplate, on_delete=models.CASCADE, related_name='instances')
    serial_number = models.UUIDField(_("Serial Number (Apple)"), default=uuid.uuid4, unique=True, editable=False)
    google_object_id = models.CharField(_("Google Object ID"), max_length=255, unique=True, blank=True, null=True)
    
    # Customer Info
    customer_name = models.CharField(_("Customer Name"), max_length=255, blank=True)
    customer_email = models.EmailField(_("Customer Email"), blank=True)
    phone = models.CharField(_("Phone Number"), max_length=50, blank=True)
    
    # Values
    balance = models.DecimalField(_("Balance (Points/Currency)"), max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(_("Is Active"), default=True)
    pass_data = models.JSONField(_("Pass Instance Data"), default=dict, blank=True, help_text=_("Specific details for this pass instance (e.g. seat, flight, tier, expiry)."))
    
    # Vertical details
    vertical = models.CharField(_("Vertical"), max_length=20, choices=VERTICAL_CHOICES, default='TICKETING')
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='pass_instances')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Pass Instance")
        verbose_name_plural = _("Pass Instances")

    def __str__(self):
        return f"{self.customer_name} - {self.template.title}"

class PassAnalytics(models.Model):
    class EventTypes(models.TextChoices):
        CREATE = 'CREATE', _('Created')
        INSTALL = 'INSTALL', _('Installed')
        UNINSTALL = 'UNINSTALL', _('Uninstalled')
        UPDATE = 'UPDATE', _('Updated')
        REDEMPTION = 'REDEMPTION', _('Redeemed')
        CHECK_IN = 'CHECK_IN', _('Checked In')
        PURCHASE = 'PURCHASE', _('Purchased')
        CLASS_BOOKED = 'CLASS_BOOKED', _('Class Booked')
        TICKET_SCANNED = 'TICKET_SCANNED', _('Ticket Scanned')
        STRIPE_CHARGE = 'STRIPE_CHARGE', _('Stripe Charge')

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='analytics')
    pass_instance = models.ForeignKey(PassInstance, on_delete=models.SET_NULL, null=True, blank=True, related_name='analytics')
    event_type = models.CharField(_("Event Type"), max_length=20, choices=EventTypes.choices)
    value_changed = models.DecimalField(_("Value Changed"), max_digits=10, decimal_places=2, default=0.00, help_text=_("Difference in points or currency balance"))
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Pass Analytics")
        verbose_name_plural = _("Pass Analytics Events")
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.company.name} - {self.get_event_type_display()} at {self.timestamp}"

class StripeTransaction(models.Model):
    VERTICAL_CHOICES = [
        ('TICKETING', _('Ticketing')),
        ('GYM', _('Gym')),
        ('CAFE', _('Cafe')),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stripe_transactions')
    vertical = models.CharField(_("Vertical"), max_length=20, choices=VERTICAL_CHOICES)
    stripe_payment_intent_id = models.CharField(_("Stripe Payment Intent ID"), max_length=255, unique=True)
    amount = models.DecimalField(_("Gross Amount"), max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(_("Platform Fee"), max_digits=10, decimal_places=2)
    status = models.CharField(_("Status"), max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Stripe Transaction")
        verbose_name_plural = _("Stripe Transactions")

    def __str__(self):
        return f"{self.stripe_payment_intent_id} ({self.vertical}) - {self.amount:.2f} EUR"
