
from dotenv import load_dotenv
from decimal import Decimal
from uuid import uuid4

from Adaptors.Payments.RazorpayAdapter import RazorpayAdapter

load_dotenv()


def test_razorpay_adapter():

    print("Initializing Razorpay Adapter...")

    razorpay = RazorpayAdapter()

    print("Adapter initialized successfully!")

    attempt_id = str(uuid4())

    print("\nCreating Razorpay test order...")

    response = razorpay.create_order(
        order_id=attempt_id,
        amount=Decimal("10.00"),
        customer={
            "customer_id": "SB_TEST_USER",
            "phone": "9999999999",
            "email": "test@example.com"
        },
        idempotency_key=f"stablebus-{attempt_id}",
        currency="INR"
    )

    print("\nOrder created successfully!")
    print("Order ID:", response.get("id"))
    print("Amount:", response.get("amount"))
    print("Currency:", response.get("currency"))
    print("Status:", response.get("status"))

    razorpay.close()


if __name__ == "__main__":
    test_razorpay_adapter()
