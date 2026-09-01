import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def send_password_reset_email(to_email: str, reset_link: str):
    subject = "Password Reset Request"

    body = f"""
    Hello,

    We received a request to reset your password. Click the link below to set a new password:

    {reset_link}

    This link will expire in 30 minutes. If you did not request this, please ignore this email.

    Thanks,
    Your App Team
    """

    message = MIMEMultipart()
    message["From"] = GMAIL_ADDRESS
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_email, message.as_string())
        print(f"Password reset email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise