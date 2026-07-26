import os
import glob
import requests
import json
import base64
from logger import loga

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
                    if ":" in line:
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

    # If there is a saved token, use it immediately
    if env_token:
        print("[+] A saved Token was detected in the .env file. Using token automatically...")
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

    print("=== HOTMART AUTHENTICATION METHODS ===")
    print("1. Send OTP Code/Token to my email address (Recommended)")
    print("2. Paste Bearer Token directly from the browser (F12)")
    print("3. User Credentials / Password (Sparkle Legacy API)")
    metodo = input("Select auth method (1, 2 or 3, default 1): ").strip() or "1"
    
    if metodo == "1":
        email = kwargs.get("email") or env_email
        if not email:
            email = input("Enter your registered Hotmart email:\n").strip()
            
        loga(".", "INFO", f"Requesting OTP code to {email}")
        print(f"\n[+] Requesting verification code to: {email} ...")
        
        try:
            resp = authMart.post(
                "https://sso.hotmart.com/api/v1/login/email",
                json={"email": email},
                headers={
                    "content-type": "application/json",
                    "origin": "https://sso.hotmart.com",
                    "referer": "https://sso.hotmart.com/login?passwordless=true"
                },
                timeout=15
            )
            if resp.status_code in [200, 201, 204]:
                print(f"Verification code successfully sent to {email}!")
            else:
                print(f"[WARNING] HTTP Status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[WARNING] Could not automatically request verification code: {e}")

        print("\nCheck your inbox or spam in Hotmart.")
        token_input = input("Enter the received OTP code (or Bearer Token): ").strip()
        
        if token_input.startswith("Bearer "):
            token_input = token_input.replace("Bearer ", "").strip()
            
        authMart.headers['authorization'] = f'Bearer {token_input}'
        params = {'token': token_input}
        return authMart, params

    elif metodo == "2":
        print("\nHow to get your Token from the browser?")
        print("1. Log in to your Hotmart course in Chrome/Firefox.")
        print("2. Press F12 -> 'Network' tab.")
        print("3. Reload the page or click on any class.")
        print("4. Search for any request to 'api-club.hotmart.com'.")
        print("5. Copy the value of the 'authorization' header (Bearer eyJ...) or the 'token'.\n")
        token = input("Paste your Token here: ").strip()
        if token.startswith("Bearer "):
            token = token.replace("Bearer ", "").strip()
        
        authMart.headers['authorization'] = f'Bearer {token}'
        params = {'token': token}
        return authMart, params

    # Legacy Authorization (Option 3)
    email = kwargs.get("email") or env_email
    if not email:
        email = str(input("What is your login email?\n"))
    senha = kwargs.get("senha", None) or env_password
    if senha is None:
        senha = str(input("What is your login password?\n"))
        
    data = {'username': email, 'password': senha, 'grant_type': 'password'}
    loga(".", "INFO", f"Attempting authorization to Sparkle with payload: {str(data)}")

    authSparkle = authMart.post('https://api.sparkleapp.com.br/oauth/token', data=data)
    if authSparkle.status_code == 200:
        loga(".", "INFO", "Authentication successful!")
        authSparkle_json = authSparkle.json()
    else:
        print(f"\n[ERROR] Error authenticating against Hotmart (HTTP {authSparkle.status_code}):")
        print(f"API Response: {authSparkle.text[:300]}")
        loga(".", "ERROR", f"Authentication failed. HTTP status: {authSparkle.status_code}")
        loga(".", "ERROR", f"{authSparkle.text}")
        try:
            authSparkle_json = authSparkle.json()
        except Exception:
            authSparkle_json = {}

    try:
        params = {'token': authSparkle_json['access_token']}
    except KeyError:
        print("\nInvalid email or password, or Sparkle API failure. Exiting...")
        loga(".", "ERROR", "Token not found. Access credentials may be invalid or API has changed.")
        loga(".", "ERROR", f"{authSparkle.text}")
        exit(13)
        
    authMart.headers.clear()
    authMart.headers[
        'user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    authMart.headers['authorization'] = 'Bearer ' + str(authSparkle_json['access_token'])
    return authMart, params
