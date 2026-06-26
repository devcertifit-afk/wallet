import os
import uuid
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status as rest_status
from rest_framework.permissions import IsAuthenticated

from passes.models import Company, PassInstance, StripeTransaction, PassAnalytics
from passes.decorators import merchant_required
from passes.billing import BillingService
from ticketing.models import Venue, Event, TicketOrder
from ticketing.tasks import trigger_order_fulfillment_async

logger = logging.getLogger(__name__)

try:
    import stripe
except ImportError:
    stripe = None

# ======================================================================
# PUBLIC EVENT PURCHASING VIEWS
# ======================================================================

def organizer_profile(request, organizer_slug):
    """Public organizer profile listing their events."""
    company = get_object_or_404(Company, slug=organizer_slug, vertical='TICKETING')
    events = Event.objects.filter(company=company, is_published=True).order_by('date')
    return render(request, 'ticketing/organizer_profile.html', {
        'company': company,
        'events': events
    })

def event_detail(request, organizer_slug, event_slug):
    """Public detail page for a ticketing event."""
    company = get_object_or_404(Company, slug=organizer_slug, vertical='TICKETING')
    event = get_object_or_404(Event, company=company, slug=event_slug, is_published=True)
    return render(request, 'ticketing/event_detail.html', {
        'company': company,
        'event': event
    })

def initiate_checkout(request, organizer_slug, event_slug):
    """Initiates checkout. Redirects to Stripe or Local Mock checkout if Stripe is unconfigured."""
    company = get_object_or_404(Company, slug=organizer_slug, vertical='TICKETING')
    event = get_object_or_404(Event, company=company, slug=event_slug, is_published=True)
    
    if request.method == 'POST':
        ticket_type = request.POST.get('ticket_type')
        buyer_name = request.POST.get('buyer_name', '').strip()
        buyer_email = request.POST.get('buyer_email', '').strip()
        
        # Validation
        if not all([ticket_type, buyer_name, buyer_email]):
            return render(request, 'ticketing/event_detail.html', {
                'company': company,
                'event': event,
                'error': 'All fields are required.'
            })
            
        # Parse ticket types configuration to find matching price
        ticket_config = None
        for tt in event.ticket_types:
            if tt.get('name') == ticket_type:
                ticket_config = tt
                break
                
        if not ticket_config:
            return render(request, 'ticketing/event_detail.html', {
                'company': company,
                'event': event,
                'error': 'Invalid ticket type selected.'
            })
            
        price = float(ticket_config.get('price', 0))
        order_ref = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        
        with transaction.atomic():
            order = TicketOrder.objects.create(
                event=event,
                order_ref=order_ref,
                ticket_type=ticket_type,
                buyer_name=buyer_name,
                buyer_email=buyer_email
            )
            
        # Check if Stripe keys are configured
        stripe_secret = getattr(settings, 'STRIPE_SECRET_KEY', '')
        if stripe and stripe_secret:
            try:
                stripe.api_key = stripe_secret
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{
                        'price_data': {
                            'currency': 'eur',
                            'product_data': {
                                'name': f"{event.name} - {ticket_type}",
                            },
                            'unit_amount': int(price * 100),
                        },
                        'quantity': 1,
                    }],
                    mode='payment',
                    success_url=request.build_absolute_uri(
                        reverse('order-confirm', kwargs={'organizer_slug': organizer_slug, 'event_slug': event_slug})
                    ) + f"?order_ref={order_ref}&session_id={'{CHECKOUT_SESSION_ID}'}",
                    cancel_url=request.build_absolute_uri(
                        reverse('event-detail', kwargs={'organizer_slug': organizer_slug, 'event_slug': event_slug})
                    ),
                    metadata={
                        'order_ref': order_ref,
                    }
                )
                return redirect(session.url)
            except Exception as e:
                logger.error(f"Failed to create Stripe Checkout session: {str(e)}")
                # Fail gracefully to mock checkout
                
        # Mock Stripe checkout fallback for local tests and keyless local environments
        return redirect(reverse('mock-stripe-checkout') + f"?order_ref={order_ref}&amount={price}")

    return redirect('event-detail', organizer_slug=organizer_slug, event_slug=event_slug)

