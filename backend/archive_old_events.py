import os
import shutil
from datetime import datetime
import json
import smtplib
from email.message import EmailMessage

# === CONFIG ===
events_dir = './events'
archived_dir = './archived'
log_file = os.path.join(archived_dir, 'archive_log.json')

# === Ensure directories exist ===
os.makedirs(archived_dir, exist_ok=True)

# === ARCHIVE LOG ===
def log_archive(filename):
    log_entry = {
        "filename": filename,
        "archived_at": datetime.now().isoformat()
    }

    # Load or initialize the log
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
    else:
        log_data = []

    log_data.append(log_entry)

    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

# === ARCHIVING ===
def archive_old_events():
    for filename in os.listdir(events_dir):
        if filename.startswith('events_') and filename.endswith('.json'):
            date_str = filename.replace('events_', '').replace('.json', '')
            try:
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                if (datetime.now() - file_date).days > 7:
                    src = os.path.join(events_dir, filename)
                    dst = os.path.join(archived_dir, filename)
                    shutil.move(src, dst)
                    log_archive(filename)
                    print(f'📦 Archived: {filename}')
            except ValueError:
                print(f'⚠️ Skipping invalid date file: {filename}')

# === EMAIL SENDER ===
def send_archive_log_email():
    if not os.path.exists(log_file):
        print("No archive log found.")
        return

    with open(log_file, 'r', encoding='utf-8') as f:
        log_content = f.read()

    msg = EmailMessage()
    msg['Subject'] = '📦 Archive Log - Revelacode'
    msg['From'] = 'musombiwilliam769@gmail.com'         # ✅ Your email
    msg['To'] = 'musombiwilliam769@gmail.com'           # ✅ Send to yourself (or change)
    msg.set_content(log_content)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login('musombiwilliam769@gmail.com', 'okgxvjfgpdbugaam')  # ✅ Use Gmail App Password
            smtp.send_message(msg)
            print("✅ Archive log email sent.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# === MAIN RUNNER ===
if __name__ == '__main__':
    archive_old_events()
    send_archive_log_email()
