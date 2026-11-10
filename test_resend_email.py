from Adaptors.Notifications.ResendEmailAdapter import (
    ResendEmailAdapter,
)

adapter = ResendEmailAdapter()

try:
    response = adapter.send_email(
        to_email="vamsinagisetti22@gmail.com",
        subject="StableBus - Test Email",
        html="""
        <h2>Welcome to StableBus!</h2>
        <p>Your email notification integration is working.</p>
        <p>Happy journeys!</p>
        """,
        text="StableBus email integration is working!",
    )

    print("Email sent successfully!")
    print("Resend response:", response)

finally:
    adapter.close()