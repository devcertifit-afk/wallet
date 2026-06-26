from django.contrib import admin
from .models import Venue, Event, TicketOrder

@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'address', 'total_capacity')
    search_fields = ('name', 'company__name')

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'venue', 'date', 'is_published')
    list_filter = ('is_published', 'date')
    search_fields = ('name', 'company__name')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(TicketOrder)
class TicketOrderAdmin(admin.ModelAdmin):
    list_display = ('order_ref', 'event', 'buyer_name', 'buyer_email', 'ticket_type', 'is_scanned')
    list_filter = ('is_scanned', 'ticket_type')
    search_fields = ('order_ref', 'buyer_name', 'buyer_email')