def mock_stripe_checkout(request):
    """A styled local simulation of the Stripe payment gateway."""
    order_ref = request.GET.get('order_ref')
    amount = request.GET.get('amount')
    
    order = get_object_or_404(TicketOrder, order_ref=order_ref)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'pay':
            # 1. Create Mock Stripe Transaction log
            billing_service = BillingService()
            billing_service.charge_ticket_purchase(order, amount)
            
            # 2. Trigger asynchronous pass and PDF generation
            trigger_order_fulfillment_async(order)
            
            # 3. Redirect to confirm page
            organizer_slug = order.event.company.slug
            event_slug = order.event.slug
            return redirect(reverse('order-confirm', kwargs={'organizer_slug': organizer_slug, 'event_slug': event_slug}) + f"?order_ref={order_ref}")
        else:
            return redirect('landing')

    return render(request, 'ticketing/mock_checkout.html', {
        'order': order,
        'amount': amount
    })

def order_confirm(request, organizer_slug, event_slug):
    """Order confirmation success page showing loading state and download links."""
    company = get_object_or_404(Company, slug=organizer_slug, vertical='TICKETING')
    event = get_object_or_404(Event, company=company, slug=event_slug, is_published=True)
    order_ref = request.GET.get('order_ref')
    order = get_object_or_404(TicketOrder, order_ref=order_ref, event=event)
    
    # Check if Stripe checkout returned success and fulfill it here if not already done
    stripe_session_id = request.GET.get('session_id')
    if stripe_session_id and not order.stripe_transaction:
        billing_service = BillingService()
        billing_service.charge_ticket_purchase(order, order.event.ticket_types[0].get('price', 0), stripe_session_id)
        trigger_order_fulfillment_async(order)
        
    return render(request, 'ticketing/confirm.html', {
        'company': company,
        'event': event,
        'order': order
    })

def order_status_api(request, order_ref):
    """Endpoint for frontend AJAX polling to check if passes/PDF are generated."""
    order = get_object_or_404(TicketOrder, order_ref=order_ref)
    if order.pdf_url and order.pass_instance:
        return JsonResponse({
            'status': 'success',
            'pdf_url': order.pdf_url,
            'apple_url': reverse('instance-apple', kwargs={'serial_number': order.pass_instance.serial_number}),
            'google_url': reverse('instance-google', kwargs={'serial_number': order.pass_instance.serial_number}),
        })
    return JsonResponse({'status': 'pending'})


# ======================================================================
# MERCHANT DASHBOARD & DOOR SCANNER VIEWS
# ======================================================================

@merchant_required
def dashboard_events(request):
    """Lists organizer events in the merchant backoffice."""
    if request.company.vertical != 'TICKETING':
        return HttpResponseForbidden("Not authorized for Ticketing dashboard.")
        
    events = Event.objects.filter(company=request.company).order_by('-date')
    return render(request, 'ticketing/dashboard/events.html', {
        'employee': request.employee,
        'company': request.company,
        'events': events
    })

