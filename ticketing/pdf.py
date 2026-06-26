import os
import logging
from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, Exception) as e:
    logger.warning(f"WeasyPrint is not available, falling back to HTML-based ticket receipt: {str(e)}")
    WEASYPRINT_AVAILABLE = False

class TicketPDFGenerator:
    def generate_ticket_pdf(self, ticket_order, pass_instance=None) -> str:
        """
        Generates a beautiful ticket file.
        Falls back to a printable HTML ticket if WeasyPrint C-libraries are missing.
        Returns the relative URL path to the generated file.
        """
        # Ensure media directory exists
        tickets_dir = os.path.join(settings.MEDIA_ROOT, 'tickets')
        os.makedirs(tickets_dir, exist_ok=True)
        
        # QR Code URL using free API (no external python library required)
        qr_data = ticket_order.order_ref
        qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={qr_data}"
        
        # Date string formatting
        event_date_str = ticket_order.event.date.strftime('%B %d, %Y at %I:%M %p') if ticket_order.event.date else "TBD"
        
        # Build context for template
        context = {
            'order': ticket_order,
            'event': ticket_order.event,
            'venue': ticket_order.event.venue,
            'event_date_str': event_date_str,
            'qr_code_url': qr_code_url,
            'theme_color': '#4f46e5',
        }
        
        # Render HTML template to string
        html_content = render_to_string('ticketing/ticket_pdf_template.html', context)
        
        if WEASYPRINT_AVAILABLE:
            filename = f"ticket_{ticket_order.order_ref}.pdf"
            filepath = os.path.join(tickets_dir, filename)
            try:
                HTML(string=html_content).write_pdf(filepath)
                logger.info(f"Successfully generated PDF ticket at {filepath}")
                return os.path.join(settings.MEDIA_URL, 'tickets', filename).replace('\\', '/')
            except Exception as e:
                logger.error(f"WeasyPrint PDF rendering failed, falling back to HTML: {str(e)}")
                # Continue to HTML fallback
        
        # Fallback: Save as a standalone styled HTML file that is printable
        filename = f"ticket_{ticket_order.order_ref}.html"
        filepath = os.path.join(tickets_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Successfully generated fallback HTML ticket at {filepath}")
        return os.path.join(settings.MEDIA_URL, 'tickets', filename).replace('\\', '/')
