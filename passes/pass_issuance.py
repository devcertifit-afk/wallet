from django.db import transaction
from .models import PassInstance, PassAnalytics, PassTemplate, Company

class PassIssuanceService:
    def issue_event_ticket(self, ticket_order, seat=None) -> PassInstance:
        """Create a new event ticket pass instance for a buyer."""
        from decimal import Decimal
        
        template = PassTemplate.objects.filter(
            company=ticket_order.event.company,
            pass_type=PassTemplate.PassTypes.EVENT_TICKET
        ).first()
        
        if not template:
            template = PassTemplate.objects.create(
                company=ticket_order.event.company,
                pass_type=PassTemplate.PassTypes.EVENT_TICKET,
                title=ticket_order.event.name[:100],
                background_color='#1e1b4b',
                foreground_color='#ffffff'
            )
            
        with transaction.atomic():
            pass_instance = PassInstance.objects.create(
                template=template,
                customer_name=ticket_order.buyer_name,
                customer_email=ticket_order.buyer_email,
                balance=Decimal('0.00'),
                vertical='TICKETING',
                pass_data={
                    "event_name": ticket_order.event.name,
                    "venue": ticket_order.event.venue.name,
                    "event_date": ticket_order.event.date.strftime('%B %d, %Y %I:%M %p') if ticket_order.event.date else "TBD",
                    "seat": seat or "General Admission",
                    "order_ref": ticket_order.order_ref
                }
            )
            
            # Link it to the order
            ticket_order.pass_instance = pass_instance
            ticket_order.save()
            
            # Log analytics
            PassAnalytics.objects.create(
                company=ticket_order.event.company,
                pass_instance=pass_instance,
                event_type=PassAnalytics.EventTypes.CREATE,
                value_changed=Decimal('0.00')
            )
            
            return pass_instance

    def issue_membership_card(self, gym_member, plan) -> PassInstance:
        """Stub method. Will be implemented in Phase 3."""
        raise NotImplementedError("issue_membership_card is not implemented yet.")

    def issue_loyalty_card(self, company, customer_name, customer_email, template, initial_balance=0.00, phone="") -> PassInstance:
        """Create a new loyalty card (pass instance) for a customer."""
        with transaction.atomic():
            pass_instance = PassInstance.objects.create(
                template=template,
                customer_name=customer_name,
                customer_email=customer_email,
                phone=phone,
                balance=initial_balance,
                vertical='CAFE'  # Default vertical for loyalty cards in our SaaS core
            )
            # Log analytics event
            PassAnalytics.objects.create(
                company=company,
                pass_instance=pass_instance,
                event_type=PassAnalytics.EventTypes.CREATE,
                value_changed=initial_balance
            )
            return pass_instance

    def push_update(self, pass_instance, updated_fields=None) -> None:
        """
        Generic hook stub for triggering Apple/Google wallet pushes.
        Left empty for now (to be implemented in future phases).
        """
        pass
