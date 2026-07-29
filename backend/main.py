import os
import asyncio
import threading
from dotenv import load_dotenv

load_dotenv()
from typing import List, Dict, Any
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests

from fastapi.middleware.cors import CORSMiddleware
from auth import autenticacao
from hotmark import download_class_assets, slugify

app = FastAPI(title="Hotmart Course Downloader Web")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global session and configuration
auth_session = None
auth_params = None
course_structure = None
domain_subdomain = ""
nav_headers_global = {}

# Active downloads state
active_downloads: Dict[str, Dict[str, Any]] = {}
websocket_clients: List[WebSocket] = []

class LoginRequest(BaseModel):
    token: str
    subdomain: str = ""
    product_id: str = ""
    download_dir: str = ""

def update_env_keys(updates: dict):
    """Safely updates or adds specified KEY=VALUE pairs in .env without overwriting other keys."""
    env_file = ".env"
    lines = []
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            pass

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k, v = stripped.split("=", 1)
            k_upper = k.strip().upper()
            if k_upper in updates:
                new_lines.append(f'{k_upper}="{updates[k_upper]}"\n')
                updated_keys.add(k_upper)
                continue
        new_lines.append(line)

    for k_upper, v_val in updates.items():
        if k_upper not in updated_keys and v_val:
            new_lines.append(f'{k_upper}="{v_val}"\n')

    try:
        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception:
        pass

class DownloadRequest(BaseModel):
    lesson_ids: List[str]

async def broadcast_progress(lesson_id: str, percentage: int, status: str):
    message = {
        "lesson_id": lesson_id,
        "percentage": percentage,
        "status": status
    }
    for client in websocket_clients:
        try:
            await client.send_json(message)
        except Exception:
            pass

def run_download_sync(aula: list, modName: str, folder_path_class: str, first_folder: str, authMart, nav_headers: dict, dominio: str, lesson_id: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def progress_callback(step: int, total: int, percentage: int, status_msg: str = "Downloading..."):
        active_downloads[lesson_id] = {
            "percentage": percentage,
            "status": status_msg
        }
        loop.run_until_complete(broadcast_progress(lesson_id, percentage, status_msg))
    
    try:
        active_downloads[lesson_id] = {"percentage": 0, "status": "Starting..."}
        loop.run_until_complete(broadcast_progress(lesson_id, 0, "Starting..."))
        
        # Download assets with progress callback injected
        download_class_assets(
            aula=aula,
            modulo=modName,
            folder_path_class=folder_path_class,
            first_folder=first_folder,
            authMart=authMart,
            nav_headers=nav_headers,
            dominio=dominio,
            progress_callback=progress_callback
        )
        
        active_downloads[lesson_id] = {"percentage": 100, "status": "Completed"}
        loop.run_until_complete(broadcast_progress(lesson_id, 100, "Completed"))
    except Exception as e:
        active_downloads[lesson_id] = {"percentage": 0, "status": f"Error: {str(e)}"}
        loop.run_until_complete(broadcast_progress(lesson_id, 0, f"Error: {str(e)}"))
    finally:
        loop.close()

def start_downloads_background(lesson_ids: List[str]):
    global auth_session, course_structure, domain_subdomain, nav_headers_global
    if not auth_session or not course_structure:
        return

    # Find matching lessons in the structure
    lessons_to_download = []
    # Normalize folder name to avoid duplicate prefixes
    sub_clean = domain_subdomain
    if sub_clean.startswith("universo-hot-"):
        first_folder = sub_clean
    else:
        first_folder = f"universo-hot-{sub_clean}"
        
    download_dir = os.getenv('DOWNLOAD_DIR', '').strip()
    if download_dir:
        first_folder = os.path.join(download_dir, first_folder)
        
    if not os.path.exists(first_folder):
        os.makedirs(first_folder)

    for moduloOrder in course_structure:
        for modName in course_structure[moduloOrder]:
            folder_path = f'{first_folder}/{slugify(str(moduloOrder))}_{slugify(modName)}'
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                
            for aula in course_structure[moduloOrder][modName]:
                if aula[2] in lesson_ids:
                    folder_path_class = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}"
                    if not os.path.exists(folder_path_class):
                        os.makedirs(folder_path_class)
                    
                    lessons_to_download.append((aula, modName, folder_path_class, first_folder, aula[2]))

    # Run downloads sequentially in a background thread to prevent blocking FastAPI
    def worker():
        for aula, modName, folder_path_class, first_folder, lesson_id in lessons_to_download:
            run_download_sync(
                aula=aula,
                modName=modName,
                folder_path_class=folder_path_class,
                first_folder=first_folder,
                authMart=auth_session,
                nav_headers=nav_headers_global,
                dominio=domain_subdomain,
                lesson_id=lesson_id
            )

    threading.Thread(target=worker, daemon=True).start()


