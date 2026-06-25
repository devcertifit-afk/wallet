from django.db import transaction
from .models import StripeTransaction, Company

class BillingService:
    def charge_ticket_purchase(self, ticket_order, gross_amount) -> StripeTransaction:
        """Stub method. Will be implemented in Phase 2."""
        raise NotImplementedError("charge_ticket_purchase is not implemented yet.")

    def charge_gym_member(self, gym_member, plan) -> StripeTransaction:
        """Stub method. Will be implemented in Phase 3."""
        raise NotImplementedError("charge_gym_member is not implemented yet.")

    def charge_cafe_order(self, order) -> StripeTransaction:
        """Stub method. Will be implemented in Phase 4."""
        raise NotImplementedError("charge_cafe_order is not implemented yet.")
