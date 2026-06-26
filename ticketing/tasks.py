import logging
import threading
from django.db import transaction
from ticketing.models import TicketOrder
from ticketing.pdf import TicketPDFGenerator
from passes.pass_issuance import PassIssuanceService

logger = logging.getLogger(__name__)

def fulfill_ticket_order_task(order_id):
    """
    Background worker task to fulfill a ticket order:
    1. Creates Apple/Google Wallet PassInstance.
    2. Renders PDF / HTML printable ticket.
    3. Saves generated urls to order.
    """
    logger.info(f"Asynchronous ticket fulfillment started for Order ID {order_id}")
    try:
        # Fetch order
        order = TicketOrder.objects.get(id=order_id)
        
        # 1. Issue Wallet Pass
        issuance_service = PassIssuanceService()
        pass_instance = issuance_service.issue_event_ticket(order)
        
        # 2. Render PDF Ticket (WeasyPrint / HTML fallback)
        pdf_generator = TicketPDFGenerator()
        pdf_url = pdf_generator.generate_ticket_pdf(order, pass_instance)
        
        # 3. Save details
        with transaction.atomic():
            order.pdf_url = pdf_url
            order.save()
            
        logger.info(f"Fulfillment successfully completed for Order ID {order_id}. PDF URL: {pdf_url}")
    except Exception as e:
        logger.error(f"Fulfillment failed for Order ID {order_id}: {str(e)}", exc_info=True)

def trigger_order_fulfillment_async(order):
    """
    Triggers order fulfillment asynchronously.
    In production, dispatches a Google Cloud Task webhook to Cloud Run.
    In local development, spawns a Python daemon thread.
    """
    from django.conf import settings
    import json
    
    project = getattr(settings, 'GCP_PROJECT_ID', None)
    location = getattr(settings, 'GCP_LOCATION', 'europe-west3')
    queue = getattr(settings, 'GCP_TASKS_QUEUE_NAME', 'ticketing-fulfillment')
    domain = getattr(settings, 'APP_DOMAIN', '')

    # Check if we should use Google Cloud Tasks (production mode)
    use_cloud_tasks = not settings.DEBUG and project and domain

    if use_cloud_tasks:
        try:
            from google.cloud import tasks_v2
            client = tasks_v2.CloudTasksClient()
            parent = client.queue_path(project, location, queue)
            
            url = f"https://{domain}/api/v1/tasks/fulfill/"
            payload = {'order_id': order.id}
            
            task = {
                'http_request': {
                    'http_method': tasks_v2.HttpMethod.POST,
                    'url': url,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps(payload).encode('utf-8'),
                    # OIDC authentication token (Cloud Run IAM security)
                    'oidc_token': {
                        'service_account_email': settings.GOOGLE_SERVICE_ACCOUNT_EMAIL,
                    }
                }
            }
            
            response = client.create_task(request={'parent': parent, 'task': task})
            logger.info(f"Dispatched Google Cloud Task for Order ID {order.id}. Task Name: {response.name}")
            return
        except Exception as e:
            logger.error(f"Failed to dispatch Cloud Task: {str(e)}", exc_info=True)
            if not settings.DEBUG:
                # Do not fall back to background thread in production (it will be throttled by Cloud Run)
                raise

    # Local background thread fallback
    thread = threading.Thread(target=fulfill_ticket_order_task, args=(order.id,))
    thread.daemon = True
    thread.start()
    logger.info(f"Dispatched background fulfillment thread for Order ID {order.id}")
