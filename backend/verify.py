# backend/verify.py
import random
import time
import json
import os

CODES_FILE = './backend/verification_codes.json'
CODE_EXPIRY_SECONDS = 300  # 5 minutes

def load_codes():
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_codes(codes):
    with open(CODES_FILE, 'w') as f:
        json.dump(codes, f, indent=2)

def generate_code():
    return f"{random.randint(100000, 999999)}"

def send_code(destination, code, method='email'):
    # TODO: replace this with real SMS / Email gateway integration
    print(f"[DEV MODE] Sending verification code '{code}' to {destination} via {method}")

def request_verification(destination, method='email'):
    codes = load_codes()
    code = generate_code()
    codes[destination] = {
        'code': code,
        'timestamp': time.time()
    }
    save_codes(codes)
    send_code(destination, code, method)
    print(f"✅ Verification code sent to {destination}.")

def verify_code(destination, submitted_code):
    codes = load_codes()
    record = codes.get(destination)

    if not record:
        print("⚠ No verification request found.")
        return False

    # Check expiry
    if time.time() - record['timestamp'] > CODE_EXPIRY_SECONDS:
        print("⌛ Verification code expired.")
        del codes[destination]
        save_codes(codes)
        return False

    # Check correctness
    if record['code'] == submitted_code:
        print("✅ Verification successful!")
        del codes[destination]
        save_codes(codes)
        return True
    else:
        print("❌ Incorrect verification code.")
        return False

if __name__ == "__main__":
    # Quick manual test
    dest = input("Enter email or phone: ").strip()
    request_verification(dest, method='email' if '@' in dest else 'sms')
    code = input("Enter the code you received: ").strip()
    verified = verify_code(dest, code)
    print("Result:", "Success ✅" if verified else "Failed ❌")
