from django.urls import path
from . import views

urlpatterns = [
    # Dashboard routes
    path('dashboard/events/', views.dashboard_events, name='dashboard-events'),
    path('dashboard/events/new/', views.dashboard_events_new, name='dashboard-events-new'),
    path('dashboard/events/<slug:event_slug>/', views.dashboard_events_detail, name='dashboard-events-detail'),
    path('dashboard/events/<slug:event_slug>/scanner/', views.dashboard_events_scanner, name='dashboard-events-scanner'),
    path('dashboard/events/<slug:event_slug>/scanner/scan/', views.dashboard_events_scan_api, name='dashboard-events-scan-api'),
    
    # API endpoints
    path('api/v1/orders/<str:order_ref>/status/', views.order_status_api, name='order-status-api'),
    path('api/v1/tasks/fulfill/', views.tasks_order_fulfill_webhook, name='tasks-order-fulfill-webhook'),
    
    # Public views
    path('checkout/mock/', views.mock_stripe_checkout, name='mock-stripe-checkout'),
    path('<slug:organizer_slug>/', views.organizer_profile, name='organizer-profile'),
    path('<slug:organizer_slug>/<slug:event_slug>/', views.event_detail, name='event-detail'),
    path('<slug:organizer_slug>/<slug:event_slug>/checkout/', views.initiate_checkout, name='initiate-checkout'),
    path('<slug:organizer_slug>/<slug:event_slug>/confirm/', views.order_confirm, name='order-confirm'),
]
