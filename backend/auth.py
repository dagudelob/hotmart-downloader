import os
import glob
import requests
import json
import base64
import http.server
import threading
import sys
import time
import select
from logger import loga, print_color

received_token = [None]

class TokenReceiver(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress HTTP server output logs in CLI

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = """
        <html>
        <head><title>Hotmart Token Receiver</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background-color: #f9f9f9;">
            <h1 style="color: #4CAF50;">Server is Ready!</h1>
            <p>This local server is waiting to receive your token automatically.</p>
            <p>Please paste the JavaScript snippet in your Hotmart course browser tab console (F12) to submit the token.</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body)
            token = data.get("token")
            if token:
                received_token[0] = token
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            else:
                self.wfile.write(json.dumps({"status": "error", "message": "No token provided"}).encode("utf-8"))
        except Exception as e:
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

def update_env_token(token):
    lines = []
    token_written = False
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("TOKEN="):
                    lines.append(f'TOKEN="{token}"\n')
                    token_written = True
                else:
                    lines.append(line)
    if not token_written:
        lines.append(f'TOKEN="{token}"\n')
        
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

def update_env_download_dir(dir_path):
    lines = []
    dir_written = False
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("DOWNLOAD_DIR="):
                    lines.append(f'DOWNLOAD_DIR="{dir_path}"\n')
                    dir_written = True
                else:
                    lines.append(line)
    if not dir_written:
        lines.append(f'DOWNLOAD_DIR="{dir_path}"\n')
        
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

def autenticacao(**kwargs):
    """
    Handles user authentication against the Hotmart API (via SSO OTP or Sparkle Legacy API).
    Checks credentials and environment variables, fallback to interactive input if token isn't in .env.
    """
    if not os.path.exists('temp'):
        os.makedirs('temp')
    for f in glob.glob("temp/*"):
        if os.path.isfile(f):
            try:
                os.remove(f)
            except Exception:
                pass
        
    authMart = requests.session()
    authMart.headers[
        'user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    # Try reading token, email, and password from .env or temp/.env
    env_token = ""
    env_email = ""
    env_password = ""
    env_file = ".env" if os.path.exists(".env") else ("temp/.env" if os.path.exists("temp/.env") else None)
    if env_file:
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Standard KEY=VALUE format
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip().lower()
                        v = v.strip().strip('"\'')
                        if k == "token":
                            env_token = v
                        elif k == "email":
                            env_email = v
                        elif k == "password":
                            env_password = v
                    # Legacy KEY: VALUE format
                    elif ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip().strip('"\'')
                        if k == "token":
                            env_token = v
                        elif k == "email":
                            env_email = v
                        elif k == "password":
                            env_password = v
        except Exception:
            pass
    # Also check OS environment variables as fallback
    if not env_token:
        env_token = os.environ.get("TOKEN", "")

    # If there is a saved token, use it immediately
    if env_token:
        print_color("[INFO] A saved Token was detected in the .env file. Using token automatically...")
        if env_token.startswith("Bearer "):
            env_token = env_token.replace("Bearer ", "").strip()
            
        # Parse JWT payload to extract inner access_token if present
        try:
            parts = env_token.split(".")
            if len(parts) == 3:
                payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
                payload_json = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
                if "access_token" in payload_json:
                    access_tok = payload_json["access_token"]
                    authMart.headers['authorization'] = f'Bearer {access_tok}'
                    params = {'token': access_tok}
                    return authMart, params
        except Exception:
            pass

        authMart.headers['authorization'] = f'Bearer {env_token}'
        params = {'token': env_token}
        return authMart, params

    print("\n=== HOTMART AUTHENTICATION ===")
    print("To download courses, a Hotmart Bearer Token is required.")
    print("How to get your Token from your browser:")
    print("1. Log in to your Hotmart course in Chrome/Firefox.")
    print("2. Open Developer Tools by pressing F12 -> 'Console' tab.")
    print("3. Paste the contents of 'Get_Token.js' and press Enter (it will copy the token to your clipboard).")
    print("   OR open F12 -> 'Network' tab, look for requests to 'api-club.hotmart.com', and copy the authorization header.")
    print("--------------------------------------------------------------------------------")
    
    while True:
        token = input("Paste your Bearer Token here (or type 'exit' to quit): ").strip()
        if token.lower() == 'exit':
            print("Exiting...")
            exit(0)
            
        if not token:
            print_color("[WARNING] No token entered. Please enter a valid Bearer Token.")
            continue
            
        if token.startswith("Bearer "):
            token = token.replace("Bearer ", "").strip()
            
        # Save token in .env safely
        try:
            update_env_token(token)
            print_color("[SUCCESS] Token saved successfully in the .env file.")
        except Exception as e:
            print_color(f"[WARNING] Failed to save token in .env: {e}")
            
        authMart.headers['authorization'] = f'Bearer {token}'
        params = {'token': token}
        return authMart, params
