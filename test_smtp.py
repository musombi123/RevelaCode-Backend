import os
import smtplib
from email.mime.text import MIMEText
from flask import Flask, jsonify

app = Flask(__name__)

user = os.getenv("EMAIL_USER")      # Set this on Render
password = os.getenv("EMAIL_PASS")  # Set this on Render
to = user

@app.route("/test-email", methods=["GET"])
def test_email():
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(user, password)

        msg = MIMEText("Render production email test from RevelaCode 🚀")
        msg["Subject"] = "Render SMTP Test"
        msg["From"] = user
        msg["To"] = to

        server.send_message(msg)
        server.quit()
        return jsonify({"status": "success", "message": "Email sent from Render"})

    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500

if __name__ == "__main__":
    app.run()
