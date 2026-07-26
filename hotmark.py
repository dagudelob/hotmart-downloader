# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                      Descargador de Cursos de Hotmart                                               #
#                                                                                                                     #
#  Basado en el gist original de @juvenal: https://gist.github.com/juvenal/2d9a822325769d30c45c635fbf388c1b           #
#  Con mejoras para descargar archivos PDF incrustados de Google Drive                                                #
#                                                                                                                     #
#  NOTA: La API de Hotmart cambió (2026) y ahora necesitas agregar manualmente los subdominios                        #
#        de los cursos en el archivo config_cursos.py                                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Requisitos:
# - FFMPEG instalado en el sistema (agregado a las variables de entorno / PATH)
# - Dependencias Python: pip install -r requirements.txt
#   (m3u8, beautifulsoup4, youtube_dl / yt-dlp, requests)
#
# Cómo usar:
# 1. Configura los subdominios en config_cursos.py
# 2. Ejecuta: python hotmark.py  (o: uv run python hotmark.py)
# 3. Ingresa correo y contraseña cuando se solicite
#
# Lo que hace el script:
# - Descarga videos (Hotmart, Vimeo, YouTube)
# - Descarga adjuntos normales (PDFs, archivos ZIP, etc.)
# - Descarga PDFs incrustados de Google Drive (iframes de vista previa dentro del texto de las clases)
# - Guarda enlaces de lectura complementaria
# - Guarda las descripciones de las clases (HTML)
# - Reanuda descargas interrumpidas automáticamente
# - Organiza todo en carpetas por módulo/clase

import time
import datetime
import requests
import m3u8  # pip install m3u8
import re
import os
import json
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from bs4 import BeautifulSoup  # pip install beautifulsoup4
import youtube_dl  # pip install youtube_dl o yt-dlp
import subprocess
import glob
import unicodedata

