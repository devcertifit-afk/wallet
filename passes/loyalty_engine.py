from decimal import Decimal
from django.db import transaction
from .models import PassInstance, PassAnalytics

class LoyaltyEngine:
    def earn_points(self, pass_instance, amount, vertical, context=None) -> int:
        """
        Processes point/punch earning based on the template's config.
        Updates the pass instance balance or reward list dynamically.
        Returns the points or punches added.
        """
        context = context or {}
        template = pass_instance.template
        config = template.custom_metadata or {}
        
        loyalty_type = config.get('loyalty_type', 'POINTS') # default to POINTS
        
        points_to_add = 0
        
        with transaction.atomic():
            # Ensure balance is Decimal to prevent float vs Decimal operations on in-memory objects
            current_balance = Decimal(str(pass_instance.balance))

            if loyalty_type == 'PUNCH_CARD':
                # Increment punch/visit counter by 1
                points_to_add = 1
                pass_instance.balance = current_balance + Decimal(points_to_add)
                
                # Check for target limit
                target = int(config.get('target_limit', 5))
                if pass_instance.balance >= Decimal(target):
                    # Reset punches
                    pass_instance.balance = Decimal(0)
                    
                    # Unlocked a reward!
                    reward_name = config.get('reward', 'Free Item')
                    pass_data = pass_instance.pass_data or {}
                    rewards = pass_data.get('rewards', [])
                    rewards.append(reward_name)
                    pass_data['rewards'] = rewards
                    pass_instance.pass_data = pass_data
                    
                    # Log analytics for reward unlocked
                    PassAnalytics.objects.create(
                        company=template.company,
                        pass_instance=pass_instance,
                        event_type=PassAnalytics.EventTypes.UPDATE,
                        value_changed=Decimal(0.00)
                    )
            else:
                # Standard points system
                multiplier = Decimal(str(config.get('points_per_eur', 1.0)))
                amount_dec = Decimal(str(amount))
                points_to_add = int(amount_dec * multiplier)
                
                pass_instance.balance = current_balance + Decimal(points_to_add)
                
            pass_instance.save()
            
            # Log analytics event
            PassAnalytics.objects.create(
                company=template.company,
                pass_instance=pass_instance,
                event_type=PassAnalytics.EventTypes.UPDATE,
                value_changed=Decimal(points_to_add)
            )
            
        return points_to_add

    def redeem_points(self, pass_instance, amount) -> None:
        """Subtract points or value from a pass instance balance."""
        amount_dec = Decimal(str(amount))
        if pass_instance.balance < amount_dec:
            raise ValueError("Insufficient balance")
            
        with transaction.atomic():
            pass_instance.balance -= amount_dec
            pass_instance.save()
            
            # Log Analytics Event
            PassAnalytics.objects.create(
                company=pass_instance.template.company,
                pass_instance=pass_instance,
                event_type=PassAnalytics.EventTypes.REDEMPTION,
                value_changed=-amount_dec
            )

    def get_tier(self, pass_instance) -> str:
        """Determines customer loyalty tier based on balance/points."""
        balance = int(pass_instance.balance)
        if balance >= 1000:
            return "Gold"
        elif balance >= 500:
            return "Silver"
        else:
            return "Bronze"

    def evaluate_campaign(self, company, customer) -> list:
        """Stub method. Returns active campaigns for a customer."""
        return []
