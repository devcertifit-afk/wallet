from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

class Venue(models.Model):
    company = models.ForeignKey('passes.Company', on_delete=models.CASCADE, related_name='venues')
    name = models.CharField(_("Venue Name"), max_length=255)
    address = models.TextField(_("Address"))
    total_capacity = models.PositiveIntegerField(_("Total Capacity"), default=100)

    class Meta:
        verbose_name = _("Venue")
        verbose_name_plural = _("Venues")

    def __str__(self):
        return f"{self.name} - {self.company.name}"

class Event(models.Model):
    company = models.ForeignKey('passes.Company', on_delete=models.CASCADE, related_name='events')
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='events')
    slug = models.SlugField(_("Slug"), max_length=255)
    name = models.CharField(_("Event Name"), max_length=255)
    date = models.DateTimeField(_("Event Date"))
    description = models.TextField(_("Description"), blank=True)
    ticket_types = models.JSONField(_("Ticket Types"), default=list, help_text=_("JSON array of ticket types: [{'name': 'VIP', 'price': 50.00, 'qty': 100}, ...]"))
    is_published = models.BooleanField(_("Is Published"), default=False)

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        unique_together = [('company', 'slug')]

    def __str__(self):
        return f"{self.name} ({self.date.strftime('%Y-%m-%d')}) - {self.company.name}"

class TicketOrder(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='orders')
    pass_instance = models.OneToOneField('passes.PassInstance', on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_order')
    stripe_transaction = models.OneToOneField('passes.StripeTransaction', on_delete=models.SET_NULL, null=True, blank=True, related_name='order')
    order_ref = models.CharField(_("Order Reference"), max_length=100, unique=True)
    ticket_type = models.CharField(_("Ticket Type"), max_length=100)
    buyer_name = models.CharField(_("Buyer Name"), max_length=255)
    buyer_email = models.EmailField(_("Buyer Email"))
    pdf_url = models.CharField(_("PDF Ticket URL"), max_length=500, blank=True)
    is_scanned = models.BooleanField(_("Is Scanned"), default=False)
    scanned_at = models.DateTimeField(_("Scanned At"), null=True, blank=True)
    scanned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='scanned_tickets')

    class Meta:
        verbose_name = _("Ticket Order")
        verbose_name_plural = _("Ticket Orders")

    def __str__(self):
        return f"{self.order_ref} - {self.buyer_name} ({self.ticket_type})"