def slugify(value, allow_unicode=False):
    """
    Tomado de https://github.com/django/django/blob/master/django/utils/text.py
    Convierte cadenas a formato 'slug' limpio para nombres de archivos y carpetas válidos (sin caracteres especiales).
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')


def extrair_google_drive_urls(html_content):
    """
    ¿POR QUÉ BUSCA COSAS EN GOOGLE DRIVE?
    Muchos profesores e instructores en Hotmart no suben sus documentos como 'Adjuntos oficiales',
    sino que insertan visores PDF o documentos incrustados (iframes) apuntando a su Google Drive personal.
    Esta función escanea el HTML de la clase para extraer los IDs de esos archivos de Google Drive y generar 
    enlaces de descarga directa.
    
    Retorna una lista de tuplas: (file_id, url_preview, url_download)
    """
    if not html_content:
        return []
    
    urls = []
    # Patrón Regex para encontrar enlaces de iframes de Google Drive (drive.google.com/file/d/ID_DEL_ARCHIVO)
    pattern = r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)'
    matches = re.findall(pattern, html_content)
    
    for file_id in matches:
        preview_url = f"https://drive.google.com/file/d/{file_id}/preview"
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        urls.append((file_id, preview_url, download_url))
    
    return urls


def baixar_google_drive(file_id, download_url, output_path, first_folder):
    """
    Descarga un archivo público o incrustado desde Google Drive hacia el disco local.
    Maneja pantallas intermedias de confirmación de descarga para archivos grandes de Google Drive.
    
    Retorna True si la descarga fue exitosa, False en caso contrario.
    """
    try:
        loga(first_folder, "INFO", f"Iniciando descarga de Google Drive: {file_id}")
        
        # Crea una sesión para mantener cookies durante la redirección de Google
        session = requests.Session()
        
        # Primer intento: descarga directa
        response = session.get(download_url, stream=True)
        
        # Si el archivo es grande, Google Drive muestra una página intermedia de aviso/confirmación de virus
        if 'confirm' in response.text or 'virus scan warning' in response.text.lower():
            # Busca el enlace de confirmación generado en el HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if 'export=download' in href and 'confirm' in href:
                    download_url = 'https://drive.google.com' + href
                    response = session.get(download_url, stream=True)
                    break
        
        # Guarda el archivo en trozos (chunks) en el disco
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verifica que el archivo no esté vacío
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                loga(first_folder, "INFO", f"Descarga completada: {output_path} ({os.path.getsize(output_path)} bytes)")
                return True
            else:
                loga(first_folder, "ERROR", f"Archivo vacío o no creado: {output_path}")
                return False
        else:
            loga(first_folder, "ERROR", f"Fallo en la descarga de Google Drive: {response.status_code}")
            return False
            
    except Exception as e:
        loga(first_folder, "ERROR", f"Excepción al descargar de Google Drive {file_id}: {str(e)}")
        return False


# Ruta global para el archivo de debug detallado
_debug_log_path = None

def set_debug_log(curso):
    """Inicializa la ruta del log de debug al empezar a procesar un curso."""
    global _debug_log_path
    if curso:
        if not os.path.exists(curso):
            os.makedirs(curso)
        _debug_log_path = curso + "/debug.log"

def debug(msg):
    """Escribe un mensaje de nivel DEBUG en debug.log (con timestamp)."""
    ts = datetime.datetime.today().replace(microsecond=0)
    line = f"[{ts}] DEBUG: {msg}\n"
    if _debug_log_path:
        try:
            with open(_debug_log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

def http_log(method, url, status_code, extra=None):
    """
    Registra cada petición HTTP en debug.log con método, URL, código de estado
    y cualquier información extra (primeros 300 chars de respuesta o error).
    """
    msg = f"[HTTP {method}] {status_code} → {url}"
    if extra:
        msg += f"\n         ↳ {str(extra)[:300]}"
    debug(msg)
    # También imprimir en consola si hay error
    if isinstance(status_code, int) and status_code not in (200, 201, 204):
        print(f"[HTTP {method}] {status_code} → {url[:90]}")
        if extra:
            print(f"         ↳ {str(extra)[:200]}")

def loga(curso, status, msg):
    """
    Registra eventos (logs) en log.txt Y debug.log dentro de la carpeta del curso.
    """
    ts = datetime.datetime.today().replace(microsecond=0)
    line = f"[{ts}] {status}: {msg}\n"
    try:
        if curso and not os.path.exists(curso):
            os.makedirs(curso)
        with open(curso + "/log.txt", "a", encoding="utf-8") as logz:
            logz.write(line)
    except Exception:
        pass
    debug(f"[{status}] {msg}")


def autenticacao(**kwargs):
    """
    Realiza la autenticación del usuario contra la API de Hotmart (vía Sparkle OAuth).
    Pide credenciales de correo y contraseña si no se pasan por argumento.
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
    
    # Intenta leer token, email y password desde .env o temp/.env si existen
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

    # Si hay un token guardado en .env, utilizarlo directamente sin preguntas
    if env_token:
        print("[+] A saved Token was detected in the .env file. Using token automatically...")
        if env_token.startswith("Bearer "):
            env_token = env_token.replace("Bearer ", "").strip()
            
        # Si el token es un JWT que contiene access_token dentro del payload
        try:
            import json, base64
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
            
        loga(".", "INFO", f"Solicitando envío de código OTP a {email}")
        print(f"\n[+] Solicitando envío de código de verificación a: {email} ...")
        
        # Petición a la API SSO de Hotmart para solicitar código OTP por correo
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
                print(f"¡Código enviado con éxito a {email}!")
            else:
                print(f"[AVISO] Estado HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[AVISO] No se pudo solicitar automáticamente el código: {e}")

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

    # Flujo Legacy (Opción 3)
    email = kwargs.get("email") or env_email
    if not email:
        email = str(input("What is your login email?\n"))
    senha = kwargs.get("senha", None)
    if senha is None:
        senha = str(input("What is your login password?\n"))
        
    data = {'username': email, 'password': senha, 'grant_type': 'password'}
    loga(".", "INFO", f"Intentando autenticar en Hotmart con el payload {str(data)}")

    authSparkle = authMart.post('https://api.sparkleapp.com.br/oauth/token', data=data)
    if authSparkle.status_code == 200:
        loga(".", "INFO", "¡Autenticación exitosa!")
        authSparkle_json = authSparkle.json()
    else:
        print(f"\n[ERROR] Error al autenticar contra Hotmart (HTTP {authSparkle.status_code}):")
        print(f"Respuesta de la API: {authSparkle.text[:300]}")
        loga(".", "ERROR", f"Autenticación fallida. Código de error:{authSparkle.status_code}")
        loga(".", "ERROR", f"{authSparkle.text}")
        try:
            authSparkle_json = authSparkle.json()
        except Exception:
            authSparkle_json = {}

    try:
        params = {'token': authSparkle_json['access_token']}
    except KeyError:
        print("\nInvalid email or password, or Sparkle API failure. Exiting...")
        loga(".", "ERROR", "¡Token no encontrado! Es posible que la contraseña o usuario sean incorrectos o la API haya cambiado.")
        loga(".", "ERROR", f"{authSparkle.text}")
        exit(13)
        
    authMart.headers.clear()
    authMart.headers[
        'user-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    authMart.headers['authorization'] = 'Bearer ' + str(authSparkle_json['access_token'])
    return authMart, params


def listacursos(authMart, params):
    """
    Obtiene la lista de cursos asociados a la cuenta de Hotmart del usuario.
    Posteriormente navega por la estructura de módulos, clases, videos y materiales para descargarlos.
    """
    # Intenta obtener productos del endpoint check_token
    check_token_response = authMart.get('https://api-sec-vlc.hotmart.com/security/oauth/check_token', params=params).json()
    
    # Guarda la respuesta completa para depuración
    import json
    with open("api_response_debug.json", "w", encoding="utf-8") as f:
        json.dump(check_token_response, f, indent=2, ensure_ascii=False)
    
    loga(".", "DEBUG", "Respuesta de check_token guardada en api_response_debug.json")
    
    produtos = check_token_response.get('resources', [])
    
    # Si la API no devolvió productos (cambio de API Hotmart 2026), intenta cargar desde config_cursos.py
    if not produtos:
        loga(".", "WARN", "No se encontraron productos en check_token")
        print("\nWARNING: Hotmart API did not return courses automatically.")
        
        # Intenta importar desde el archivo de configuración manual
        try:
            from config_cursos import CURSOS_SUBDOMINIOS
            if CURSOS_SUBDOMINIOS:
                print(f"\nSe encontraron {len(CURSOS_SUBDOMINIOS)} curso(s) en el archivo config_cursos.py")
                for item in CURSOS_SUBDOMINIOS:
                    if isinstance(item, dict):
                        sub = item.get("subdomain", "").strip()
                        pid = str(item.get("productId", "")).strip()
                    else:
                        sub = str(item).strip()
                        pid = "1643794"
                        
                    produtos.append({
                        'resource': {
                            'subdomain': sub,
                            'productId': pid,
                            'status': 'ACTIVE'
                        },
                        'roles': ['STUDENT']
                    })
                loga(".", "INFO", f"Se cargaron {len(CURSOS_SUBDOMINIOS)} cursos desde el archivo de configuración")
            else:
                print("\nWARNING: config_cursos.py file is empty.")
        except ImportError:
            print("\nWARNING: config_cursos.py file not found.")
        except Exception as e:
            loga(".", "ERROR", f"Error al cargar config_cursos.py: {e}")
            print(f"\nAVISO: Error al cargar la configuración: {e}")
        
        # Si aún no hay cursos, permite al usuario ingresarlos de forma interactiva
        if not produtos:
            print("\nTo find your course subdomain:")
            print("1. Go to https://sun.hotmart.com/minhas-compras")
            print("2. Click on 'Access' in the desired course")
            print("3. Inside the URL you will see: https://hotmart.com/en/club/SUBDOMAIN/...")
            print("4. The 'SUBDOMAIN' is the part to copy")
            print("\nTip: Edit 'config_cursos.py' to save subdomains permanently\n")
            
            subdominios_manuais = []
            while True:
                subdomain = input("Enter the course subdomain (or press Enter to finish): ").strip()
                if not subdomain:
                    if not subdominios_manuais:
                        print("WARNING: No course was added. Exiting...")
                        exit(0)
                    break
                subdominios_manuais.append(subdomain)
                print(f"Subdominio '{subdomain}' agregado\n")
            
            for subdomain in subdominios_manuais:
                produtos.append({
                    'resource': {
                        'subdomain': subdomain,
                        'status': 'ACTIVE'
                    },
                    'roles': ['STUDENT']
                })
            
            loga(".", "INFO", f"Se agregaron {len(subdominios_manuais)} cursos manualmente")

    loga(".", "INFO", "Listando productos de la cuenta.")
    cursosValidos = []
    for idx, i in enumerate(produtos):
        try:
            loga(".", "DEBUG", f"Producto {idx + 1}: status={i.get('resource', {}).get('status')}, roles={i.get('roles')}")
            
            if i.get('resource', {}).get('status') == "ACTIVE" and "STUDENT" in i.get('roles', []):
                dominio = i['resource']['subdomain']
                loga(".", "DEBUG", f"Producto válido encontrado. Subdominio: {dominio}")
                authMart.headers['origin'] = f'https://{dominio}.club.hotmart.com'
                authMart.headers['referer'] = f'https://{dominio}.club.hotmart.com'
                authMart.headers['club'] = dominio
                
                # Probar comunicación directa con la API de Hotmart Club para obtener el nombre del curso
                try:
                    resp_membership = authMart.get(
                        f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/user/{dominio}/status',
                        headers={'origin': 'https://hotmart.com', 'referer': 'https://hotmart.com/'},
                        timeout=10
                    )
                    if resp_membership.status_code == 200:
                        i["nome"] = dominio
                    else:
                        resp_legacy = authMart.get(
                            'https://api-club.hotmart.com/hot-club-api/rest/v3/membership?attach_token=false',
                            timeout=10
                        )
                        if resp_legacy.status_code == 200:
                            i["nome"] = re.sub(r'[<>:"/\\|?*]', '', resp_legacy.json().get('name', dominio)).strip()
                        else:
                            i["nome"] = dominio
                except Exception:
                    i["nome"] = dominio
                    
                loga(".", "DEBUG", f"Nombre del curso obtenido: {i['nome']}")
                cursosValidos.append(i)
            else:
                loga(".", "DEBUG", f"Producto {idx + 1} no cumple criterios (ACTIVE + STUDENT)")
        except Exception as e:
            loga(".", "ERROR", f"Error al procesar producto: {e}")
            continue
    
    if not cursosValidos:
        print("\n[ERROR] Could not connect or validate membership for the provided subdomains.")
        print("Please check your Token or course membership status.")
        exit(1)

    def select_item_cli(options, title="Select an option:", show_exit=True):
        """
        Interactively select an option using keyboard arrow keys or shortcuts.
        Displays dynamic pagination and shortcut indicators on top of the screen.
        """
        import msvcrt
        import sys
        
        display_options = list(options)
        if show_exit:
            display_options.append("Exit / Cancel")
            
        options_count = len(display_options)
        
        # Ask the user if they want to digit index manually or scroll
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"=== {title} ===")
        print("Choose selection method:")
        print("1. Scroll/Navigate with keyboard arrows")
        print("2. Type/Digit the index number directly")
        choice = ""
        while choice not in ["1", "2"]:
            # Capture keyboard key directly
            k = msvcrt.getch()
            if k == b'1':
                choice = "1"
            elif k == b'2':
                choice = "2"
            elif k == b'\x1b': # ESC
                print("\nExiting program...")
                exit(0)
                
        if choice == "2":
            # Digit mode
            while True:
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"=== {title} ===")
                for idx, opt in enumerate(display_options, start=1):
                    print(f"{idx:3d}. {opt}")
                print(f"\nEnter the number (1 to {options_count}) or type 'exit' to quit:")
                typed = input("> ").strip()
                if typed.lower() == 'exit':
                    print("\nExiting program...")
                    exit(0)
                try:
                    num = int(typed) - 1
                    if 0 <= num < options_count:
                        if show_exit and num == options_count - 1:
                            print("\nExiting program...")
                            exit(0)
                        return num
                except ValueError:
                    pass
                print("Invalid index. Press any key to retry...")
                msvcrt.getch()
                
        # Scroll Mode
        selected = 0
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            # Shortcut headers printed on top of the screen
            print("=====================================================================")
            print(" [ESC] Exit  |  [F] Find/Type index directly  |  [C] Display all content ")
            print("=====================================================================")
            print(f"\n=== {title} ===")
            print("(Use UP/DOWN arrows to navigate, SPACE or ENTER to select.)\n")
            
            start_idx = max(0, selected - 5)
            end_idx = min(options_count, selected + 6)
            
            if selected - 5 < 0:
                end_idx = min(options_count, 11)
            if selected + 6 > options_count:
                start_idx = max(0, options_count - 11)
            
            if start_idx > 0:
                print("   ... (more options above) ...")
                
            for i in range(start_idx, end_idx):
                opt = display_options[i]
                if i == selected:
                    print(f" > [x] {i + 1:3d}. {opt}")
                else:
                    print(f"   [ ] {i + 1:3d}. {opt}")
                    
            if end_idx < options_count:
                print("   ... (more options below) ...")
            
            key = msvcrt.getch()
            
            # Key Bindings & Shortcuts
            if key == b'\x1b': # ESC
                print("\nExiting program...")
                exit(0)
            elif key == b'\x03': # Ctrl+C
                print("\nOperation cancelled.")
                exit(0)
            elif key == b'f' or key == b'F': # F shortcut - switch to typing mode
                while True:
                    print(f"\nEnter the number (1 to {options_count}) to select: ")
                    typed = input("> ").strip()
                    try:
                        num = int(typed) - 1
                        if 0 <= num < options_count:
                            if show_exit and num == options_count - 1:
                                print("\nExiting program...")
                                exit(0)
                            return num
                    except ValueError:
                        pass
                    print("Invalid index. Try again.")
            elif key == b'c' or key == b'C': # C shortcut - display all content (no truncation)
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"=== {title} (Full List) ===")
                for idx, opt in enumerate(display_options, start=1):
                    print(f"{idx:3d}. {opt}")
                print("\nPress any key to return to navigation...")
                msvcrt.getch()
            elif key == b'\r' or key == b' ': # Enter or Space
                if show_exit and selected == options_count - 1:
                    print("\nExiting program...")
                    exit(0)
                return selected
            elif key == b'\xe0': # Special key (arrows)
                arrow = msvcrt.getch()
                if arrow == b'H': # UP arrow
                    selected = (selected - 1) % options_count
                elif arrow == b'P': # DOWN arrow
                    selected = (selected + 1) % options_count

    # Selección de curso con bucle de validación y soporte de exit
    cursor_opts = [f"{c['nome']} (subdomain: {c['resource']['subdomain']})" for c in cursosValidos]
    opcao = select_item_cli(cursor_opts, title=f"Cursos disponibles ({len(cursosValidos)} encontrado(s))")
    
    nmcurso = slugify(cursosValidos[opcao]['nome'])

    loga(".", "INFO", f"Iniciando descarga del curso {nmcurso}")
    loga(".", "INFO", f"{cursosValidos[opcao]}")
    
    # Se guarda directamente en la carpeta actual del proyecto
    first_folder = f'{nmcurso}'
    if not os.path.exists(first_folder):
        os.makedirs(first_folder)
    
    # Inicializar el log de debug detallado para todo el proceso del curso
    set_debug_log(first_folder)
    debug(f"=== Iniciando sesión de descarga para curso: {nmcurso} ===")
        
    dominio = cursosValidos[opcao]['resource']['subdomain']
    authMart.headers['origin'] = f'https://{dominio}.club.hotmart.com/'
    authMart.headers['referer'] = f'https://{dominio}.club.hotmart.com/'

    authMart.headers['club'] = dominio
    
    # Obtiene el mapa completo de módulos y lecciones del curso (con fallback)
    resp_nav = authMart.get('https://api-club.hotmart.com/hot-club-api/rest/v3/navigation')
    if resp_nav.status_code == 200 and 'modules' in resp_nav.json():
        curso = resp_nav.json()
    else:
        # Petición al nuevo gateway de consumo con el token del usuario y encabezados requeridos
        nav_headers = {
            'origin': 'https://hotmart.com',
            'referer': 'https://hotmart.com/',
            'x-app-name': 'app-club-consumer_v1.357.2_production'
        }
        # Intentar obtener product_id si está en la información del recurso
        prod_id = cursosValidos[opcao].get('resource', {}).get('productId') or cursosValidos[opcao].get('productId') or "1643794"
        nav_headers['x-product-id'] = str(prod_id)

        resp_nav = authMart.get(
            f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/navigation?subdomain={dominio}',
            headers=nav_headers
        )
        
        # Si aún requiere x-product-id y no lo teníamos, intenta la ruta /v2/modules o /v1/modules
        if resp_nav.status_code == 400 and 'x-product-id' in resp_nav.text:
            # Probar obtener productos/membership para extraer productId
            resp_mem = authMart.get(f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/user/{dominio}/status', headers=nav_headers)
            if resp_mem.status_code == 200:
                p_id = resp_mem.json().get('productId') or resp_mem.json().get('id')
                if p_id:
                    nav_headers['x-product-id'] = str(p_id)
                    resp_nav = authMart.get(
                        f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/navigation?subdomain={dominio}',
                        headers=nav_headers
                    )

        if resp_nav.status_code == 200:
            curso = resp_nav.json()
            if 'modules' not in curso and 'data' in curso:
                curso['modules'] = curso['data']
        else:
            print(f"\n[ERROR] No se pudo obtener la lista de módulos (HTTP {resp_nav.status_code}):")
            print(f"Respuesta de la API: {resp_nav.text[:300]}")
            exit(1)

    if 'modules' not in curso:
        print(f"\n[ERROR] La estructura devuelta por la API no contiene 'modules'. Claves recibidas: {list(curso.keys())}")
        print(f"Respuesta completa: {str(curso)[:300]}")
        exit(1)

    estrutura = {}
    tempAula = []
    aulas = []
    tempAnexo = []
    tempLink = []
    x = 0

    loga(first_folder, "INFO", "Estructura obtenida con éxito, construyendo diccionario del curso")

    for idx_mod, modulo in enumerate(curso['modules'], 1):
        mod_order = modulo.get('moduleOrder') or modulo.get('order') or idx_mod
        mod_name = modulo.get('name') or f"Modulo_{mod_order}"
        mod_name_clean = re.sub(r'[<>:"/\\|?*]', '', mod_name).strip()
        estrutura[mod_order] = {mod_name_clean: []}
        
        paginas = modulo.get('pages') or modulo.get('lessons') or modulo.get('contents') or []
        for idx_page, i in enumerate(paginas, 1):
            x += 1
            page_order = i.get('pageOrder') or i.get('order') or idx_page
            page_name = i.get('name') or i.get('title') or f"Clase_{page_order}"
            page_hash = i.get('hash') or i.get('id') or i.get('code')
            
            # Se guardan los datos básicos de la lista instantáneamente sin hacer peticiones HTTP adicionales
            aulas = [page_order, re.sub(r'[<>:"/\\|?*]', '', page_name).strip(), page_hash, {'videos': []},
                     {'anexos': []}, {'links': []}]
                     
            # Si el menú de navegación trae las medias directamente en memoria
            medias = i.get('mediasSrc') or i.get('medias') or []
            for video in medias:
                v_name = video.get('mediaName') or video.get('name') or 'video'
                v_code = video.get('mediaCode') or video.get('code') or video.get('id')
                v_url = video.get('mediaSrcUrl') or video.get('url') or video.get('src')
                tempAula = [re.sub(r'[<>:"/\\|?*]', '', v_name).strip(), v_code, v_url]
                aulas[3]['videos'].append(tempAula)

            estrutura[mod_order][mod_name_clean].append(aulas)

    # Guarda una copia de la estructura en debug.txt por si ocurre algún fallo
    with open(first_folder + '/debug.txt', 'a', encoding='utf-8') as debug_file:
        debug_file.write(str(curso['modules']) + '\n\n\n' + str(estrutura))

    loga(first_folder, "INFO", "Dictionary created successfully, exported as debug.txt")
    loga(first_folder, "INFO", f"Total classes in the course {nmcurso}: {str(x)}")

    # Download options: Whole course, single class or custom range
    download_modes = [
        "Download ONLY 1 specific class/video (Step-by-step)",
        "Download the ENTIRE course",
        "Download a RANGE of classes (From X to Y)"
    ]
    selected_mode_idx = select_item_cli(download_modes, title="DOWNLOAD MODE")
    modo_descarga = str(selected_mode_idx + 1)
    
    clases_a_descargar = [] # List of selected class hashes to download
    
    # Build index list of all classes
    todas_las_clases = []
    for modulo in estrutura:
        for nome_mod in estrutura[modulo]:
            for aula_item in estrutura[modulo][nome_mod]:
                todas_las_clases.append((modulo, nome_mod, aula_item))
                
    if modo_descarga == "1":
        class_options = [f"[{nome_mod}] {aula_item[1]}" for (modulo, nome_mod, aula_item) in todas_las_clases]
        idx_clase = select_item_cli(class_options, title="Available classes list")
        _, _, aula_sel = todas_las_clases[idx_clase]
        clases_a_descargar.append(aula_sel[2])
        print(f"\n[+] Starting download for class: '{aula_sel[1]}'\n")
        
    elif modo_descarga == "3":
        while True:
            # Range validation loop
            try:
                print(f"\nTotal classes in the course: {len(todas_las_clases)}")
                desde_input = input(f"Start downloading from class number? (1 to {len(todas_las_clases)}, or type 'exit' to quit): ").strip()
                if desde_input.lower() == 'exit':
                    print("\nExiting program...")
                    exit(0)
                desde = int(desde_input) - 1
                
                hasta_input = input(f"Download up to class number? ({desde + 1} to {len(todas_las_clases)}, or type 'exit' to quit): ").strip()
                if hasta_input.lower() == 'exit':
                    print("\nExiting program...")
                    exit(0)
                hasta = int(hasta_input) - 1
                
                if 0 <= desde < len(todas_las_clases) and desde <= hasta < len(todas_las_clases):
                    break
                else:
                    print(f"\n[!] Option not available. Please enter a valid class range.")
            except ValueError:
                print(f"\n[!] Option not available. Please enter valid integers.")
        
        print(f"\n[+] Seleccionado rango de clases del {desde + 1} al {hasta + 1}:")
        for i in range(desde, hasta + 1):
            _, _, aula_sel = todas_las_clases[i]
            clases_a_descargar.append(aula_sel[2])
            print(f"  - {i + 1}. {aula_sel[1]}")
        print()

    # Iterate modules and classes to process downloads
    for modulo in estrutura:
        for aulas in estrutura[modulo]:
            # Filtrar si el usuario eligió modo selectivo (1 o 3)
            if (modo_descarga == "1" or modo_descarga == "3"):
                clases_filtradas = [a for a in estrutura[modulo][aulas] if a[2] in clases_a_descargar]
                if not clases_filtradas:
                    continue
            
            folder_path = f'{first_folder}/{slugify(str(modulo))}_{slugify(aulas)}'
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

                loga(first_folder, "INFO", f"Creada la carpeta del módulo {str(modulo)}.{aulas}")

            for aula in estrutura[modulo][aulas]:
                # Si se seleccionó modo selectivo, omitir las demás
                if (modo_descarga == "1" or modo_descarga == "3") and aula[2] not in clases_a_descargar:
                    continue

                folder_path_class = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}"
                print(f"Verificando la clase\n\t {folder_path_class}")
                if not os.path.exists(folder_path_class):
                    os.makedirs(folder_path_class)

                    loga(first_folder, "INFO", f"Creada la carpeta de la clase {slugify(str(aula[0]))}.{slugify(aula[1])}")

                # 1. Obtener detalles de la clase (contenido HTML, anexos y links) únicamente para la clase seleccionada
                try:
                    resp_page = authMart.get(f'https://api-club.hotmart.com/hot-club-api/rest/v3/page/{aula[2]}')
                    lesson_json = {}
                    if resp_page.status_code == 200:
                        lesson_json = resp_page.json()
                        desct = lesson_json.get('content', '')
                    else:
                        resp_page = authMart.get(
                            f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v2/web/lessons/{aula[2]}',
                            headers=nav_headers
                        )
                        lesson_json = resp_page.json()
                        desct = lesson_json.get('content') or lesson_json.get('description') or ''
                        
                    # Extraer anexos si no venían cargados previamente
                    if not aula[4]['anexos']:
                        attachments = lesson_data.get('attachments') if 'lesson_data' in locals() else lesson_json.get('attachments', [])
                        for anexo in attachments:
                            tempAnexo = [anexo.get('fileMembershipId') or anexo.get('id'), re.sub(r'[<>:"/\\|?*]', '', anexo.get('fileName') or anexo.get('name') or 'anexo').strip()]
                            aula[4]['anexos'].append(tempAnexo)

                    # Extraer links si no venían cargados previamente
                    if not aula[5]['links']:
                        links = lesson_json.get('complementaryReadings') or lesson_json.get('links') or []
                        for link in links:
                            tempLink = [re.sub(r'[<>:"/\\|?*]', '', link.get('articleName') or link.get('name') or 'link').strip(), link.get('articleUrl') or link.get('url')]
                            aula[5]['links'].append(tempLink)

                    if desct:
                        with open(f"{folder_path_class}/descripcion.html", 'w', encoding='utf-8') as dd:
                            dd.write(str(desct))
                            loga(first_folder, "INFO", f"Descripción guardada con éxito, clase {str(aula[0])}.{aula[1]}")
                except Exception as e_desc:
                    loga(first_folder, "ERROR", f"Fallo al guardar la descripción de la clase {str(aula[0])}. {aula[1]}: {e_desc}")

                # 2. Descarga de videos
                # Si no se habían extraído videos previamente, intentar consultar la lección en la API v2
                if not aula[3]['videos']:
                    try:
                        resp_lesson = authMart.get(
                            f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v2/web/lessons/{aula[2]}',
                            headers=nav_headers
                        )
                        if resp_lesson.status_code == 200:
                            lesson_data = resp_lesson.json()
                            medias = lesson_data.get('medias') or lesson_data.get('mediasSrc') or []
                            for video in medias:
                                v_name = video.get('name') or video.get('mediaName') or 'video'
                                v_code = video.get('code') or video.get('mediaCode') or video.get('id')
                                v_url = video.get('url') or video.get('mediaSrcUrl') or video.get('src')
                                if v_code or v_url:
                                    aula[3]['videos'].append([re.sub(r'[<>:"/\\|?*]', '', v_name).strip(), v_code, v_url])
                    except Exception:
                        pass

                if not aula[3]['videos']:
                    loga(first_folder, "WARN",
                         "Class does not contain native Hotmart videos, checking external hosts (Vimeo/YouTube)...")

                    try:
                        pjson = BeautifulSoup(desct, features="html.parser")
                        viframe = pjson.find_all("iframe")
                        for x, i in enumerate(viframe, start=1):
                            if 'player.vimeo' in i.get("src"):
                                youtube_dl.utils.std_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"

                                loga(first_folder, "INFO", f"¡Vídeo de Vimeo encontrado! {i.get('src')}")

                                if '?' in i.get("src"):
                                    linkV = i.get("src").split('?')[0]
                                else:
                                    linkV = i.get("src")
                                if linkV[-1] == "/":
                                    linkV = linkV.split("/")[-1]

                            elif 'vimeo.com' in i.get("src"):
                                youtube_dl.utils.std_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"

                                loga(first_folder, "INFO", f"¡Vídeo de Vimeo encontrado! {i.get('src')}")

                                vimeoID = i.get("src").split('vimeo.com/')[1]
                                if "?" in vimeoID:
                                    vimeoID = vimeoID.split("?")[0]
                                linkV = "https://player.vimeo.com/video/" + vimeoID

                            elif "wistia.com" in i.get("src"):
                                loga(first_folder, "ERROR", f"WISTIA! Vídeo encontrado: {i.get('src')}")
                                pass

                            elif "youtube.com" in i.get("src") or "youtu.be" in i.get("src"):
                                loga(first_folder, "INFO", f"¡Vídeo de YouTube encontrado! {i.get('src')}")
                                linkV = i.get("src")
                                
                            # Cambiar nombre del video al formato módulo.clase.mp4
                            video_filename = f"{slugify(str(modulo))}.{slugify(str(aula[0]))}.mp4"
                            folder_path_class_video = f'{folder_path_class}/{video_filename}'
                            if not os.path.isfile(folder_path_class_video):
                                print(f"Descargando clase externa\n\t {folder_path_class_video}")
                                ydl_opts = {"format": "best", 'outtmpl': folder_path_class_video}
                                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                                    ydl.download([linkV])
                                    loga(first_folder, "INFO", "External video downloaded successfully.")
                            else:
                                print("Class already exists, skipping...")
                                loga(first_folder, "INFO", "Clase ya presente. Omitida.")

                    except:
                        loga(first_folder, "WARN",
                             "No videos found on the platform, checking if it is a text-only class.")
                        pass

                else:  # Reproductor nativo de Hotmart (HLS m3u8)
                    for x, i in enumerate(aula[3]['videos'], start=1):
                        video_filename = f"{slugify(str(modulo))}.{slugify(str(aula[0]))}.mp4"
                        folder_path_class_video = f'{folder_path_class}/{video_filename}'
                        if not os.path.isfile(folder_path_class_video):
                            print(f"Intentando descargar clase de Hotmart\n\t {folder_path_class_video}")
                            loga(first_folder, "INFO", f"Intentando descargar la clase {str(aula[0])} ({aula[1]})")

                            mediaUrl = i[2]
                            videoHash = i[1]

                            debug(f"=== Iniciando descarga video hash={videoHash} ===")
                            debug(f"mediaUrl: {mediaUrl}")
                            debug(f"authMart headers: {dict(authMart.headers)}")

                            # ─────────────────────────────────────────────────────────────────────
                            # ESTRATEGIA 1: yt-dlp con cookies del navegador Chrome
                            # Las firmas Akamai (hdnts) solo son válidas dentro de una sesión de
                            # navegador autenticada. yt-dlp puede usar esas cookies directamente.
                            # ─────────────────────────────────────────────────────────────────────
                            print(f"[YTDLP] Intentando con cookies de Chrome: {mediaUrl[:70]}...")
                            debug(f"[YTDLP] Ejecutando yt-dlp --cookies-from-browser chrome sobre {mediaUrl}")
                            yt_cmd = [
                                "yt-dlp",
                                "--cookies-from-browser", "chrome",
                                "--referer", f"https://{dominio}.club.hotmart.com/",
                                "--add-header", "Origin:https://cf-embed.play.hotmart.com",
                                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                "--no-warnings",
                                "-o", os.path.abspath(folder_path_class_video),
                                mediaUrl
                            ]
                            try:
                                debug(f"[YTDLP CMD] {' '.join(yt_cmd)}")
                                res_yt = subprocess.run(yt_cmd, capture_output=True, text=True)
                                debug(f"[YTDLP STDOUT] {res_yt.stdout[-1000:]}")
                                debug(f"[YTDLP STDERR] {res_yt.stderr[-1000:]}")
                                if res_yt.stderr:
                                    print(f"[YTDLP] {res_yt.stderr[-300:]}")
                                if os.path.exists(folder_path_class_video) and os.path.getsize(folder_path_class_video) > 0:
                                    size_mb = os.path.getsize(folder_path_class_video) / (1024 * 1024)
                                    print(f"[OK] Video descargado con yt-dlp+cookies ({size_mb:.2f} MB)")
                                    loga(first_folder, "INFO", f"Video descargado con yt-dlp+cookies ({size_mb:.2f} MB)")
                                    continue
                                else:
                                    print(f"[YTDLP WARN] yt-dlp no descargó el archivo, intentando extracción manual de HLS...")
                                    debug("[YTDLP] Descarga directa falló, continuando con extracción manual")
                            except Exception as e_yt:
                                print(f"[YTDLP ERROR] {e_yt}")
                                debug(f"[YTDLP EXCEPTION] {e_yt}")

                            # ─────────────────────────────────────────────────────────────────────
                            # ESTRATEGIA 2: Extraer jwtToken de mediaUrl y consultar API de assets
                            # ─────────────────────────────────────────────────────────────────────
                            hls_url = None
                            jwt_in_url = None
                            if mediaUrl and 'jwtToken=' in mediaUrl:
                                try:
                                    parsed_m_url = urlparse(mediaUrl)
                                    qs_m = parse_qs(parsed_m_url.query)
                                    if 'jwtToken' in qs_m:
                                        jwt_in_url = qs_m['jwtToken'][0]
                                        debug(f"[JWT] jwtToken extraído de mediaUrl (primeros 60 chars): {jwt_in_url[:60]}")
                                except Exception as e_jwt:
                                    debug(f"[JWT ERROR] {e_jwt}")

                            for api_path in ["v2", "v1"]:
                                player_api_url = f"https://api-player.hotmart.com/{api_path}/media/{videoHash}/assets"
                                player_api_headers = {
                                    'origin': 'https://cf-embed.play.hotmart.com',
                                    'referer': mediaUrl or 'https://cf-embed.play.hotmart.com/',
                                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                                }
                                if jwt_in_url:
                                    player_api_headers['authorization'] = f'Bearer {jwt_in_url}'
                                elif 'authorization' in authMart.headers:
                                    player_api_headers['authorization'] = authMart.headers['authorization']

                                print(f"[HTTP API PLAYER] GET {player_api_url}")
                                debug(f"[HTTP API PLAYER] GET {player_api_url}")
                                debug(f"[HTTP API PLAYER] headers enviados: {player_api_headers}")
                                try:
                                    resp_p = authMart.get(player_api_url, headers=player_api_headers)
                                    http_log("GET", player_api_url, resp_p.status_code, resp_p.text[:300])
                                    if resp_p.status_code == 200:
                                        p_data = resp_p.json()
                                        debug(f"[HTTP API PLAYER] Respuesta JSON: {json.dumps(p_data)[:500]}")
                                        assets = p_data.get('assets', [])
                                        for a_item in assets:
                                            if a_item.get('url') and 'm3u8' in a_item.get('url'):
                                                hls_url = a_item.get('url')
                                                break
                                        if not hls_url:
                                            hls_url = p_data.get('mediaSrcUrl') or p_data.get('url') or p_data.get('hlsUrl')
                                        if hls_url:
                                            debug(f"[HTTP API PLAYER] hls_url obtenido: {hls_url[:100]}")
                                            break
                                except Exception as e_papi:
                                    debug(f"[HTTP API PLAYER EXCEPTION] {e_papi}")
                                    print(f"[HTTP API PLAYER WARN] {e_papi}")

                            # ─────────────────────────────────────────────────────────────────────
                            # ESTRATEGIA 3: Parsear la página embed cf-embed para extraer m3u8
                            # ─────────────────────────────────────────────────────────────────────
                            if not hls_url and mediaUrl:
                                print(f"[HTTP] Solicitando página embed: {mediaUrl[:75]}...")
                                debug(f"[HTTP] GET embed page: {mediaUrl}")
                                ticket_resp = authMart.get(mediaUrl, headers=nav_headers)
                                http_log("GET", mediaUrl, ticket_resp.status_code, ticket_resp.text[:300])
                                if ticket_resp.status_code == 200:
                                    debug(f"[EMBED HTML] Primeros 2000 chars:\n{ticket_resp.text[:2000]}")
                                    try:
                                        ticket_data = ticket_resp.json()
                                        if isinstance(ticket_data, dict):
                                            debug(f"[EMBED JSON] {json.dumps(ticket_data)[:500]}")
                                            assets = ticket_data.get('assets', [])
                                            for asset in assets:
                                                if asset.get('url') and 'm3u8' in asset.get('url'):
                                                    hls_url = asset.get('url')
                                                    break
                                            if not hls_url:
                                                hls_url = ticket_data.get('mediaSrcUrl') or ticket_data.get('url') or ticket_data.get('hlsUrl')
                                    except Exception:
                                        pass

                                    if not hls_url and ticket_resp.text:
                                        # Decodificar escapes unicode JSON (\u0026 → &, \u003d → =, etc.)
                                        # ya que la URL m3u8 está embebida dentro de un JSON en el HTML
                                        import codecs
                                        raw_text = ticket_resp.text
                                        # Reemplazar secuencias de escape JSON unicode → caracteres reales
                                        try:
                                            raw_text = raw_text.encode('utf-8').decode('unicode_escape', errors='replace')
                                        except Exception:
                                            pass
                                        raw_text = raw_text.replace('\\/', '/').replace('\\u0026', '&').replace('\\u003d', '=').replace('\\u003D', '=')
                                        m3u8_matches = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', raw_text)
                                        debug(f"[EMBED REGEX] m3u8 encontrados (decodificados): {m3u8_matches[:2]}")
                                        if m3u8_matches:
                                            for m in m3u8_matches:
                                                if 'hdnts=' in m or 'Key-Pair-Id=' in m or 'token=' in m or 'Signature=' in m:
                                                    hls_url = m
                                                    break
                                            if not hls_url:
                                                for m in m3u8_matches:
                                                    if 'master' in m or 'play' in m:
                                                        hls_url = m
                                                        break
                                            if not hls_url:
                                                hls_url = m3u8_matches[0]
                                        if hls_url:
                                            # Decodificar el percent-encoding de la URL (%7E → ~, %3D → =, etc.)
                                            from urllib.parse import unquote
                                            hls_url = unquote(hls_url)
                                            debug(f"[EMBED] hls_url decodificada: {hls_url[:150]}")

                            # ─────────────────────────────────────────────────────────────────────
                            # ESTRATEGIA 4: Endpoints alternativos de ticket
                            # ─────────────────────────────────────────────────────────────────────
                            if not hls_url:
                                ticket_endpoints = [
                                    f"https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/lessons/{aula[2]}/medias/{videoHash}/ticket",
                                    f"https://api-player.hotmart.com/v1/media/{videoHash}/ticket",
                                    f"https://api-club.hotmart.com/hot-club-api/rest/v3/media/{videoHash}/ticket"
                                ]
                                for ep in ticket_endpoints:
                                    print(f"[HTTP] Consultando ticket endpoint: {ep[:70]}...")
                                    debug(f"[HTTP] GET ticket: {ep}")
                                    t_resp = authMart.get(ep, headers=nav_headers)
                                    http_log("GET", ep, t_resp.status_code, t_resp.text[:300])
                                    if t_resp.status_code == 200:
                                        try:
                                            t_json = t_resp.json()
                                            debug(f"[TICKET JSON] {json.dumps(t_json)[:500]}")
                                            hls_url = t_json.get('mediaSrcUrl') or t_json.get('url') or t_json.get('hlsUrl')
                                            if hls_url:
                                                break
                                        except Exception:
                                            pass

                            if not hls_url:
                                print(f"[ERROR] No se pudo obtener la URL HLS para {videoHash}. Revisa debug.log en la carpeta del curso.")
                                loga(first_folder, "ERROR", f"No se obtuvo hls_url para videoHash={videoHash}")
                                debug(f"[ERROR] Todas las estrategias fallaron para {videoHash}")
                                continue

                            debug(f"[HLS] hls_url final: {hls_url}")

                            # Definir cabeceras de reproductor para Akamai/CloudFront
                            player_headers = {
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                                'Origin': 'https://cf-embed.play.hotmart.com',
                                'Referer': mediaUrl if mediaUrl else 'https://cf-embed.play.hotmart.com/'
                            }

                            print(f"[HTTP] Solicitando master playlist desde: {hls_url[:80]}...")
                            debug(f"[HTTP] GET master playlist: {hls_url}")
                            teste = authMart.get(hls_url, headers=player_headers)
                            http_log("GET", hls_url, teste.status_code, teste.text[:300])

                            if teste.status_code != 200:
                                player_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"
                                teste = authMart.get(hls_url, headers=player_headers)
                                http_log("GET (retry referer)", hls_url, teste.status_code, teste.text[:300])

                            if teste.status_code != 200:
                                print(f"[ERROR] HTTP {teste.status_code} al obtener master playlist")
                                debug(f"[ERROR] master playlist response body:\n{teste.text[:1000]}")
                                loga(first_folder, "ERROR", f"HTTP {teste.status_code} en master playlist")
                                continue

                            masterPlaylist = m3u8.loads(teste.text)
                            target_playlist = None
                            if masterPlaylist.playlists:
                                # Ordenar playlists por ancho de banda/resolución
                                masterPlaylist.playlists.sort(key=lambda p: p.stream_info.bandwidth if p.stream_info.bandwidth else 0, reverse=True)
                                target_playlist = masterPlaylist.playlists[0]
                                highestQual_uri = target_playlist.uri
                            else:
                                highestQual_uri = ""

                            print(f"[INFO] Variantes detectadas. URI seleccionada: {highestQual_uri}")

                            # Resolver la URL completa de la variante resolviendo rutas relativas y preservando token si existe
                            if highestQual_uri.startswith("http"):
                                variant_url = highestQual_uri
                            else:
                                variant_url = urljoin(hls_url, highestQual_uri)
                                # Si la URL principal tenia query params (tokens hdnts/hdntl) y la variante no, adjuntarlos
                                base_parsed = urlparse(hls_url)
                                var_parsed = urlparse(variant_url)
                                if base_parsed.query and not var_parsed.query:
                                    variant_url = f"{variant_url}?{base_parsed.query}"

                            print(f"[HTTP] Descargando manifiesto de calidad variante desde: {variant_url[:80]}...")
                            highqual = authMart.get(variant_url, headers=player_headers)

                            if highqual.status_code != 200:
                                print(f"[ERROR] HTTP {highqual.status_code} al obtener la playlist de calidad")
                                continue

                            targetm3u8 = m3u8.loads(highqual.text)
                            total_segmentos = len(targetm3u8.segments)
                            print(f"[INFO] Total de fragmentos de video a descargar: {total_segmentos}")

                            # Reescribir dump.m3u8 apuntando a los archivos .ts locales (sin query string ni path)
                            # FFMPEG no puede resolver URLs con ?hdntl= como archivos locales
                            lines = highqual.text.splitlines()
                            clean_lines = []
                            for line in lines:
                                stripped = line.strip()
                                # Líneas de segmento: no empiezan con # y terminan en .ts (posiblemente con ?query)
                                if stripped and not stripped.startswith('#'):
                                    # Extraer solo el nombre de archivo local sin query string
                                    seg_local = os.path.basename(urlparse(stripped).path)
                                    clean_lines.append(seg_local)
                                elif stripped.startswith('#EXT-X-KEY') or stripped.startswith('#EXT-X-SESSION-KEY'):
                                    # Reemplazar la URI de la llave con el nombre de archivo local
                                    key_match = re.search(r'URI="([^"]+)"', stripped)
                                    if key_match:
                                        key_full_uri = key_match.group(1)
                                        key_local_name = os.path.basename(urlparse(key_full_uri).path)
                                        line = re.sub(r'URI="[^"]+"', f'URI="{key_local_name}"', line)
                                    clean_lines.append(line)
                                else:
                                    clean_lines.append(line)

                            with open('temp/dump.m3u8', 'w', encoding='utf-8') as dump:
                                dump.write("\n".join(clean_lines))

                            key_uri = None
                            for idx_seg, segment in enumerate(targetm3u8.segments, 1):
                                if segment.key and segment.key.uri:
                                    key_uri = segment.key.uri
                                
                                seg_rel_uri = segment.uri
                                if seg_rel_uri.startswith("http"):
                                    seg_url = seg_rel_uri
                                else:
                                    seg_url = urljoin(variant_url, seg_rel_uri)
                                    var_q = urlparse(variant_url).query
                                    if var_q and not urlparse(seg_url).query:
                                        seg_url = f"{seg_url}?{var_q}"

                                # Descarga de fragmento con porcentaje visible en consola
                                porcentaje = int((idx_seg / total_segmentos) * 100)
                                print(f"\r[DESCARGA VIDEO] [{porcentaje:3d}%] Fragmento {idx_seg}/{total_segmentos}", end="", flush=True)
                                
                                local_seg_filename = os.path.basename(urlparse(seg_rel_uri).path)
                                frag = authMart.get(seg_url, headers=player_headers)
                                with open("temp/" + local_seg_filename, 'wb') as sfrag:
                                    sfrag.write(frag.content)

                            print() # Nueva línea tras terminar los fragmentos
                            loga(first_folder, "INFO", f"Todos los {total_segmentos} fragmentos HLS descargados correctamente")

                            if key_uri:
                                print(f"[HTTP] Descargando llave de descifrado: {key_uri[:60]}...")
                                if key_uri.startswith("http"):
                                    key_url = key_uri
                                else:
                                    key_url = urljoin(variant_url, key_uri)
                                    var_q = urlparse(variant_url).query
                                    if var_q and not urlparse(key_url).query:
                                        key_url = f"{key_url}?{var_q}"
                                        
                                local_key_filename = os.path.basename(urlparse(key_uri).path)
                                fragkey = authMart.get(key_url, headers=player_headers)
                                with open("temp/" + local_key_filename, 'wb') as skey:
                                    skey.write(fragkey.content)
                                print("[OK] Llave de descifrado descargada correctamente")

                            print("[FFMPEG] Ensamblando video .mp4...")
                            dest_abs = os.path.abspath(folder_path_class_video)
                            
                            # Comando FFMPEG ejecutado directamente en la carpeta temp
                            cwd_actual = os.getcwd()
                            os.chdir("temp")
                            ffmpegcmd = f'ffmpeg -y -hide_banner -loglevel warning -allowed_extensions ALL -protocol_whitelist file,http,https,tcp,tls,crypto -i dump.m3u8 -c copy "{dest_abs}"'

                            loga(first_folder, "INFO", "Ejecutando FFMPEG")
                            try:
                                proc = subprocess.run(ffmpegcmd, shell=True, capture_output=True, text=True)
                                os.chdir(cwd_actual)
                                
                                if os.path.exists(dest_abs) and os.path.getsize(dest_abs) > 0:
                                    size_mb = os.path.getsize(dest_abs) / (1024 * 1024)
                                    print(f"¡ÉXITO! Video descargado y guardado en: {dest_abs} ({size_mb:.2f} MB)")
                                    loga(first_folder, "INFO", f"Video guardado ({size_mb:.2f} MB)")
                                else:
                                    print(f"[ERROR FFMPEG]: {proc.stderr}")
                                    loga(first_folder, "ERROR", f"FFMPEG fallo: {proc.stderr}")
                            except Exception as e:
                                os.chdir(cwd_actual)
                                print(f"[ERROR SUBPROCESS]: {e}")

                            time.sleep(1)
                            for f in glob.glob("temp/*"):
                                if os.path.isfile(f):
                                    try:
                                        os.remove(f)
                                    except Exception:
                                        pass

                            loga(first_folder, "INFO", "Temporary folder cleared")
                        else:
                            print("Class already exists, skipping...")
                            loga(first_folder, "INFO", "Clase ya presente, omitida")

                # 3. Descarga de archivos adjuntos nativos de la clase (PDFs, ZIPs, etc.)
                if aula[4]['anexos']:
                    print(f"\n{len(aula[4]['anexos'])} anexo(s) encontrado(s) para la clase: {aula[1]}")
                    folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materiais"
                    if not os.path.exists(folder_path_class_attach):
                        os.makedirs(folder_path_class_attach)
                        loga(first_folder, "INFO",
                             f"Carpeta de materiales creada en la clase {str(aula[0])}. {aula[1]}")
                    
                    anexos_baixados = 0
                    anexos_pulados = 0
                    anexos_falhos = 0
                    
                    for idx, i in enumerate(aula[4]['anexos'], 1):
                        anexo_id = i[0]
                        anexo_nome = i[1]
                        folder_path_class_attach_file = f"{folder_path_class_attach}/{anexo_nome}"
                        
                        print(f"  [{idx}/{len(aula[4]['anexos'])}] {anexo_nome}")
                        
                        if os.path.isfile(folder_path_class_attach_file):
                            file_size = os.path.getsize(folder_path_class_attach_file)
                            if file_size > 0:
                                print(f"      [OK] Ya existe ({file_size} bytes) - omitiendo")
                                loga(first_folder, "INFO", f"Anexo ya existente: {anexo_nome} ({file_size} bytes)")
                                anexos_pulados += 1
                                continue
                            else:
                                print("      [AVISO] El archivo existe pero está vacío - re-descargando")
                                loga(first_folder, "WARN", f"Anexo vacío detectado, re-descargando: {anexo_nome}")
                                os.remove(folder_path_class_attach_file)
                        
                        max_tentativas = 3
                        sucesso = False
                        
                        for tentativa in range(1, max_tentativas + 1):
                            try:
                                if tentativa > 1:
                                    print(f"      [REINTENTO] Reintento {tentativa}/{max_tentativas}...")
                                    time.sleep(2)
                                
                                loga(first_folder, "INFO", f"Descargando anexo {anexo_nome} (intento {tentativa})")
                                
                                response = authMart.get(
                                    f'https://api-club.hotmart.com/hot-club-api/rest/v3/attachment/{anexo_id}/download',
                                    timeout=30
                                )
                                
                                if response.status_code != 200:
                                    raise Exception(f"Error HTTP {response.status_code}: {response.text[:100]}")
                                
                                anexo_info = response.json()
                                
                                if 'directDownloadUrl' in anexo_info:
                                    print("      [DOWNLOAD] Descargando vía directDownloadUrl...")
                                    anexo = requests.get(anexo_info['directDownloadUrl'], timeout=60)
                                    
                                    if anexo.status_code != 200:
                                        raise Exception(f"Error al descargar: HTTP {anexo.status_code}")
                                
                                elif 'lambdaUrl' in anexo_info:
                                    print("      [DOWNLOAD] Descargando vía lambdaUrl...")
                                    vrum = requests.session()
                                    vrum.headers.update(authMart.headers)
                                    vrum.headers['token'] = anexo_info.get('token', '')
                                    
                                    lambda_response = vrum.get(anexo_info['lambdaUrl'], timeout=30)
                                    download_url = lambda_response.text
                                    anexo = requests.get(download_url, timeout=60)
                                    del vrum
                                    
                                    if anexo.status_code != 200:
                                        raise Exception(f"Error al descargar vía lambda: HTTP {anexo.status_code}")
                                else:
                                    raise Exception("No se encontró URL de descarga en la respuesta de la API")
                                
                                if not anexo.content or len(anexo.content) == 0:
                                    raise Exception("Contenido vacío recibido")
                                
                                with open(folder_path_class_attach_file, 'wb') as ann:
                                    ann.write(anexo.content)
                                
                                if not os.path.exists(folder_path_class_attach_file):
                                    raise Exception("El archivo no fue guardado correctamente")
                                
                                file_size = os.path.getsize(folder_path_class_attach_file)
                                if file_size == 0:
                                    raise Exception("El archivo guardado está vacío")
                                
                                print(f"      [OK] Descargado con éxito ({file_size} bytes)")
                                loga(first_folder, "INFO", f"Anexo descargado: {anexo_nome} ({file_size} bytes)")
                                anexos_baixados += 1
                                sucesso = True
                                break
                                
                            except Exception as e:
                                erro_msg = str(e)
                                loga(first_folder, "ERROR", f"Error al descargar anexo {anexo_nome} (intento {tentativa}): {erro_msg}")
                                
                                if tentativa == max_tentativas:
                                    print(f"      [ERROR] FALTA tras {max_tentativas} intentos: {erro_msg}")
                                    anexos_falhos += 1
                                    
                                    if os.path.exists(folder_path_class_attach_file):
                                        try:
                                            os.remove(folder_path_class_attach_file)
                                        except:
                                            pass
                                else:
                                    print(f"      [AVISO] Error: {erro_msg}")
                        
                        if sucesso:
                            time.sleep(0.5)
                    
                    print("\n  [RESUMEN] Anexos:")
                    print(f"     Descargados: {anexos_baixados}")
                    print(f"     Omitidos: {anexos_pulados}")
                    if anexos_falhos > 0:
                        print(f"     Fallos: {anexos_falhos}")
                    print()
                    
                    loga(first_folder, "INFO", f"Anexos procesados - Descargados: {anexos_baixados}, Omitidos: {anexos_pulados}, Fallos: {anexos_falhos}")

                # 4. Procesar archivos PDF de Google Drive incrustados en la lección HTML
                try:
                    aula_completa = authMart.get(f'https://api-club.hotmart.com/hot-club-api/rest/v3/page/{aula[2]}').json()
                    content_html = aula_completa.get('content', '')
                    
                    if content_html:
                        google_drive_files = extrair_google_drive_urls(content_html)
                        
                        if google_drive_files:
                            print(f"\n{len(google_drive_files)} archivo(s) incrustado(s) de Google Drive detectado(s) en el contenido HTML de la clase")
                            
                            folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materiais"
                            if not os.path.exists(folder_path_class_attach):
                                os.makedirs(folder_path_class_attach)
                                loga(first_folder, "INFO", "Carpeta de materiales creada para archivos de Google Drive")
                            
                            gdrive_baixados = 0
                            gdrive_pulados = 0
                            gdrive_falhos = 0
                            
                            for idx, (file_id, preview_url, download_url) in enumerate(google_drive_files, 1):
                                file_name = f"gdrive_{file_id}.pdf"
                                output_path = f"{folder_path_class_attach}/{file_name}"
                                
                                print(f"  [{idx}/{len(google_drive_files)}] {file_name}")
                                
                                if os.path.isfile(output_path):
                                    file_size = os.path.getsize(output_path)
                                    if file_size > 0:
                                        print(f"      [OK] Ya existe ({file_size} bytes) - omitiendo")
                                        loga(first_folder, "INFO", f"Archivo de Google Drive ya existente: {file_name}")
                                        gdrive_pulados += 1
                                        continue
                                    else:
                                        print("      [AVISO] El archivo existe pero está vacío - re-descargando")
                                        os.remove(output_path)
                                
                                print("      [DOWNLOAD] Descargando desde Google Drive...")
                                sucesso = baixar_google_drive(file_id, download_url, output_path, first_folder)
                                
                                if sucesso:
                                    print("      [OK] Descargado con éxito")
                                    gdrive_baixados += 1
                                else:
                                    print("      [ERROR] Fallo en la descarga")
                                    gdrive_falhos += 1
                                
                                time.sleep(1)
                            
                            print("\n  [RESUMEN] Archivos de Google Drive:")
                            print(f"     Descargados: {gdrive_baixados}")
                            print(f"     Omitidos: {gdrive_pulados}")
                            if gdrive_falhos > 0:
                                print(f"     Fallos: {gdrive_falhos}")
                            print()
                            
                            loga(first_folder, "INFO", f"Google Drive files - Descargados: {gdrive_baixados}, Omitidos: {gdrive_pulados}, Fallos: {gdrive_falhos}")
                
                except Exception as e:
                    loga(first_folder, "ERROR", f"Error al procesar contenido de Google Drive: {str(e)}")

                # 5. Guardar enlaces externos/complementarios en links.txt
                if aula[5]['links']:
                    folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materiais"
                    print(f"Guardando enlaces encontrados para la clase en\n\t {folder_path_class_attach}")
                    loga(first_folder, "INFO", f"Enlaces detectados para la clase {str(aula[0])}{aula[1]}")
                    folder_path_class_links = f"{folder_path_class_attach}/links.txt"
                    with open(folder_path_class_links, "a", encoding="utf-8") as linkz:
                        for i in aula[5]['links']:
                            linkz.write(f"{i[0]}: {i[1]}\n")
                    loga(first_folder, "INFO", "Links saved successfully")


login = {
    "Info": "You can define your email and password here if you do not want to enter them in the console each time.",
    "autor": "Telegram: @katomaro"
}

listacursos(*autenticacao(**login))