def _read_env_token() -> str:
    """Read the saved Bearer token from .env file. Supports both KEY=VALUE and KEY: VALUE formats."""
    env_token = ""
    env_file = ".env" if os.path.exists(".env") else ("temp/.env" if os.path.exists("temp/.env") else None)
    if env_file:
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Support standard KEY=VALUE format
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip().upper() == "TOKEN":
                            env_token = v.strip().strip('"\'')
                    # Legacy support for KEY: VALUE format
                    elif ":" in line:
                        k, v = line.split(":", 1)
                        if k.strip().lower() == "token":
                            env_token = v.strip().strip('"\'')
        except Exception:
            pass
    # Also check OS environment variable as fallback
    if not env_token:
        env_token = os.environ.get("TOKEN", "")
    return env_token


@app.get("/api/subdomains")
async def get_subdomains():
    """
    Returns a combined list of subdomains:
    1. Saved subdomains from config_cursos.py
    2. Auto-detected subdomains from Hotmart API using saved token
    Always returns JSON — never raises a 500 HTML response.
    """
    try:
        result = []
        seen = set()

        # 1. Load subdomains saved in config_cursos.py
        try:
            from config_cursos import CURSOS_SUBDOMINIOS
            for item in CURSOS_SUBDOMINIOS:
                sd = item.get("subdomain", "").strip()
                if sd and sd not in seen:
                    result.append({"subdomain": sd, "source": "config", "name": sd})
                    seen.add(sd)
        except Exception:
            pass

        # 2. Auto-detect from Hotmart API using saved token
        token = _read_env_token()
        token_present = bool(token)
        if token:
            if token.startswith("Bearer "):
                token = token.replace("Bearer ", "").strip()
            try:
                import base64 as _b64
                import json as _json
                parts = token.split(".")
                if len(parts) == 3:
                    padded = parts[1] + "=" * (-len(parts[1]) % 4)
                    payload = _json.loads(_b64.b64decode(padded).decode("utf-8"))
                    if "access_token" in payload:
                        token = payload["access_token"]
            except Exception:
                pass

            headers = {
                "authorization": f"Bearer {token}",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "accept": "application/json",
            }
            try:
                resp = requests.get(
                    "https://api-club.hotmart.com/hot-club-api/rest/v3/membership",
                    headers=headers,
                    timeout=10
                )
                if resp.status_code == 200:
                    memberships = resp.json()
                    items = memberships if isinstance(memberships, list) else memberships.get("items", [])
                    for item in items:
                        resource = item.get("resource", item)
                        sd = resource.get("subdomain", "").strip()
                        name = resource.get("name") or resource.get("productName") or sd
                        if sd and sd not in seen:
                            result.append({"subdomain": sd, "source": "api", "name": name})
                            seen.add(sd)
            except Exception:
                pass

            # Fallback endpoint
            if not [r for r in result if r["source"] == "api"]:
                try:
                    resp2 = requests.get(
                        "https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/memberships",
                        headers=headers,
                        timeout=10
                    )
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        items2 = data2 if isinstance(data2, list) else data2.get("items", [])
                        for item in items2:
                            sd = item.get("subdomain", "").strip()
                            name = item.get("name") or sd
                            if sd and sd not in seen:
                                result.append({"subdomain": sd, "source": "api", "name": name})
                                seen.add(sd)
                except Exception:
                    pass

        return {"subdomains": result, "token_present": token_present}

    except Exception as e:
        return JSONResponse(status_code=200, content={"subdomains": [], "token_present": False, "error": str(e)})


