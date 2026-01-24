import smtplib
from email.mime.text import MIMEText

host = "smtp.gmail.com"
port = 587
user = "musombiwilliam769@gmail.com"
password = "gpuzmjftxkdbtjou"
to = "musombiwilliam769@gmail.com"  # try sending to yourself first

msg = MIMEText("Test email from RevelaCode")
msg["Subject"] = "Test SMTP"
msg["From"] = user
msg["To"] = to

try:
    server = smtplib.SMTP(host, port)
    server.set_debuglevel(1)  # prints SMTP conversation
    server.starttls()
    server.login(user, password)
    server.send_message(msg)
    print("✅ Email sent!")
    server.quit()
except Exception as e:
    print("❌ SMTP error:", e)
