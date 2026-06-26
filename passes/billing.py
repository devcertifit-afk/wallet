from django.db import transaction
from .models import StripeTransaction, Company

class BillingService:
    def charge_ticket_purchase(self, ticket_order, gross_amount, stripe_payment_intent_id=None) -> StripeTransaction:
        """Charge the ticket purchase and log the StripeTransaction."""
        from django.conf import settings
        from decimal import Decimal
        import uuid
        
        # Calculate platform fee
        platform_fee = getattr(settings, 'TICKETING_FEE_FIXED', Decimal('0.50'))
        
        # Generate dummy payment intent if none provided
        if not stripe_payment_intent_id:
            stripe_payment_intent_id = f"pi_mock_{uuid.uuid4().hex[:12]}"
            
        with transaction.atomic():
            tx = StripeTransaction.objects.create(
                company=ticket_order.event.company,
                vertical='TICKETING',
                stripe_payment_intent_id=stripe_payment_intent_id,
                amount=Decimal(str(gross_amount)),
                platform_fee=platform_fee,
                status='succeeded',
                ticket_order=ticket_order
            )
            
            # Associate transaction back to the ticket order
            ticket_order.stripe_transaction = tx
            ticket_order.save()
            
            return tx

    def charge_gym_member(self, gym_member, plan) -> StripeTransaction:
        """Stub method. Will be implemented in Phase 3."""
        raise NotImplementedError("charge_gym_member is not implemented yet.")

    def charge_cafe_order(self, order) -> StripeTransaction:
        """Stub method. Will be implemented in Phase 4."""
        raise NotImplementedError("charge_cafe_order is not implemented yet.")