@app.get("/")
async def get_index():
    env_token = _read_env_token()
    env_download_dir = os.getenv("DOWNLOAD_DIR", "")
    return {
        "status": "online",
        "message": "Hotmart Course Downloader API is running",
        "env_token_present": bool(env_token),
        "env_download_dir": env_download_dir
    }


@app.post("/api/auth/login")
async def api_login(req: LoginRequest):
    global auth_session, auth_params, domain_subdomain, nav_headers_global, course_structure
    
    domain_subdomain = req.subdomain.strip()

    try:
        # Build auth session directly from the provided Bearer token (no CLI interaction needed)
        import requests as req_lib
        import base64, json as _json

        token = req.token.strip()
        pasted_token = ""
        pasted_subdomain = ""
        pasted_product_id = ""

        if "TOKEN=" in token or "SUBDOMAIN=" in token:
            for line in token.splitlines():
                line_str = line.strip()
                if "=" in line_str and not line_str.startswith("#"):
                    k, v = line_str.split("=", 1)
                    k_upper = k.strip().upper()
                    v_val = v.strip().strip('"\'')
                    if k_upper == "TOKEN":
                        pasted_token = v_val
                    elif k_upper == "SUBDOMAIN":
                        pasted_subdomain = v_val
                    elif k_upper == "PRODUCT_ID" or k_upper == "PRODUCTID":
                        pasted_product_id = v_val

            if pasted_token:
                token = pasted_token
            if pasted_subdomain and not req.subdomain.strip():
                domain_subdomain = pasted_subdomain
            if pasted_product_id and not req.product_id.strip():
                req.product_id = pasted_product_id

        if token.startswith("Bearer "):
            token = token.replace("Bearer ", "").strip()

        auth_session = req_lib.Session()
        auth_session.headers.update({
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "authorization": f"Bearer {token}",
            "origin": f"https://{domain_subdomain}.club.hotmart.com",
            "referer": f"https://{domain_subdomain}.club.hotmart.com/",
            "club": domain_subdomain
        })
        auth_params = {"token": token}
        
        # Auto detect product_id for chosen subdomain if missing
        product_id = req.product_id.strip()
        detected_courses = []
        if domain_subdomain:
            for ep in ["https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/memberships", "https://api-club.hotmart.com/hot-club-api/rest/v3/membership"]:
                try:
                    r_mem = auth_session.get(ep, timeout=10)
                    if r_mem.status_code == 200:
                        d_mem = r_mem.json()
                        items = d_mem if isinstance(d_mem, list) else d_mem.get("items", [])
                        for it in items:
                            res_it = it.get("resource", it) if isinstance(it, dict) else {}
                            sub = res_it.get("subdomain") or it.get("subdomain")
                            pid = str(res_it.get("productId") or res_it.get("id") or it.get("productId") or it.get("id") or "")
                            name = res_it.get("name") or res_it.get("productName") or it.get("name") or sub or ""
                            if sub and pid:
                                detected_courses.append({"name": name, "subdomain": sub, "product_id": pid})
                            if sub and sub.strip().lower() == domain_subdomain.strip().lower():
                                if pid:
                                    product_id = pid
                        if product_id:
                            break
                except Exception:
                    pass

        # If still no product_id is resolved and we have detected courses, use the first matching one or show info
        if not product_id and detected_courses:
            # Fallback to the first course matching the subdomain case-insensitively
            for dc in detected_courses:
                if dc["subdomain"].strip().lower() == domain_subdomain.strip().lower():
                    product_id = dc["product_id"]
                    break

        nav_headers_global = {
            'authority': 'api-club-course-consumption-gateway-ga.cb.hotmart.com',
            'accept': 'application/json, text/plain, */*',
            'origin': f'https://{domain_subdomain}.club.hotmart.com',
            'referer': f'https://{domain_subdomain}.club.hotmart.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'authorization': f"Bearer {token}"
        }
        if product_id:
            nav_headers_global['x-product-id'] = product_id
        else:
            # Format a helpful message listing all detected courses for the user
            if detected_courses:
                course_list_str = "\n".join([f"• {c['name']} (Subdomain: {c['subdomain']}, Product ID: {c['product_id']})" for c in detected_courses])
                raise RuntimeError(
                    f"Product ID could not be resolved for subdomain '{domain_subdomain}'. "
                    f"We detected the following courses in your account:\n{course_list_str}"
                )
            else:
                raise RuntimeError(
                    f"Required header 'x-product-id' is missing. Please select one of the auto-detected subdomains "
                    f"or specify the PRODUCT_ID in your .env file."
                )

        # Safely update .env without wiping other keys
        env_updates = {"TOKEN": req.token.strip()}
        if domain_subdomain:
            env_updates["SUBDOMAIN"] = domain_subdomain
        if product_id:
            env_updates["PRODUCT_ID"] = product_id
        if req.download_dir.strip():
            env_updates["DOWNLOAD_DIR"] = req.download_dir.strip()
            os.environ["DOWNLOAD_DIR"] = req.download_dir.strip()

        update_env_keys(env_updates)
        
        # Load course structure/navigation
        from hotmark import fetch_course_navigation
        curso = fetch_course_navigation(auth_session, domain_subdomain, nav_headers_global)
        
        # Map structure
        course_structure = {}
        modules = curso.get('modules') or curso.get('data') or []
        for idx_mod, mod in enumerate(modules, start=1):
            mod_name = mod.get('name')
            mod_order = mod.get('moduleOrder') or mod.get('order') or idx_mod
            if mod_order not in course_structure:
                course_structure[mod_order] = {}
            if mod_name not in course_structure[mod_order]:
                course_structure[mod_order][mod_name] = []
                
            pages = mod.get('pages') or mod.get('lessons') or []
            for idx_page, page in enumerate(pages, start=1):
                page_name = page.get('name')
                page_order = page.get('pageOrder') or page.get('order') or idx_page
                page_hash = page.get('hash') or page.get('id')
                
                # Check for videos, attachments and content types in page metadata
                has_video_meta = bool(page.get('hasVideo') or page.get('medias') or page.get('videos'))
                has_attachment_meta = bool(page.get('attachments') or page.get('files') or page.get('hasAttachment'))

                course_structure[mod_order][mod_name].append([
                    page_order,
                    page_name,
                    page_hash,
                    {"videos": []},
                    {"anexos": []},
                    {"links": []},
                    {"has_video_meta": has_video_meta, "has_attachment_meta": has_attachment_meta}
                ])
                
        # Format course data for Frontend listing, including local download detection
        import glob
        sub_clean = domain_subdomain
        first_folder = sub_clean if sub_clean.startswith("universo-hot-") else f"universo-hot-{sub_clean}"
        
        download_dir = os.getenv('DOWNLOAD_DIR', '').strip()
        if download_dir:
            first_folder = os.path.join(download_dir, first_folder)
        
        # Cache list of directories in first_folder to make match robust against index shifts
        existing_mods = {}
        if os.path.exists(first_folder):
            for d in os.listdir(first_folder):
                if os.path.isdir(os.path.join(first_folder, d)):
                    parts = d.split("_", 1)
                    if len(parts) > 1:
                        existing_mods[parts[1]] = d
                    else:
                        existing_mods[d] = d

        formatted_modules = []
        for mod_order in sorted(course_structure.keys()):
            for mod_name, lessons in course_structure[mod_order].items():
                mod_slug_base = slugify(mod_name)
                if mod_slug_base in existing_mods:
                    actual_mod_dir = existing_mods[mod_slug_base]
                else:
                    actual_mod_dir = f"{slugify(str(mod_order))}_{mod_slug_base}"
                
                actual_mod_path = os.path.join(first_folder, actual_mod_dir)
                
                # Cache class folders inside this module
                existing_classes = {}
                if os.path.exists(actual_mod_path):
                    for c_dir in os.listdir(actual_mod_path):
                        if os.path.isdir(os.path.join(actual_mod_path, c_dir)):
                            c_parts = c_dir.split(".", 1)
                            if len(c_parts) > 1:
                                existing_classes[c_parts[1]] = c_dir
                            else:
                                existing_classes[c_dir] = c_dir

                formatted_lessons = []
                for lesson in lessons:
                    lesson_order = lesson[0]
                    lesson_name = lesson[1]
                    
                    lesson_slug_base = slugify(lesson_name)
                    if lesson_slug_base in existing_classes:
                        actual_class_dir = existing_classes[lesson_slug_base]
                    else:
                        actual_class_dir = f"{slugify(str(lesson_order))}.{lesson_slug_base}"
                        
                    class_folder = os.path.join(actual_mod_path, actual_class_dir)
                    
                    downloaded_status = False
                    has_video = lesson[6].get("has_video_meta", False)
                    has_pdf = False
                    has_attached = lesson[6].get("has_attachment_meta", False)
                    
                    if os.path.exists(class_folder):
                        mp4s = glob.glob(os.path.join(class_folder, "*.mp4"))
                        if mp4s and any(os.path.getsize(f) > 0 for f in mp4s):
                            downloaded_status = True
                            has_video = True
                        else:
                            candidate_paths = [
                                os.path.join(class_folder, f"{slugify(str(lesson_order))}.{lesson_slug_base}.mp4"),
                                os.path.join(class_folder, f"{slugify(mod_name)}.{slugify(str(lesson_order))}.mp4"),
                                os.path.join(class_folder, f"aula-{slugify(str(lesson_order))}.mp4")
                            ]
                            if any(os.path.exists(path) and os.path.getsize(path) > 0 for path in candidate_paths):
                                downloaded_status = True
                                has_video = True

                        materials_folder = os.path.join(class_folder, "Materials")
                        if os.path.exists(materials_folder):
                            mat_files = os.listdir(materials_folder)
                            if mat_files:
                                has_attached = True
                                if any(f.endswith(".pdf") or "gdrive" in f.lower() for f in mat_files):
                                    has_pdf = True
                    
                    formatted_lessons.append({
                        "order": lesson_order,
                        "name": lesson_name,
                        "id": lesson[2],
                        "downloaded": downloaded_status,
                        "has_video": has_video,
                        "has_pdf": has_pdf,
                        "has_attached": has_attached
                    })
                formatted_modules.append({
                    "order": mod_order,
                    "name": mod_name,
                    "lessons": formatted_lessons
                })

        return {"status": "success", "modules": formatted_modules, "subdomain": domain_subdomain}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/api/logs")
