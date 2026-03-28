# stripe_service.py - Stripe payment processing for Clau Trading Backend.
import logging
import stripe
from config import STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)
stripe.api_key = STRIPE_SECRET_KEY

def create_payment_intent(amount: float, currency: str = "usd") -> dict:
    """
    Create a Stripe payment intent.
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # dollars -> cents
            currency=currency,
            payment_method_types=["card"],  # explicit
        )
        
        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "status": intent.status,
        }
    except stripe.error.StripeError as e:
        return {
            "error": str(e),
            "status": "failed"
        }

def confirm_payment(payment_intent_id: str, payment_method_id: str) -> dict:
    """
    Confirm a Stripe PaymentIntent with the client-supplied payment method.
    The payment_method_id is obtained from Stripe.js / Stripe SDK on the client.
    """
    try:
        intent = stripe.PaymentIntent.confirm(
            payment_intent_id,
            payment_method=payment_method_id,
        )
        return {
            "status": intent.status,
            "amount": intent.amount / 100,
            "payment_intent_id": intent.id,
        }
    except stripe.error.StripeError as e:
        return {
            "error": str(e),
            "status": "failed",
        }

def create_connected_account(email: str) -> dict:
    """
    Create a Stripe connected account for a user (TEST MODE).
    """
    try:
        account = stripe.Account.create(
            type="express",
            country="US",
            email=email,
            capabilities={
                "transfers": {"requested": True},
            },
            business_type="individual",
        )

        return {
            "account_id": account.id,
            "details_submitted": account.details_submitted,
            "status": "created"
        }
    except stripe.error.StripeError as e:
        return {
            "error": str(e),
            "status": "failed"
        }

def attach_test_bank_account(stripe_account_id: str) -> dict:
    """
    Attach a TEST bank account to the user's connected account.
    Only for test mode.
    """
    try:
        # Create a test bank token
        bank_token = stripe.Token.create(
            bank_account={
                "country": "US",
                "currency": "usd",
                "account_holder_name": "Test User",
                "account_holder_type": "individual",
                "routing_number": "110000000",
                "account_number": "000123456789",
            }
        )

        # Attach token as external account to connected account
        external = stripe.Account.create_external_account(
            stripe_account_id,
            external_account=bank_token.id,
        )

        return {
            "external_account_id": external.id,
            "status": "attached"
        }
    except stripe.error.StripeError as e:
        return {
            "error": str(e),
            "status": "failed"
        }

def fund_test_account(stripe_account_id: str, amount: float) -> dict:
    """
    Add test balance to connected account (TEST MODE ONLY).
    """
    try:
        logger.info("Funding connected account: %s", stripe_account_id)
        stripe.TestHelpers.Fund.create(
            destination_account=stripe_account_id,
            amount=int(amount * 100),  # dollars -> cents
        )
        
        return {
            "status": "funded",
            "amount": amount
        }
    except stripe.error.StripeError as e:
        logger.error("Stripe fund error: %s", e)
        return {
            "error": str(e),
            "status": "failed"
        }

def create_payout_to_user(stripe_account_id: str, amount: float, currency: str = "usd") -> dict:
    """
    Create a payout from the user's connected account to their bank.
    """
    try:
        payout = stripe.Payout.create(
            amount=int(amount * 100),  # dollars -> cents
            currency=currency,
            method="standard",
            stripe_account=stripe_account_id,
        )

        return {
            "payout_id": payout.id,
            "status": payout.status,
            "amount": payout.amount / 100,
            "arrival_date": payout.arrival_date,
        }
    except stripe.error.StripeError as e:
        logger.error("Stripe payout error: %s", e)
        return {
            "error": str(e),
            "status": "failed"
        }

def create_refund(payment_intent_id: str, amount: float = None) -> dict:
    """
    Create a refund for a payment intent.
    If amount is None, refunds the full amount.
    """
    try:
        refund_data = {"payment_intent": payment_intent_id}
        if amount:
            refund_data["amount"] = int(amount * 100)
        
        refund = stripe.Refund.create(**refund_data)
        return {
            "refund_id": refund.id,
            "status": refund.status,
            "amount": refund.amount / 100
        }
    except stripe.error.StripeError as e:
        return {
            "error": str(e),
            "status": "failed"
        }