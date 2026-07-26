import os
import asyncio
import threading
from typing import List, Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import requests

from auth import autenticacao
from hotmark import download_class_assets, slugify

app = FastAPI(title="Hotmart Course Downloader Web")

# Templates
templates = Jinja2Templates(directory="templates")

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
    first_folder = f"universo-hot-{domain_subdomain}"
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


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    env_token = _read_env_token()
    return templates.TemplateResponse(request, "index.html", {"env_token": env_token})


@app.post("/api/auth/login")
async def api_login(req: LoginRequest):
    global auth_session, auth_params, domain_subdomain, nav_headers_global, course_structure
    
    # Save token in .env using standard KEY=VALUE format (compatible with python-dotenv and VS Code)
    try:
        with open(".env", "w", encoding="utf-8") as f:
            f.write(f"TOKEN={req.token}\n")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to save .env file: {str(e)}"})
    domain_subdomain = req.subdomain.strip()
    nav_headers_global = {
        'authority': 'api-club-course-consumption-gateway-ga.cb.hotmart.com',
        'accept': 'application/json, text/plain, */*',
        'origin': f'https://{domain_subdomain}.club.hotmart.com',
        'referer': f'https://{domain_subdomain}.club.hotmart.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        # Build auth session directly from the provided Bearer token (no CLI interaction needed)
        import requests as req_lib
        import base64, json as _json

        token = req.token.strip()
        if token.startswith("Bearer "):
            token = token.replace("Bearer ", "").strip()

        # Try to unwrap JWT inner access_token if present
        try:
            parts = token.split(".")
            if len(parts) == 3:
                padded = parts[1] + "=" * (-len(parts[1]) % 4)
                payload = _json.loads(base64.b64decode(padded).decode("utf-8"))
                if "access_token" in payload:
                    token = payload["access_token"]
        except Exception:
            pass

        auth_session = req_lib.Session()
        auth_session.headers.update({
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "authorization": f"Bearer {token}"
        })
        auth_params = {"token": token}
        nav_headers_global['authorization'] = f"Bearer {token}"
        
        # Load course structure/navigation
        from hotmark import fetch_course_navigation
        curso = fetch_course_navigation(auth_session, domain_subdomain, nav_headers_global)
        
        # Map structure
        course_structure = {}
        modules = curso.get('modules') or curso.get('data') or []
        for mod in modules:
            mod_name = mod.get('name')
            mod_order = mod.get('moduleOrder') or mod.get('order') or 1
            if mod_name not in course_structure:
                course_structure[mod_order] = {mod_name: []}
                
            pages = mod.get('pages') or mod.get('lessons') or []
            for page in pages:
                page_name = page.get('name')
                page_order = page.get('pageOrder') or page.get('order') or 1
                page_hash = page.get('hash') or page.get('id')
                
                # Check for videos and attachments
                videos = []
                attachments = []
                
                course_structure[mod_order][mod_name].append([
                    page_order,
                    page_name,
                    page_hash,
                    {"videos": videos},
                    {"anexos": attachments},
                    {"html_content": ""}
                ])
                
        # Format course data for Frontend listing
        formatted_modules = []
        for mod_order in sorted(course_structure.keys()):
            for mod_name, lessons in course_structure[mod_order].items():
                formatted_lessons = []
                for lesson in lessons:
                    formatted_lessons.append({
                        "order": lesson[0],
                        "name": lesson[1],
                        "id": lesson[2]
                    })
                formatted_modules.append({
                    "order": mod_order,
                    "name": mod_name,
                    "lessons": formatted_lessons
                })

        return {"status": "success", "modules": formatted_modules, "subdomain": domain_subdomain}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


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
