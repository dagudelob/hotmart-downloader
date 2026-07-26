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
import requests
import m3u8  # pip install m3u8
import re
import os
import json
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup  # pip install beautifulsoup4

import subprocess
import glob

# Import modular helper functions
from utils import slugify
from logger import loga, debug, http_log, set_debug_log, print_color
from cli import select_item_cli
from auth import autenticacao
from gdrive import extrair_google_drive_urls, baixar_google_drive


def listacursos(authMart, params):
    """
    Retrieves the list of courses associated with the user's Hotmart account.
    Then navigates the modules, classes, videos, and materials structure to download them.
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


    # Course selection with validation loop and exit support
    cursor_opts = [f"{c['nome']} (subdomain: {c['resource']['subdomain']})" for c in cursosValidos]
    opcao = select_item_cli(cursor_opts, title=f"Cursos disponibles ({len(cursosValidos)} encontrado(s))")
    
    nmcurso = slugify(cursosValidos[opcao]['nome'])

    loga(".", "INFO", f"Starting course download: {nmcurso}")
    loga(".", "INFO", f"{cursosValidos[opcao]}")
    
    # Save directory set to course root
    first_folder = f'{nmcurso}'
    if not os.path.exists(first_folder):
        os.makedirs(first_folder)
    
    # Initialize detailed debug log
    set_debug_log(first_folder)
    debug(f"=== Iniciando sesión de descarga para curso: {nmcurso} ===")
        
    dominio = cursosValidos[opcao]['resource']['subdomain']
    authMart.headers['origin'] = f'https://{dominio}.club.hotmart.com/'
    authMart.headers['referer'] = f'https://{dominio}.club.hotmart.com/'

    authMart.headers['club'] = dominio
    
    # Retrieve the complete map of course modules and lessons
    resp_nav = authMart.get('https://api-club.hotmart.com/hot-club-api/rest/v3/navigation')
    if resp_nav.status_code == 200 and 'modules' in resp_nav.json():
        curso = resp_nav.json()
    else:
        # Request to the new consumption gateway with authorization
        nav_headers = {
            'origin': 'https://hotmart.com',
            'referer': 'https://hotmart.com/',
            'x-app-name': 'app-club-consumer_v1.357.2_production'
        }
        # Try retrieving product_id from resource info
        prod_id = cursosValidos[opcao].get('resource', {}).get('productId') or cursosValidos[opcao].get('productId') or "1643794"
        nav_headers['x-product-id'] = str(prod_id)

        resp_nav = authMart.get(
            f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/navigation?subdomain={dominio}',
            headers=nav_headers
        )
        
        # If x-product-id is still required, try fetching from user status
        if resp_nav.status_code == 400 and 'x-product-id' in resp_nav.text:
            # Get membership info to extract productId
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
            print_color(f"[ERROR] Could not retrieve modules list (HTTP {resp_nav.status_code}):")
            print_color(f"[ERROR] API Response: {resp_nav.text[:300]}")
            exit(1)

    if 'modules' not in curso:
        print_color(f"[ERROR] The structure returned by the API does not contain 'modules'. Received keys: {list(curso.keys())}")
        print_color(f"[ERROR] Full response: {str(curso)[:300]}")
        exit(1)

    estrutura = {}
    tempAula = []
    aulas = []
    tempAnexo = []
    tempLink = []
    x = 0

    loga(first_folder, "INFO", "Structure retrieved successfully, building course dictionary")

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
                     
            # If the navigation menu embeds media in memory
            medias = i.get('mediasSrc') or i.get('medias') or []
            for video in medias:
                v_name = video.get('mediaName') or video.get('name') or 'video'
                v_code = video.get('mediaCode') or video.get('code') or video.get('id')
                v_url = video.get('mediaSrcUrl') or video.get('url') or video.get('src')
                tempAula = [re.sub(r'[<>:"/\\|?*]', '', v_name).strip(), v_code, v_url]
                aulas[3]['videos'].append(tempAula)

            estrutura[mod_order][mod_name_clean].append(aulas)

    # Save a backup copy of the structure to debug.txt
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
            # Filter if selective download mode was chosen
            if (modo_descarga == "1" or modo_descarga == "3"):
                clases_filtradas = [a for a in estrutura[modulo][aulas] if a[2] in clases_a_descargar]
                if not clases_filtradas:
                    continue
            
            folder_path = f'{first_folder}/{slugify(str(modulo))}_{slugify(aulas)}'
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

                loga(first_folder, "INFO", f"Created module directory: {str(modulo)}.{aulas}")

            for aula in estrutura[modulo][aulas]:
                # If selective mode is enabled, skip non-selected classes
                if (modo_descarga == "1" or modo_descarga == "3") and aula[2] not in clases_a_descargar:
                    continue

                folder_path_class = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}"
                print_color(f"[INFO] Verifying class: {folder_path_class}")
                if not os.path.exists(folder_path_class):
                    os.makedirs(folder_path_class)

                    loga(first_folder, "INFO", f"Created class directory: {slugify(str(aula[0]))}.{slugify(aula[1])}")

                # 1. Retrieve class details (HTML, attachments and links)
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
                        
                    # Extract attachments if not already cached
                    if not aula[4]['anexos']:
                        attachments = lesson_data.get('attachments') if 'lesson_data' in locals() else lesson_json.get('attachments', [])
                        for anexo in attachments:
                            tempAnexo = [anexo.get('fileMembershipId') or anexo.get('id'), re.sub(r'[<>:"/\\|?*]', '', anexo.get('fileName') or anexo.get('name') or 'anexo').strip()]
                            aula[4]['anexos'].append(tempAnexo)

                    # Extract links if not already cached
                    if not aula[5]['links']:
                        links = lesson_json.get('complementaryReadings') or lesson_json.get('links') or []
                        for link in links:
                            tempLink = [re.sub(r'[<>:"/\\|?*]', '', link.get('articleName') or link.get('name') or 'link').strip(), link.get('articleUrl') or link.get('url')]
                            aula[5]['links'].append(tempLink)

                    if desct:
                        with open(f"{folder_path_class}/descripcion.html", 'w', encoding='utf-8') as dd:
                            dd.write(str(desct))
                            loga(first_folder, "INFO", f"Description saved successfully for class: {str(aula[0])}.{aula[1]}")
                except Exception as e_desc:
                    loga(first_folder, "ERROR", f"Fallo al guardar la descripción de la clase {str(aula[0])}. {aula[1]}: {e_desc}")

                # 2. Download videos
                # Fetch lesson details from API v2 if video data is missing
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

                                loga(first_folder, "INFO", f"Vimeo video detected: {i.get('src')}")

                                if '?' in i.get("src"):
                                    linkV = i.get("src").split('?')[0]
                                else:
                                    linkV = i.get("src")
                                if linkV[-1] == "/":
                                    linkV = linkV.split("/")[-1]

                            elif 'vimeo.com' in i.get("src"):
                                youtube_dl.utils.std_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"

                                loga(first_folder, "INFO", f"Vimeo video detected: {i.get('src')}")

                                vimeoID = i.get("src").split('vimeo.com/')[1]
                                if "?" in vimeoID:
                                    vimeoID = vimeoID.split("?")[0]
                                linkV = "https://player.vimeo.com/video/" + vimeoID

                            elif "wistia.com" in i.get("src"):
                                loga(first_folder, "ERROR", f"WISTIA! Vídeo encontrado: {i.get('src')}")
                                pass

                            elif "youtube.com" in i.get("src") or "youtu.be" in i.get("src"):
                                loga(first_folder, "INFO", f"YouTube video detected: {i.get('src')}")
                                linkV = i.get("src")
                                
                            # Format video filename as module.class.mp4
                            video_filename = f"{slugify(str(modulo))}.{slugify(str(aula[0]))}.mp4"
                            folder_path_class_video = f'{folder_path_class}/{video_filename}'
                            if not os.path.isfile(folder_path_class_video):
                                print(f"Downloading external class:\n\t {folder_path_class_video}")
                                ydl_opts = {"format": "best", 'outtmpl': folder_path_class_video}
                                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                                    ydl.download([linkV])
                                    loga(first_folder, "INFO", "External video downloaded successfully.")
                            else:
                                print_color("[INFO] Class already exists, skipping...")
                                loga(first_folder, "INFO", "Clase ya presente. Omitida.")

                    except:
                        loga(first_folder, "WARN",
                             "No videos found on the platform, checking if it is a text-only class.")
                        pass

                else:  # Native Hotmart Player (HLS m3u8)
                    for x, i in enumerate(aula[3]['videos'], start=1):
                        video_filename = f"{slugify(str(modulo))}.{slugify(str(aula[0]))}.mp4"
                        folder_path_class_video = f'{folder_path_class}/{video_filename}'
                        if not os.path.isfile(folder_path_class_video):
                            print_color(f"[DOWNLOAD] Attempting to download Hotmart class: {video_filename}")
                            loga(first_folder, "INFO", f"Attempting to download class: {str(aula[0])} ({aula[1]})")

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
                            print_color(f"[YTDLP] Attempting with Chrome cookies: {mediaUrl[:70]}...")
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
                                    print_color(f"[INFO] Video downloaded successfully via yt-dlp+cookies ({size_mb:.2f} MB)")
                                    loga(first_folder, "INFO", f"Video descargado con yt-dlp+cookies ({size_mb:.2f} MB)")
                                    continue
                                else:
                                    print_color("[WARNING] yt-dlp did not download the file directly. Retrying HLS manual extraction...")
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

                                print_color(f"[HTTP] [API PLAYER] GET {player_api_url}")
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
                                    print_color(f"[WARNING] [API PLAYER] {e_papi}")

                            # ─────────────────────────────────────────────────────────────────────
                            # ESTRATEGIA 3: Parsear la página embed cf-embed para extraer m3u8
                            # ─────────────────────────────────────────────────────────────────────
                            if not hls_url and mediaUrl:
                                print_color(f"[HTTP] Requesting embed page: {mediaUrl[:75]}...")
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
                                    print_color(f"[HTTP] Querying ticket endpoint: {ep[:70]}...")
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
                                print_color(f"[ERROR] Could not obtain HLS URL for {videoHash}. Please review debug.log inside the course folder.")
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

                            print_color(f"[HTTP] Requesting master playlist from: {hls_url[:80]}...")
                            debug(f"[HTTP] GET master playlist: {hls_url}")
                            teste = authMart.get(hls_url, headers=player_headers)
                            http_log("GET", hls_url, teste.status_code, teste.text[:300])

                            if teste.status_code != 200:
                                player_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"
                                teste = authMart.get(hls_url, headers=player_headers)
                                http_log("GET (retry referer)", hls_url, teste.status_code, teste.text[:300])

                            if teste.status_code != 200:
                                print_color(f"[ERROR] HTTP {teste.status_code} retrieving master playlist")
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

                            print_color(f"[INFO] Variants detected. Selected URI: {highestQual_uri}")

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

                            print_color(f"[HTTP] Downloading variant manifest from: {variant_url[:80]}...")
                            highqual = authMart.get(variant_url, headers=player_headers)

                            if highqual.status_code != 200:
                                print_color(f"[ERROR] HTTP {highqual.status_code} obtaining variant quality playlist")
                                continue

                            targetm3u8 = m3u8.loads(highqual.text)
                            total_segmentos = len(targetm3u8.segments)
                            print_color(f"[INFO] Total video segments to download: {total_segmentos}")

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
                                print_color(f"[HTTP] Downloading decryption key: {key_uri[:60]}...")
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
                                print_color("[INFO] Decryption key downloaded successfully")

                            print_color("[FFMPEG] Assembling .mp4 video...")
                            dest_abs = os.path.abspath(folder_path_class_video)
                            
                            # Comando FFMPEG ejecutado directamente en la carpeta temp
                            cwd_actual = os.getcwd()
                            os.chdir("temp")
                            ffmpegcmd = f'ffmpeg -y -hide_banner -loglevel warning -allowed_extensions ALL -protocol_whitelist file,http,https,tcp,tls,crypto -i dump.m3u8 -c copy "{dest_abs}"'

                            loga(first_folder, "INFO", "Executing FFMPEG")
                            try:
                                proc = subprocess.run(ffmpegcmd, shell=True, capture_output=True, text=True)
                                os.chdir(cwd_actual)
                                
                                if os.path.exists(dest_abs) and os.path.getsize(dest_abs) > 0:
                                    size_mb = os.path.getsize(dest_abs) / (1024 * 1024)
                                    print_color(f"[INFO] SUCCESS! Video downloaded and saved to: {dest_abs} ({size_mb:.2f} MB)")
                                    loga(first_folder, "INFO", f"Video guardado ({size_mb:.2f} MB)")
                                else:
                                    print_color(f"[ERROR] FFMPEG failed: {proc.stderr}")
                                    loga(first_folder, "ERROR", f"FFMPEG fallo: {proc.stderr}")
                            except Exception as e:
                                os.chdir(cwd_actual)
                                print_color(f"[ERROR] Subprocess error: {e}")

                            time.sleep(1)
                            for f in glob.glob("temp/*"):
                                if os.path.isfile(f):
                                    try:
                                        os.remove(f)
                                    except Exception:
                                        pass

                            loga(first_folder, "INFO", "Temporary folder cleared")
                        else:
                            print_color("[INFO] Class already exists, skipping...")
                            loga(first_folder, "INFO", "Clase ya presente, omitida")

                # 3. Download native attachments (PDFs, ZIPs, etc.)
                if aula[4]['anexos']:
                    print_color(f"\n[INFO] {len(aula[4]['anexos'])} attachment(s) found for class: {aula[1]}")
                    folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materiais"
                    if not os.path.exists(folder_path_class_attach):
                        os.makedirs(folder_path_class_attach)
                        loga(first_folder, "INFO",
                             f"Materials directory created for class: {str(aula[0])}. {aula[1]}")
                    
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
                                print_color(f"      [OK] Already exists ({file_size} bytes) - skipping")
                                loga(first_folder, "INFO", f"Attachment already exists: {anexo_nome} ({file_size} bytes)")
                                anexos_pulados += 1
                                continue
                            else:
                                print_color("      [WARNING] File exists but is empty - re-downloading")
                                loga(first_folder, "WARN", f"Empty attachment detected, re-downloading: {anexo_nome}")
                                os.remove(folder_path_class_attach_file)
                        
                        max_tentativas = 3
                        sucesso = False
                        
                        for tentativa in range(1, max_tentativas + 1):
                            try:
                                if tentativa > 1:
                                    print_color(f"      [WARNING] Retrying {tentativa}/{max_tentativas}...")
                                    time.sleep(2)
                                
                                loga(first_folder, "INFO", f"Downloading attachment: {anexo_nome} (intento {tentativa})")
                                
                                response = authMart.get(
                                    f'https://api-club.hotmart.com/hot-club-api/rest/v3/attachment/{anexo_id}/download',
                                    timeout=30
                                )
                                
                                if response.status_code != 200:
                                    raise Exception(f"Error HTTP {response.status_code}: {response.text[:100]}")
                                
                                anexo_info = response.json()
                                
                                if 'directDownloadUrl' in anexo_info:
                                    print_color("      [DOWNLOAD] Downloading via directDownloadUrl...")
                                    anexo = requests.get(anexo_info['directDownloadUrl'], timeout=60)
                                    
                                    if anexo.status_code != 200:
                                        raise Exception(f"Error al descargar: HTTP {anexo.status_code}")
                                
                                elif 'lambdaUrl' in anexo_info:
                                    print_color("      [DOWNLOAD] Downloading via lambdaUrl...")
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
                                
                                print_color(f"      [OK] Downloaded successfully ({file_size} bytes)")
                                loga(first_folder, "INFO", f"Attachment downloaded: {anexo_nome} ({file_size} bytes)")
                                anexos_baixados += 1
                                sucesso = True
                                break
                                
                            except Exception as e:
                                erro_msg = str(e)
                                loga(first_folder, "ERROR", f"Error al descargar anexo {anexo_nome} (intento {tentativa}): {erro_msg}")
                                
                                if tentativa == max_tentativas:
                                    print_color(f"      [ERROR] FAILED after {max_tentativas} attempts: {erro_msg}")
                                    anexos_falhos += 1
                                    
                                    if os.path.exists(folder_path_class_attach_file):
                                        try:
                                            os.remove(folder_path_class_attach_file)
                                        except:
                                            pass
                                else:
                                    print_color(f"      [WARNING] Error: {erro_msg}")
                        
                        if sucesso:
                            time.sleep(0.5)
                    
                    print_color("\n  [SUMMARY] Attachments:")
                    print(f"     Downloaded: {anexos_baixados}")
                    print(f"     Skipped: {anexos_pulados}")
                    if anexos_falhos > 0:
                        print_color(f"     Failed: {anexos_falhos}")
                    print()
                    
                    loga(first_folder, "INFO", f"Attachments processed - Downloaded: {anexos_baixados}, Omitidos: {anexos_pulados}, Fallos: {anexos_falhos}")

                # 4. Process embedded Google Drive PDFs from HTML
                try:
                    aula_completa = authMart.get(f'https://api-club.hotmart.com/hot-club-api/rest/v3/page/{aula[2]}').json()
                    content_html = aula_completa.get('content', '')
                    
                    if content_html:
                        google_drive_files = extrair_google_drive_urls(content_html)
                        
                        if google_drive_files:
                            print(f"\n{len(google_drive_files)} embedded Google Drive file(s) detected in the HTML content of the class")
                            
                            folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materials"
                            if not os.path.exists(folder_path_class_attach):
                                os.makedirs(folder_path_class_attach)
                                loga(first_folder, "INFO", "Materials folder created for Google Drive files")
                            
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
                                        print(f"      [OK] Already exists ({file_size} bytes) - skipping")
                                        loga(first_folder, "INFO", f"Google Drive file already exists: {file_name}")
                                        gdrive_pulados += 1
                                        continue
                                    else:
                                        print("      [WARNING] File exists but is empty - re-downloading")
                                        os.remove(output_path)
                                
                                print("      [DOWNLOAD] Downloading from Google Drive...")
                                sucesso = baixar_google_drive(file_id, download_url, output_path, first_folder)
                                
                                if sucesso:
                                    print("      [OK] Downloaded successfully")
                                    gdrive_baixados += 1
                                else:
                                    print("      [ERROR] Download failed")
                                    gdrive_falhos += 1
                                
                                time.sleep(1)
                            
                            print("\n  [SUMMARY] Google Drive Files:")
                            print(f"     Downloaded: {gdrive_baixados}")
                            print(f"     Skipped: {gdrive_pulados}")
                            if gdrive_falhos > 0:
                                print(f"     Failed: {gdrive_falhos}")
                            print()
                            
                            loga(first_folder, "INFO", f"Google Drive files - Downloaded: {gdrive_baixados}, Skipped: {gdrive_pulados}, Failed: {gdrive_falhos}")
                
                except Exception as e:
                    loga(first_folder, "ERROR", f"Error processing Google Drive content: {str(e)}")

                # 5. Save external/complementary links in links.txt
                if aula[5]['links']:
                    folder_path_class_attach = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}/Materials"
                    print(f"Saving links found for class in\n\t {folder_path_class_attach}")
                    loga(first_folder, "INFO", f"Links detected for class {str(aula[0])} {aula[1]}")
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
