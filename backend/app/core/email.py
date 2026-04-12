
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.app.core.config import settings


def send_otp_email(to_email: str, full_name: str, otp: str) -> None:
    """Send a 6-digit OTP to the user for password reset."""

    subject = f"{settings.EMAILS_FROM_NAME} — Your Password Reset Code"

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Inter,Arial,sans-serif;background:#F4F7FC;padding:40px 20px;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;
              box-shadow:0 4px 20px rgba(0,0,0,0.08);overflow:hidden;">
    <div style="background:linear-gradient(135deg,#5352ED,#403EA0);padding:32px 40px;text-align:center;">
      <h1 style="color:#fff;font-size:22px;margin:0;">{settings.EMAILS_FROM_NAME}</h1>
      <p style="color:rgba(255,255,255,0.8);margin:8px 0 0;font-size:13px;">Password Reset Request</p>
    </div>
    <div style="padding:36px 40px;">
      <p style="font-size:15px;color:#2D3436;margin:0 0 6px;">Hi {full_name},</p>
      <p style="color:#747D8C;line-height:1.6;margin:0 0 28px;font-size:14px;">
        Use the code below to reset your password.
        It expires in <strong>10 minutes</strong>.
      </p>
      <div style="background:#EEF2FF;border-radius:12px;padding:24px;text-align:center;
                  margin-bottom:28px;border:2px dashed #5352ED;">
        <p style="margin:0 0 4px;font-size:11px;color:#747D8C;text-transform:uppercase;
                  letter-spacing:1.5px;">Verification Code</p>
        <p style="margin:0;font-size:42px;font-weight:800;color:#5352ED;
                  letter-spacing:10px;">{otp}</p>
      </div>
      <p style="color:#A4B0BE;font-size:13px;line-height:1.6;">
        If you did not request this, ignore this email.
        Your password will <strong>not</strong> be changed.
      </p>
    </div>
    <div style="background:#F4F7FC;padding:16px 40px;text-align:center;">
      <p style="margin:0;font-size:11px;color:#A4B0BE;">
        &copy; 2026 {settings.EMAILS_FROM_NAME}. All rights reserved.
      </p>
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{settings.EMAILS_FROM_NAME} <{settings.SMTP_USER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as srv:
        srv.ehlo()
        srv.starttls()
        srv.login(settings.SMTP_USER, settings.SMTP_PASS)
        srv.sendmail(settings.SMTP_USER, to_email, msg.as_string())
