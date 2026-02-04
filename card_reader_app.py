"""
Suica Card Reader for Access Control System
Uses Sony RC-S380 NFC Reader with pyscard library
Designed for use in Japan
"""

from smartcard.System import readers
import json
import os
from datetime import datetime
import pytz
import time
import sys
import ctypes
import tkinter as tk
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# File paths
USERS_FILE = "authorized_users.json"
LOG_FILE = "access_log.txt"

# Japan timezone
JAPAN_TZ = pytz.timezone('Asia/Tokyo')

# Get UID/IDm command (works for most contactless cards)
GET_UID_CMD = [0xFF, 0xCA, 0x00, 0x00, 0x00]

# Global cache for authorized users
_cached_users = {}
_last_mtime = 0

def load_authorized_users():
    """Load authorized users from JSON file with caching."""
    global _cached_users, _last_mtime
    
    if not os.path.exists(USERS_FILE):
        return {}
    
    try:
        current_mtime = os.path.getmtime(USERS_FILE)
        if current_mtime == _last_mtime:
            return _cached_users
            
        # File changed or first load
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                print(f"Warning: The file '{USERS_FILE}' is empty.")
                new_users = {}
            else:
                data = json.loads(content)
                # Create a dictionary for quick lookup: card_number -> name
                if 'users' in data:
                    new_users = {user['card_number'].upper(): user['name'] for user in data['users']}
                else:
                    new_users = {}
        
        _cached_users = new_users
        _last_mtime = current_mtime
        print(f"Loaded {len(_cached_users)} authorized users.")
        return _cached_users
            
    except json.JSONDecodeError:
        print(f"Error: Failed to parse '{USERS_FILE}'. Invalid JSON.")
        return _cached_users # Return last known good state
    except Exception as e:
        print(f"Error loading users: {e}")
        return _cached_users


def log_access(card_number, user_name, action="Access Granted"):
    """Log successful access to the log file."""
    japan_time = datetime.now(JAPAN_TZ)
    timestamp = japan_time.strftime("%Y-%m-%d %H:%M:%S JST")
    
    log_entry = f"{timestamp} | {action} | Card: {card_number} | User: {user_name}\n"
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)
    
    print(f"Log: {log_entry.strip()}")


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


def process_card(card_number, authorized_users):
    """Process the card and check authorization."""
    print("\n" + "=" * 50)
    print("カードを検出しました / Card detected!")
    print(f"Card Number (IDm): {card_number}")
    
    if card_number in authorized_users:
        user_name = authorized_users[card_number]
        print("\n" + "★" * 20)
        print(f"✓ アクセス許可 / ACCESS GRANTED")
        print(f"ようこそ、{user_name}さん!")
        print(f"Welcome to the system, {user_name}!")
        print("★" * 20)
        
        # Log successful access
        log_access(card_number, user_name, "Access Granted")
    else:
        print("\n" + "✗" * 20)
        print("✗ アクセス拒否 / ACCESS DENIED")
        print("このカードは登録されていません。")
        print("This card is not registered.")
        print("✗" * 20)
    
    print("=" * 50)


