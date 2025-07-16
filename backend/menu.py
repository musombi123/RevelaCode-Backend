# backend/menu.py
from register import register
from login import login_user, guest_mode
from reset_password import reset_password
from delete_account import delete_account
from list_users import list_users

def main_menu():
    while True:
        print("\n=== 📜 RevelaCode Menu ===")
        print("[1] Register new account")
        print("[2] Login")
        print("[3] Continue as guest")
        print("[4] Reset password")
        print("[5] Delete account")
        print("[6] List users (admin only)")
        print("[0] Exit")

        choice = input("Choose option: ").strip()

        if choice == '1':
            register()
        elif choice == '2':
            user, role = login_user()
            if user:
                print(f"✅ Welcome, {user}! Role: {role}")
        elif choice == '3':
            guest_mode()
        elif choice == '4':
            reset_password()
        elif choice == '5':
            delete_account()
        elif choice == '6':
            list_users()
        elif choice == '0':
            print("👋 Exiting. Goodbye!")
            break
        else:
            print("⚠ Invalid choice. Try again.")

if __name__ == "__main__":
    main_menu()
