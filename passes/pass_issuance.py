from django.db import transaction
from .models import PassInstance, PassAnalytics, PassTemplate, Company

class PassIssuanceService:
    def issue_event_ticket(self, ticket_order, seat) -> PassInstance:
        """Stub method. Will be implemented in Phase 2."""
        raise NotImplementedError("issue_event_ticket is not implemented yet.")

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
