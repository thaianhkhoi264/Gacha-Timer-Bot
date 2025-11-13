# Building External Applications for Shadowverse Match Tracking

This guide shows you how to build an external application that logs Shadowverse matches to your Discord bot via the REST API.

## Table of Contents

- [Quick Start](#quick-start)
- [API Configuration](#api-configuration)
- [API Endpoints](#api-endpoints)
- [Building a Python Application](#building-a-python-application)
- [Building a GUI Application](#building-a-gui-application)
- [Creating an Executable](#creating-an-executable)
- [Error Handling](#error-handling)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### What You Need

1. **API URL**: Your Cloudflare Tunnel URL (e.g., `https://gacha-bot.yourdomain.com`)
2. **API Key**: A secret key from your bot's `api_keys.json` file
3. **Discord User ID**: The user's Discord ID (18-digit number)

### Test Connection

**Windows PowerShell:**
```powershell
# Test if API is reachable
Invoke-WebRequest -Uri "https://your-domain.com/api/health"

# Validate your API key
Invoke-WebRequest -Uri "https://your-domain.com/api/validate_key" `
    -Headers @{"X-API-Key"="your_api_key_here"}
```

**Linux/Mac (or curl.exe on Windows):**
```bash
# Test if API is reachable
curl https://your-domain.com/api/health

# Validate your API key
curl -H "X-API-Key: your_api_key_here" https://your-domain.com/api/validate_key
```

---

## API Configuration

### Required Information

Your application needs these hardcoded values:

```python
# config.py
API_URL = "https://gacha-bot.yourdomain.com"  # Your Cloudflare Tunnel URL
API_KEY = "your_secret_key_here"              # From api_keys.json on bot server
```

### Valid Craft Names

Matches must use these exact strings (case-sensitive):

- `Forestcraft`
- `Swordcraft`
- `Runecraft`
- `Dragoncraft`
- `Abysscraft`
- `Havencraft`
- `Portalcraft`

---

## API Endpoints

### 1. Health Check

**Purpose:** Verify API is running and bot is connected

**Endpoint:** `GET /api/health`

**No authentication required**

**Response:**
```json
{
  "status": "ok",
  "bot_connected": true,
  "bot_user": "Kanami#4362"
}
```

---

### 2. Validate API Key

**Purpose:** Check if your API key is valid

**Endpoint:** `GET /api/validate_key`

**Headers:**
- `X-API-Key`: Your API key

**Response (Success):**
```json
{
  "valid": true,
  "description": "Shared Key - All Users"
}
```

**Response (Invalid):**
```json
{
  "valid": false,
  "error": "Invalid API key."
}
```

---

### 3. Log Match

**Purpose:** Record a Shadowverse match and update Discord dashboard

**Endpoint:** `POST /api/shadowverse/log_match`

**Headers:**
- `X-API-Key`: Your API key
- `Content-Type`: `application/json`

**Request Body:**
```json
{
  "user_id": "123456789012345678",
  "played_craft": "Dragoncraft",
  "opponent_craft": "Forestcraft",
  "win": true,
  "brick": false
}
```

**Parameters:**
- `user_id` (string, required): Discord user ID (18-digit number as string)
- `played_craft` (string, required): Craft you played (see valid crafts above)
- `opponent_craft` (string, required): Craft opponent played
- `win` (boolean, required): `true` if you won, `false` if you lost
- `brick` (boolean, optional): `true` if you bricked, defaults to `false`

**Response (Success):**
```json
{
  "success": true,
  "message": "Match logged successfully and dashboard updated",
  "details": {
    "user_id": "123456789012345678",
    "server_id": "1374399849574961152",
    "played_craft": "Dragoncraft",
    "opponent_craft": "Forestcraft",
    "result": "win",
    "brick": false
  }
}
```

**Response (Error - Invalid Craft):**
```json
{
  "success": false,
  "error": "Invalid played_craft. Must be one of: Forestcraft, Swordcraft, Runecraft, Dragoncraft, Abysscraft, Havencraft, Portalcraft"
}
```

**Response (Error - User Not Found):**
```json
{
  "success": false,
  "error": "User 123456789012345678 not found in development server. Are they a member?"
}
```

---

## Building a Python Application

### Simple Command-Line Tracker

Create a file `shadowverse_tracker.py`:

```python
import requests
import json
import os

# ============================================
# CONFIGURATION - Update these values!
# ============================================
API_URL = "https://gacha-bot.yourdomain.com"
API_KEY = "your_secret_key_here"

# Valid crafts
CRAFTS = [
    "Forestcraft",
    "Swordcraft", 
    "Runecraft",
    "Dragoncraft",
    "Abysscraft",
    "Havencraft",
    "Portalcraft"
]

CONFIG_FILE = "user_config.json"

# ============================================
# HELPER FUNCTIONS
# ============================================

def load_user_id():
    """Load saved user ID from config file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return data.get("user_id")
    return None

def save_user_id(user_id):
    """Save user ID so they don't need to enter again"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"user_id": user_id}, f)
    print(f"✓ User ID saved! You won't need to enter it again.\n")

def validate_api_connection():
    """Check if API is reachable and bot is connected"""
    try:
        response = requests.get(f"{API_URL}/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("bot_connected"):
                print("✓ Connected to API successfully!")
                print(f"  Bot: {data.get('bot_user')}\n")
                return True
            else:
                print("✗ API is running but bot is not connected!")
                return False
        else:
            print(f"✗ API returned status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Cannot connect to API: {e}")
        print(f"  Make sure the API URL is correct: {API_URL}\n")
        return False

def log_match(user_id, played_craft, opponent_craft, win, brick=False):
    """Send match data to the API"""
    try:
        response = requests.post(
            f"{API_URL}/api/shadowverse/log_match",
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "user_id": user_id,
                "played_craft": played_craft,
                "opponent_craft": opponent_craft,
                "win": win,
                "brick": brick
            },
            timeout=10
        )
        
        result = response.json()
        
        if response.status_code == 200 and result.get("success"):
            return True, result.get("message", "Match logged successfully")
        else:
            return False, result.get("error", "Unknown error occurred")
            
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {e}"
    except json.JSONDecodeError:
        return False, "Invalid response from server"

# ============================================
# MAIN APPLICATION
# ============================================

def main():
    print("=" * 60)
    print("         SHADOWVERSE MATCH TRACKER")
    print("=" * 60)
    print()
    
    # Check API connection first
    if not validate_api_connection():
        print("Please check your API configuration and try again.")
        input("\nPress Enter to exit...")
        return
    
    # Get or setup user ID
    user_id = load_user_id()
    
    if user_id:
        print(f"Logged in as Discord User: {user_id}")
        change = input("Change user? (y/n): ").lower()
        if change == 'y':
            user_id = None
    
    if not user_id:
        print("\n" + "=" * 60)
        print("FIRST TIME SETUP")
        print("=" * 60)
        print()
        print("You need your Discord User ID to log matches.")
        print()
        print("To get your Discord User ID:")
        print("  1. Open Discord")
        print("  2. Go to Settings → Advanced")
        print("  3. Enable 'Developer Mode'")
        print("  4. Right-click your username → Copy User ID")
        print()
        
        user_id = input("Enter your Discord User ID: ").strip()
        
        if not user_id or not user_id.isdigit():
            print("\n✗ Invalid User ID! Must be a number.")
            input("\nPress Enter to exit...")
            return
        
        save_user_id(user_id)
    
    print()
    
    # Main match logging loop
    while True:
        print("\n" + "=" * 60)
        print("LOG A NEW MATCH")
        print("=" * 60)
        print()
        
        # Select your craft
        print("What craft did YOU play?")
        for i, craft in enumerate(CRAFTS, 1):
            print(f"  {i}. {craft}")
        
        try:
            played_idx = int(input("\nEnter number (1-7): ")) - 1
            if played_idx < 0 or played_idx >= len(CRAFTS):
                print("✗ Invalid number! Please enter 1-7.")
                continue
            played_craft = CRAFTS[played_idx]
        except (ValueError, IndexError):
            print("✗ Invalid input! Please enter a number 1-7.")
            continue
        
        print()
        
        # Select opponent craft
        print("What craft did your OPPONENT play?")
        for i, craft in enumerate(CRAFTS, 1):
            print(f"  {i}. {craft}")
        
        try:
            opponent_idx = int(input("\nEnter number (1-7): ")) - 1
            if opponent_idx < 0 or opponent_idx >= len(CRAFTS):
                print("✗ Invalid number! Please enter 1-7.")
                continue
            opponent_craft = CRAFTS[opponent_idx]
        except (ValueError, IndexError):
            print("✗ Invalid input! Please enter a number 1-7.")
            continue
        
        print()
        
        # Result
        win_input = input("Did you WIN? (y/n): ").lower()
        if win_input not in ['y', 'n']:
            print("✗ Please enter 'y' or 'n'")
            continue
        win = (win_input == 'y')
        
        # Brick
        brick_input = input("Did you BRICK? (y/n, default=n): ").lower()
        brick = (brick_input == 'y')
        
        print()
        print("-" * 60)
        print("MATCH SUMMARY:")
        print(f"  You played: {played_craft}")
        print(f"  Opponent played: {opponent_craft}")
        print(f"  Result: {'WIN' if win else 'LOSS'}")
        print(f"  Bricked: {'YES' if brick else 'NO'}")
        print("-" * 60)
        
        confirm = input("\nLog this match? (y/n): ").lower()
        if confirm != 'y':
            print("Match cancelled.")
            continue
        
        # Send to API
        print("\nSending to bot...")
        success, message = log_match(user_id, played_craft, opponent_craft, win, brick)
        
        print()
        if success:
            print("✓ SUCCESS! " + message)
            print("  Check your Discord dashboard for updated stats!")
        else:
            print("✗ ERROR: " + message)
        
        print()
        
        # Continue?
        cont = input("Log another match? (y/n): ").lower()
        if cont != 'y':
            print("\n" + "=" * 60)
            print("Thanks for using Shadowverse Match Tracker!")
            print("=" * 60)
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        input("Press Enter to exit...")
```

### Running the Script

1. Save the file as `shadowverse_tracker.py`
2. Update `API_URL` and `API_KEY` at the top
3. Install dependencies:
   ```bash
   pip install requests
   ```
4. Run:
   ```bash
   python shadowverse_tracker.py
   ```

---

## Building a GUI Application

### Simple Tkinter GUI

Create a file `shadowverse_tracker_gui.py`:

```python
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
import os

# ============================================
# CONFIGURATION - Update these values!
# ============================================
API_URL = "https://gacha-bot.yourdomain.com"
API_KEY = "your_secret_key_here"

CRAFTS = [
    "Forestcraft",
    "Swordcraft",
    "Runecraft",
    "Dragoncraft",
    "Abysscraft",
    "Havencraft",
    "Portalcraft"
]

CONFIG_FILE = "user_config.json"

# ============================================
# API FUNCTIONS
# ============================================

def load_user_id():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return data.get("user_id")
    return None

def save_user_id(user_id):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"user_id": user_id}, f)

def validate_connection():
    try:
        response = requests.get(f"{API_URL}/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("bot_connected", False), data.get("bot_user", "Unknown")
        return False, "API not responding"
    except Exception as e:
        return False, str(e)

def log_match(user_id, played, opponent, win, brick):
    try:
        response = requests.post(
            f"{API_URL}/api/shadowverse/log_match",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={
                "user_id": user_id,
                "played_craft": played,
                "opponent_craft": opponent,
                "win": win,
                "brick": brick
            },
            timeout=10
        )
        result = response.json()
        return result.get("success", False), result.get("message", result.get("error", "Unknown error"))
    except Exception as e:
        return False, str(e)

# ============================================
# GUI APPLICATION
# ============================================

class ShadowverseTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Shadowverse Match Tracker")
        self.root.geometry("500x550")
        self.root.resizable(False, False)
        
        self.user_id = load_user_id()
        
        # Check connection on startup
        connected, bot_info = validate_connection()
        if not connected:
            messagebox.showerror(
                "Connection Error",
                f"Cannot connect to API!\n\n{bot_info}\n\nPlease check your configuration."
            )
        
        self.create_widgets()
    
    def create_widgets(self):
        # Title
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=80)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="SHADOWVERSE\nMATCH TRACKER",
            font=("Arial", 18, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title_label.pack(expand=True)
        
        # Main content
        content = tk.Frame(self.root, padx=20, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        # User ID section
        user_frame = tk.LabelFrame(content, text="User Settings", padx=10, pady=10)
        user_frame.pack(fill=tk.X, pady=(0, 15))
        
        if self.user_id:
            user_label = tk.Label(user_frame, text=f"Discord User ID: {self.user_id}")
            user_label.pack(side=tk.LEFT)
            
            change_btn = tk.Button(
                user_frame,
                text="Change",
                command=self.change_user
            )
            change_btn.pack(side=tk.RIGHT)
        else:
            setup_label = tk.Label(user_frame, text="No user ID configured")
            setup_label.pack(side=tk.LEFT)
            
            setup_btn = tk.Button(
                user_frame,
                text="Setup",
                command=self.setup_user
            )
            setup_btn.pack(side=tk.RIGHT)
        
        # Your craft
        tk.Label(content, text="Your Craft:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        self.played_var = tk.StringVar(value=CRAFTS[0])
        played_dropdown = ttk.Combobox(
            content,
            textvariable=self.played_var,
            values=CRAFTS,
            state="readonly",
            width=25
        )
        played_dropdown.pack(fill=tk.X, pady=(0, 15))
        
        # Opponent craft
        tk.Label(content, text="Opponent's Craft:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        self.opponent_var = tk.StringVar(value=CRAFTS[0])
        opponent_dropdown = ttk.Combobox(
            content,
            textvariable=self.opponent_var,
            values=CRAFTS,
            state="readonly",
            width=25
        )
        opponent_dropdown.pack(fill=tk.X, pady=(0, 15))
        
        # Result
        tk.Label(content, text="Match Result:", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        self.result_var = tk.StringVar(value="win")
        result_frame = tk.Frame(content)
        result_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Radiobutton(
            result_frame,
            text="Win",
            variable=self.result_var,
            value="win"
        ).pack(side=tk.LEFT, padx=(0, 20))
        
        tk.Radiobutton(
            result_frame,
            text="Loss",
            variable=self.result_var,
            value="loss"
        ).pack(side=tk.LEFT)
        
        # Brick
        self.brick_var = tk.BooleanVar(value=False)
        brick_check = tk.Checkbutton(
            content,
            text="I bricked this game",
            variable=self.brick_var
        )
        brick_check.pack(anchor=tk.W, pady=(0, 20))
        
        # Submit button
        submit_btn = tk.Button(
            content,
            text="LOG MATCH",
            command=self.submit_match,
            bg="#27ae60",
            fg="white",
            font=("Arial", 12, "bold"),
            height=2,
            cursor="hand2"
        )
        submit_btn.pack(fill=tk.X)
        
        # Status label
        self.status_label = tk.Label(
            content,
            text="",
            font=("Arial", 9),
            wraplength=450
        )
        self.status_label.pack(pady=(10, 0))
    
    def setup_user(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Setup User ID")
        dialog.geometry("400x250")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog,
            text="Discord User ID Setup",
            font=("Arial", 14, "bold")
        ).pack(pady=(20, 10))
        
        instructions = tk.Text(dialog, height=5, width=45, wrap=tk.WORD)
        instructions.pack(pady=10)
        instructions.insert("1.0", 
            "To get your Discord User ID:\n"
            "1. Open Discord Settings → Advanced\n"
            "2. Enable 'Developer Mode'\n"
            "3. Right-click your username\n"
            "4. Click 'Copy User ID'"
        )
        instructions.config(state=tk.DISABLED)
        
        tk.Label(dialog, text="Enter Discord User ID:").pack()
        
        entry = tk.Entry(dialog, width=30)
        entry.pack(pady=5)
        entry.focus()
        
        def save():
            user_id = entry.get().strip()
            if user_id and user_id.isdigit():
                save_user_id(user_id)
                self.user_id = user_id
                dialog.destroy()
                self.root.destroy()
                self.__init__(tk.Tk())
                messagebox.showinfo("Success", "User ID saved successfully!")
            else:
                messagebox.showerror("Error", "Invalid User ID! Must be a number.")
        
        tk.Button(dialog, text="Save", command=save, width=15).pack(pady=10)
    
    def change_user(self):
        self.user_id = None
        save_user_id("")
        self.root.destroy()
        root = tk.Tk()
        app = ShadowverseTracker(root)
        root.mainloop()
    
    def submit_match(self):
        if not self.user_id:
            messagebox.showerror("Error", "Please setup your User ID first!")
            return
        
        played = self.played_var.get()
        opponent = self.opponent_var.get()
        win = (self.result_var.get() == "win")
        brick = self.brick_var.get()
        
        # Confirmation
        result_text = "WON" if win else "LOST"
        brick_text = " (BRICKED)" if brick else ""
        
        confirm = messagebox.askyesno(
            "Confirm Match",
            f"Log this match?\n\n"
            f"You: {played}\n"
            f"Opponent: {opponent}\n"
            f"Result: {result_text}{brick_text}"
        )
        
        if not confirm:
            return
        
        # Submit
        self.status_label.config(text="Submitting...", fg="blue")
        self.root.update()
        
        success, message = log_match(self.user_id, played, opponent, win, brick)
        
        if success:
            self.status_label.config(text=f"✓ {message}", fg="green")
            messagebox.showinfo("Success", f"{message}\n\nCheck your Discord dashboard!")
            
            # Reset brick checkbox
            self.brick_var.set(False)
        else:
            self.status_label.config(text=f"✗ Error: {message}", fg="red")
            messagebox.showerror("Error", f"Failed to log match:\n\n{message}")

def main():
    root = tk.Tk()
    app = ShadowverseTracker(root)
    root.mainloop()

if __name__ == "__main__":
    main()
```

### Running the GUI

1. Save as `shadowverse_tracker_gui.py`
2. Update `API_URL` and `API_KEY`
3. Install dependencies:
   ```bash
   pip install requests
   ```
4. Run:
   ```bash
   python shadowverse_tracker_gui.py
   ```

---

## Creating an Executable

### Using PyInstaller

Create a single .exe file that users can run without installing Python:

```bash
# Install PyInstaller
pip install pyinstaller

# For command-line version
pyinstaller --onefile --name="ShadoverseTracker" shadowverse_tracker.py

# For GUI version (no console window)
pyinstaller --onefile --noconsole --name="ShadoverseTracker" shadowverse_tracker_gui.py
```

The .exe will be in the `dist/` folder. Distribute this file to users!

**Important:** Make sure to update `API_URL` and `API_KEY` in your script BEFORE building the executable!

---

## Error Handling

### Common API Errors

| Error Message | Cause | Solution |
|--------------|-------|----------|
| `Missing API key` | No X-API-Key header | Add header to request |
| `Invalid API key` | Wrong API key | Check api_keys.json on server |
| `Invalid played_craft` | Typo in craft name | Use exact strings from valid crafts list |
| `User not found in server` | User not in Discord server | User must join the development Discord server |
| `Bot not initialized` | Bot not ready | Wait and retry |
| `Connection refused` | API server not running | Check bot status on Raspberry Pi |
| `502 Bad Gateway` | Tunnel can't reach API | Check cloudflared service status |

### Handling Errors in Code

```python
try:
    response = requests.post(
        f"{API_URL}/api/shadowverse/log_match",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json=match_data,
        timeout=10
    )
    
    # Check HTTP status
    if response.status_code == 401:
        print("Error: Invalid API key")
    elif response.status_code == 404:
        print("Error: User not found in Discord server")
    elif response.status_code == 400:
        result = response.json()
        print(f"Error: {result.get('error')}")
    elif response.status_code == 200:
        result = response.json()
        if result.get("success"):
            print("Match logged successfully!")
        else:
            print(f"Error: {result.get('error')}")
    else:
        print(f"Unexpected status code: {response.status_code}")
        
except requests.exceptions.Timeout:
    print("Error: Request timed out. Check your internet connection.")
except requests.exceptions.ConnectionError:
    print("Error: Cannot connect to API. Is the URL correct?")
except requests.exceptions.RequestException as e:
    print(f"Error: {e}")
```

---

## Troubleshooting

### Application can't connect to API

1. **Check API URL**: Make sure it's your Cloudflare Tunnel URL
2. **Test manually**: 
   ```bash
   curl https://your-domain.com/api/health
   ```
3. **Check Cloudflare Tunnel**: On Raspberry Pi:
   ```bash
   sudo systemctl status cloudflared
   ```

### "Invalid API key" error

1. Check `api_keys.json` on the Raspberry Pi
2. Make sure the key in your app matches exactly
3. Keys are case-sensitive!

### "User not found" error

1. User must be a member of the Discord server where the bot is
2. Make sure User ID is correct (18-digit number)
3. User ID must be a string, not a number: `"123456789012345678"`

### Matches not appearing in Discord

1. Check bot logs on Raspberry Pi:
   ```bash
   sudo journalctl -u kanami-bot.service -n 50
   ```
2. Make sure the Shadowverse module is initialized
3. User might need to run `Kanami shadowverse` command first in Discord

---

## Getting Help

If you encounter issues:

1. Check the error message returned by the API
2. Test the API manually with curl/Invoke-WebRequest
3. Check bot logs on Raspberry Pi
4. Verify Cloudflare Tunnel is running
5. Make sure your API key is valid

For API server issues, check:
```bash
# On Raspberry Pi
sudo journalctl -u kanami-bot.service -f
```

---

## Summary

**To build an external app:**

1. Get your API URL and API key
2. Use the `/api/shadowverse/log_match` endpoint
3. Send POST requests with JSON data
4. Include `X-API-Key` header
5. Handle errors appropriately
6. Optionally build to .exe for distribution

**Minimum working example:**

```python
import requests

API_URL = "https://your-domain.com"
API_KEY = "your_key"
USER_ID = "your_discord_id"

response = requests.post(
    f"{API_URL}/api/shadowverse/log_match",
    headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    json={
        "user_id": USER_ID,
        "played_craft": "Dragoncraft",
        "opponent_craft": "Forestcraft",
        "win": True,
        "brick": False
    }
)

print(response.json())
```

That's it! You now have everything you need to build an external Shadowverse match tracking application.