async def get_logs():
    """
    Returns recent log output from log.txt or debug.log.
    """
    logs_content = []
    
    # 1. Root log.txt
    if os.path.exists("log.txt"):
        try:
            with open("log.txt", "r", encoding="utf-8", errors="ignore") as f:
                logs_content.extend(f.readlines()[-200:])
        except Exception:
            pass
            
    # 2. Check course-specific log files under DOWNLOAD_DIR
    download_dir = os.getenv('DOWNLOAD_DIR', '').strip()
    sub_clean = domain_subdomain
    if sub_clean:
        course_folder = sub_clean if sub_clean.startswith("universo-hot-") else f"universo-hot-{sub_clean}"
        if download_dir:
            course_folder = os.path.join(download_dir, course_folder)
            
        for log_name in ["log.txt", "debug.log"]:
            log_path = os.path.join(course_folder, log_name)
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        logs_content.append(f"\n--- {log_name} ({log_path}) ---\n")
                        logs_content.extend(f.readlines()[-200:])
                except Exception:
                    pass

    if not logs_content:
        return {"logs": "No logs recorded yet."}
        
    return {"logs": "".join(logs_content)}


@app.post("/api/download")
async def api_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    if not auth_session or not course_structure:
        return JSONResponse(status_code=400, content={"error": "Not authenticated"})
    
    # Initialize download records
    for lesson_id in req.lesson_ids:
        active_downloads[lesson_id] = {"percentage": 0, "status": "Queued"}

    background_tasks.add_task(start_downloads_background, req.lesson_ids)
    return {"status": "started", "active_downloads": active_downloads}


@app.get("/api/downloads/status")
async def get_all_downloads_status():
    return active_downloads


@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.append(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)
    except Exception:
        if websocket in websocket_clients:
            websocket_clients.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