class AccessControlApp:
    def __init__(self, reader):
        self.reader = reader
        self.root = tk.Tk()
        self.root.title("DLX NFC Access Control")
        self.root.configure(bg='white')
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        
        # Default size
        w, h = 700, 900

        # Center the window
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)
        self.root.geometry('%dx%d+%d+%d' % (w, h, x, y))
        
        # Create Canvas for layout with background
        self.canvas = tk.Canvas(self.root, width=w, height=h, highlightthickness=0, bg='white')
        self.canvas.pack(fill="both", expand=True)

        # Load Background Image
        self.bg_photo = None
        if HAS_PIL and os.path.exists("app-bg.jpg"):
            try:
                bg_img = Image.open("app-bg.jpg")
                # Resize keeping aspect ratio? Or fill? 
                # Let's fill the window
                bg_img = bg_img.resize((w, h), Image.Resampling.LANCZOS)
                self.bg_photo = ImageTk.PhotoImage(bg_img)
                self.canvas.create_image(0, 0, image=self.bg_photo, anchor="nw")
            except Exception as e:
                print(f"Could not load background: {e}")

        # Draw Text
        current_y = 700 # Center vertically
        
        # Assuming black text ensures visibility if previously white background
        text_color = "black" if not self.bg_photo else "white" 
        
        self.text_id = self.canvas.create_text(w/2, current_y, text="Waiting for card...", 
                                             font=("Arial", 20), fill=text_color, justify="center")
        
        self.timer_id = self.canvas.create_text(w/2, h - 50, text="", 
                                              font=("Arial", 22, "bold"), fill="magenta")
        
        self.last_card = None
        self.last_user_name = None
        
        self.no_card_start_time = time.time()
        self.TIMEOUT_SECONDS = 20
        self.last_display_text = ""
        
        # Start the check loop
        self.root.after(100, self.check_loop)
        
        # Handle close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def on_close(self):
        print("Application closed by user.")
        self.root.destroy()
        sys.exit(0)
        
    def read_card(self):
        """Helper to read card UID safely."""
        try:
            connection = self.reader.createConnection()
            connection.connect()
            card_uid = get_card_uid(connection)
            connection.disconnect()
            return card_uid
        except Exception:
            return None

    def check_loop(self):
        try:
            # 2. Read Card
            card_number = self.read_card()
            
            # 3. Process Card State
            status = "NO_CARD"
            user_name = None
            authorized_users = {}
            
            if card_number:
                authorized_users = load_authorized_users()
                if card_number in authorized_users:
                    status = "AUTHORIZED"
                    user_name = authorized_users[card_number]
                else:
                    status = "UNAUTHORIZED"

            # 4. Handle Access Logic (Edge Detection)
            if card_number != self.last_card:
                # State Changed
                if self.last_card and self.last_user_name:
                    print(f"\nCard removed: {self.last_card} (User: {self.last_user_name})")
                    log_access(self.last_card, self.last_user_name, "Session Ended")
                
                if card_number:
                    process_card(card_number, authorized_users)
                    
                self.last_card = card_number
                self.last_user_name = user_name

            # 5. UI & Timeout Logic
            # Check if workstation is locked
            is_locked = (ctypes.windll.user32.GetForegroundWindow() == 0)

            if status == "AUTHORIZED":
                # Valid Card - Hide UI, Stop Timeout
                self.no_card_start_time = None 
                self.root.withdraw()

            elif is_locked:
                # Workstation is locked - Pause/Reset Timer
                self.no_card_start_time = None
                self.root.withdraw()
            
            else:
                # No Card OR Unauthorized - Show UI, Run Timeout
                display_text = "Please place card on reader\nカードをかざしてください"
                if status == "UNAUTHORIZED":
                    display_text = "Card Not Registered\nカードは未登録です"
                
                self.root.deiconify()
                self.root.attributes('-topmost', True)
                # Update text on canvas only if changed
                if display_text != self.last_display_text:
                    self.canvas.itemconfigure(self.text_id, text=display_text)
                    self.last_display_text = display_text
                
                # Start timeout if not running
                if self.no_card_start_time is None:
                    self.no_card_start_time = time.time()
                
                # Check Expiry
                elapsed = time.time() - self.no_card_start_time
                remaining = self.TIMEOUT_SECONDS - elapsed
                
                if remaining <= 0:
                    print(f"\nTimeout: No valid access for {self.TIMEOUT_SECONDS} seconds.")
                    print("Locking Windows Session...")
                    try:
                        ctypes.windll.user32.LockWorkStation()
                    except Exception as e:
                        print(f"Failed to lock workstation: {e}")
                    
                    # Reset timer
                    self.no_card_start_time = time.time()
                    remaining = self.TIMEOUT_SECONDS
                
                self.canvas.itemconfigure(self.timer_id, text=f"Auto Lock in: {remaining:.0f} ")

        except Exception as e:
            print(f"Loop error: {e}")
        
        # Schedule next check
        self.root.after(1000, self.check_loop)

    def run(self):
        self.root.mainloop()


def main():
    """Main function to run the Suica card reader."""
    print("=" * 60)
    print("  Suica Card Access Control System")
    print("  スイカカード アクセス制御システム")
    print("  Sony RC-S380 NFC Reader (pyscard)")
    print("=" * 60)
    
    # Load authorized users at startup
    authorized_users = load_authorized_users()
    print(f"\n登録ユーザー数 / Registered users: {len(authorized_users)}")
    
    # Display current Japan time
    japan_time = datetime.now(JAPAN_TZ)
    print(f"現在時刻 / Current time: {japan_time.strftime('%Y-%m-%d %H:%M:%S JST')}")
    
    # Get available readers
    try:
        available_readers = readers()
    except Exception as e:
        print(f"Error listing readers: {e}")
        return
    
    if not available_readers:
        print("\nリーダーが見つかりません / No readers found!")
        print("Please connect your Sony RC-S380 reader.")
        return
    
    print(f"\n検出されたリーダー / Detected readers:")
    for i, reader in enumerate(available_readers):
        print(f"  [{i}] {reader}")
    
    # Select the first reader
    reader = available_readers[0]
    print(f"\n使用するリーダー / Using reader: {reader}")
    
    print("\nStarting Access Control with Timeout Monitor...")
    print("(Popup window will handle timeout)")
    print("-" * 40)
    
    # Start the App
    app = AccessControlApp(reader)
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n\nシステムを終了します / Exiting system...")


if __name__ == "__main__":
    main()