@merchant_required
def dashboard_events_new(request):
    """Form and view to create a new ticketing event."""
    if request.company.vertical != 'TICKETING':
        return HttpResponseForbidden("Not authorized for Ticketing dashboard.")
        
    venues = Venue.objects.filter(company=request.company)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        venue_id = request.POST.get('venue')
        date_str = request.POST.get('date')
        description = request.POST.get('description', '')
        
        # Ticket type pricing configurations
        ticket_type_names = request.POST.getlist('ticket_type_name[]')
        ticket_type_prices = request.POST.getlist('ticket_type_price[]')
        ticket_type_qtys = request.POST.getlist('ticket_type_qty[]')
        
        ticket_types = []
        for n, p, q in zip(ticket_type_names, ticket_type_prices, ticket_type_qtys):
            if n.strip() and p.strip() and q.strip():
                ticket_types.append({
                    'name': n.strip(),
                    'price': float(p),
                    'qty': int(q)
                })
        
        from django.utils.text import slugify
        slug = slugify(name)
        base_slug = slug
        counter = 1
        while Event.objects.filter(company=request.company, slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            
        venue = get_object_or_404(Venue, id=venue_id, company=request.company)
        
        Event.objects.create(
            company=request.company,
            venue=venue,
            slug=slug,
            name=name,
            date=date_str,
            description=description,
            ticket_types=ticket_types,
            is_published=True
        )
        return redirect('dashboard-events')
        
    return render(request, 'ticketing/dashboard/events_new.html', {
        'employee': request.employee,
        'company': request.company,
        'venues': venues
    })

@merchant_required
def dashboard_events_detail(request, event_slug):
    """Manage event details and display the attendee checklist."""
    if request.company.vertical != 'TICKETING':
        return HttpResponseForbidden("Not authorized for Ticketing dashboard.")
        
    event = get_object_or_404(Event, company=request.company, slug=event_slug)
    orders = TicketOrder.objects.filter(event=event).order_by('-id')
    return render(request, 'ticketing/dashboard/events_detail.html', {
        'employee': request.employee,
        'company': request.company,
        'event': event,
        'orders': orders
    })

@merchant_required
def dashboard_events_scanner(request, event_slug):
    """The door check-in scanner camera interface."""
    if request.company.vertical != 'TICKETING':
        return HttpResponseForbidden("Not authorized for Ticketing dashboard.")
        
    event = get_object_or_404(Event, company=request.company, slug=event_slug)
    return render(request, 'ticketing/dashboard/scanner.html', {
        'employee': request.employee,
        'company': request.company,
        'event': event
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dashboard_events_scan_api(request, event_slug):
    """
    API endpoint invoked by the QR camera JS to validate a scan.
    Verifies that the scanning user belongs to the event hosting company.
    """
    # 1. Verify that the scanning user is a merchant employee of the same company
    if not hasattr(request.user, 'employee'):
        return Response({'error': 'Unauthorized staff account.'}, status=rest_status.HTTP_403_FORBIDDEN)
        
    event = get_object_or_404(Event, slug=event_slug)
    company = request.user.employee.company
    if event.company != company:
        return Response({'error': 'Unauthorized to scan tickets for this event.'}, status=rest_status.HTTP_403_FORBIDDEN)
        
    # 2. Parse scan reference
    qr_data = request.data.get('qr_data', '').strip()
    if not qr_data:
        return Response({'error': 'No QR code data provided.'}, status=rest_status.HTTP_400_BAD_REQUEST)
        
    # Look up order (either by order_ref or pass instance serial number if valid UUID)
    query = Q(order_ref=qr_data)
    try:
        uuid_val = uuid.UUID(qr_data)
        query |= Q(pass_instance__serial_number=uuid_val)
    except ValueError:
        pass
        
    order = TicketOrder.objects.filter(event=event).filter(query).first()
    
    if not order:
        return Response({'status': 'invalid', 'error': 'Ticket does not belong to this event.'}, status=rest_status.HTTP_404_NOT_FOUND)
        
    # 3. Check if already scanned
    if order.is_scanned:
        return Response({
            'status': 'already_scanned',
            'buyer_name': order.buyer_name,
            'ticket_type': order.ticket_type,
            'scanned_at': order.scanned_at.strftime('%Y-%m-%d %H:%M:%S') if order.scanned_at else "unknown",
            'scanned_by': order.scanned_by.username if order.scanned_by else "unknown"
        })
        
    # 4. Successful check-in
    with transaction.atomic():
        order.is_scanned = True
        order.scanned_at = timezone.now()
        order.scanned_by = request.user
        order.save()
        
        # Log TICKET_SCANNED event
        if order.pass_instance:
            PassAnalytics.objects.create(
                company=company,
                pass_instance=order.pass_instance,
                event_type=PassAnalytics.EventTypes.TICKET_SCANNED,
                value_changed=0.00
            )
            
    return Response({
        'status': 'success',
        'buyer_name': order.buyer_name,
        'ticket_type': order.ticket_type
    })

@api_view(['POST'])
@permission_classes([])
def tasks_order_fulfill_webhook(request):
    """
    HTTP Webhook endpoint called by Google Cloud Tasks to fulfill an order.
    """
    order_id = request.data.get('order_id')
    if not order_id:
        return Response({'error': 'Missing order_id'}, status=rest_status.HTTP_400_BAD_REQUEST)
        
    try:
        from ticketing.tasks import fulfill_ticket_order_task
        fulfill_ticket_order_task(order_id)
        return Response({'status': 'completed'})
    except Exception as e:
        logger.error(f"Webhook fulfillment failed: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=rest_status.HTTP_500_INTERNAL_SERVER_ERROR)
