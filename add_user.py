"""
Add User Tool for Access Control System
Uses Sony RC-S380 NFC Reader with pyscard library
"""

from smartcard.System import readers
import json
import os
import time
import msvcrt
import sys

# File paths
USERS_FILE = "authorized_users.json"

# Get UID/IDm command (works for most contactless cards)
GET_UID_CMD = [0xFF, 0xCA, 0x00, 0x00, 0x00]


def load_authorized_users():
    """Load authorized users from JSON file."""
    if not os.path.exists(USERS_FILE):
        print(f"Error: The file '{USERS_FILE}' does not exist.")
        return {}
    
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                print(f"Error: The file '{USERS_FILE}' is empty.")
                return {}
            data = json.loads(content)
            
        # Create a dictionary for quick lookup: card_number -> name
        if 'users' in data:
            return {user['card_number'].upper(): user['name'] for user in data['users']}
        return {}
            
    except json.JSONDecodeError:
        print(f"Error: Failed to parse '{USERS_FILE}'. Invalid JSON.")
        return {}
    except Exception as e:
        print(f"Error loading users: {e}")
        return {}


def get_card_uid(connection):
    """Get the UID/IDm from the card using GET DATA command."""
    try:
        response, sw1, sw2 = connection.transmit(GET_UID_CMD)
        
        if sw1 == 0x90 and sw2 == 0x00:
            # Success - convert response bytes to hex string
            uid = ''.join(format(byte, '02X') for byte in response)
            return uid
        else:
            print(f"GET UID failed with status: {sw1:02X} {sw2:02X}")
            return None
    except Exception as e:
        print(f"Error reading card UID: {e}")
        return None


def save_user_to_file(name, card_number):
    """Save a new user to the JSON file."""
    data = {"users": []}
    
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
        except Exception:
            pass
            
    # Remove existing entry if card exists (update)
    if "users" in data:
        data["users"] = [u for u in data["users"] if u.get("card_number") != card_number]
    else:
        data["users"] = []
        
    data["users"].append({
        "name": name,
        "card_number": card_number
    })
    
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"\nSuccessfully registered: {name} ({card_number})")
        return True
    except Exception as e:
        print(f"Error saving to file: {e}")
        return False


def registration_mode(reader):
    """Handle the user registration process."""
    print("\n" + "+" * 50)
    print("  REGISTRATION MODE / 登録モード")
    print("  Scan card to register... (Press 'x' to cancel)")
    print("+" * 50)
    
    # Clear keyboard buffer
    while msvcrt.kbhit():
        msvcrt.getch()
        
    found_card = None
    
    while not found_card:
        # Check cancel
        if msvcrt.kbhit():
            key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
            if key == 'x':
                print("Registration cancelled.")
                return False
        
        try:
            connection = reader.createConnection()
            connection.connect()
            card_uid = get_card_uid(connection)
            connection.disconnect()
            
            if card_uid:
                found_card = card_uid
                print(f"\nCard Detected: {found_card}")
                
                # Check existing
                users = load_authorized_users()
                if found_card in users:
                    print(f"Current Owner: {users[found_card]}")
                    print("Registering will overwrite this entry.")
                
                # Flush input buffer again
                while msvcrt.kbhit():
                    msvcrt.getch()
                    
                name = input("Enter User Name / 名前を入力: ").strip()
                if name:
                    save_user_to_file(name, found_card)
                    # Ask if want to register another
                    print("\nRegister another card? (y/n)")
                    while True:
                        if msvcrt.kbhit():
                            res = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                            if res == 'y':
                                found_card = None # Reset loop
                                print("\nScan next card...")
                                break
                            elif res == 'n' or res == '\r' or res == '\x1b': # Enter or Esc
                                return True
                            
                else:
                    print("Registration cancelled (empty name).")
                    return False
                    
        except Exception:
            pass
            
        time.sleep(0.2)
    return True


def main():
    """Main function to run the Add User tool."""
    print("=" * 60)
    print("  Add User Tool")
    print("  Sony RC-S380 NFC Reader (pyscard)")
    print("=" * 60)
    
    # Get available readers
    try:
        available_readers = readers()
    except Exception as e:
        print(f"Error listing readers: {e}")
        return
    
    if not available_readers:
        print("\nNo readers found!")
        print("Please connect your Sony RC-S380 reader.")
        return
    
    print(f"\nDetected readers:")
    for i, reader in enumerate(available_readers):
        print(f"  [{i}] {reader}")
    
    # Select the first reader
    reader = available_readers[0]
    print(f"\nUsing reader: {reader}")
    
    registration_mode(reader)
    
    print("\nExiting Add User Tool...")

if __name__ == "__main__":
    main()
