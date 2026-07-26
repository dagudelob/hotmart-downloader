# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                      Hotmart Course Downloader                                                      #
#                                                                                                                     #
#  Based on the original gist by @juvenal: https://gist.github.com/juvenal/2d9a822325769d30c45c635fbf388c1b           #
#  With support for downloading Google Drive embedded files and external video hosts (Vimeo/YouTube)                  #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Requirements:
# - FFMPEG installed in the system and added to PATH
# - Python libraries: pip install -r requirements.txt (m3u8, beautifulsoup4, requests)

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
from cli import select_item_cli, input_number_cli
from auth import autenticacao
from gdrive import extrair_google_drive_urls, baixar_google_drive


def fetch_course_navigation(authMart, dominio, nav_headers):
    """
    Retrieve modules and pages of the course from Hotmart API.
    Supports gateway fallback routing.
    Raises RuntimeError on failure instead of calling exit() so web server stays alive.
    """
    # First attempt: legacy API (no subdomain needed)
    resp_nav = authMart.get(
        'https://api-club.hotmart.com/hot-club-api/rest/v3/navigation',
        headers=nav_headers
    )
    if resp_nav.status_code == 200 and 'modules' in resp_nav.json():
        return resp_nav.json()

    # Second attempt: new gateway with subdomain
    resp_nav = authMart.get(
        f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/navigation?subdomain={dominio}',
        headers=nav_headers
    )

    # Fallback to fetch productId if x-product-id header is required
    if resp_nav.status_code == 400 and 'x-product-id' in resp_nav.text:
        resp_mem = authMart.get(
            f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/user/{dominio}/status',
            headers=nav_headers
        )
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
        return curso
    else:
        print_color(f"[ERROR] Could not retrieve modules list (HTTP {resp_nav.status_code}):")
        print_color(f"[ERROR] API Response: {resp_nav.text[:300]}")
        raise RuntimeError(f"Hotmart API returned {resp_nav.status_code}: {resp_nav.text[:200]}")


def download_class_video(aula, modulo, folder_path_class, first_folder, authMart, nav_headers, dominio, progress_callback=None):
    """
    Downloads native HLS videos or external streams (Vimeo, YouTube) for a given class.
    """
    video_filename = f"{slugify(str(modulo))}.{slugify(str(aula[0]))}.mp4"
    folder_path_class_video = f'{folder_path_class}/{video_filename}'

    if os.path.isfile(folder_path_class_video):
        print_color("[INFO] Class already exists, skipping...")
        loga(first_folder, "INFO", "Class already exists, skipped")
        return

    # Case A: External video provider (Vimeo / YouTube)
    if not aula[3]['videos']:
        loga(first_folder, "WARN", "Class does not contain native Hotmart videos, checking external hosts...")
        desct = aula[5].get('html_content', '')
        if not desct:
            return

        try:
            pjson = BeautifulSoup(desct, features="html.parser")
            viframe = pjson.find_all("iframe")
            for x, i in enumerate(viframe, start=1):
                src = i.get("src", "")
                if 'player.vimeo' in src:
                    loga(first_folder, "INFO", f"[INFO] Vimeo video detected: {src}")
                    linkV = src.split('?')[0] if '?' in src else src
                    if linkV[-1] == "/":
                        linkV = linkV.split("/")[-1]

                elif 'vimeo.com' in src:
                    loga(first_folder, "INFO", f"[INFO] Vimeo video detected: {src}")
                    vimeoID = src.split('vimeo.com/')[1]
                    if "?" in vimeoID:
                        vimeoID = vimeoID.split("?")[0]
                    linkV = "https://player.vimeo.com/video/" + vimeoID

                elif "wistia.com" in src:
                    loga(first_folder, "ERROR", f"[ERROR] WISTIA video detected: {src} - wistia download is not supported")
                    continue

                elif "youtube.com" in src or "youtu.be" in src:
                    loga(first_folder, "INFO", f"[INFO] YouTube video detected: {src}")
                    linkV = src
                else:
                    continue

                print_color(f"[DOWNLOAD] Downloading external class: {video_filename}")
                yt_cmd = [
                    "yt-dlp",
                    "--referer", f"https://{dominio}.club.hotmart.com/",
                    "-f", "best",
                    "-o", os.path.abspath(folder_path_class_video),
                    linkV
                ]
                subprocess.run(yt_cmd, capture_output=True)
                loga(first_folder, "INFO", "External video downloaded successfully.")
                break
        except Exception as e_ext:
            loga(first_folder, "WARN", f"Failed parsing external videos: {e_ext}")
        return

    # Case B: Native Hotmart HLS player
    for idx_vid, video_item in enumerate(aula[3]['videos'], start=1):
        videoHash = video_item[1]
        mediaUrl = video_item[2]

        print_color(f"[DOWNLOAD] Attempting to download Hotmart class: {video_filename}")
        loga(first_folder, "INFO", f"Attempting to download class {str(aula[0])} ({aula[1]})")

        debug(f"=== Starting download video hash={videoHash} ===")
        debug(f"mediaUrl: {mediaUrl}")

        # Determine if it's a native Hotmart player embed
        is_native_hotmart = mediaUrl and any(d in mediaUrl for d in ['cf-embed.play.hotmart.com', 'play.hotmart.com', 'hotmart.com/embed'])

        # Strategy 1: yt-dlp (Only for external domains, skip for native Hotmart player)
        if not is_native_hotmart:
            print_color(f"[YTDLP] Attempting with Chrome cookies: {mediaUrl[:70]}...")
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
                res_yt = subprocess.run(yt_cmd, capture_output=True, text=True)
                if os.path.exists(folder_path_class_video) and os.path.getsize(folder_path_class_video) > 0:
                    size_mb = os.path.getsize(folder_path_class_video) / (1024 * 1024)
                    print_color(f"[SUCCESS] Video downloaded successfully via yt-dlp ({size_mb:.2f} MB)")
                    loga(first_folder, "INFO", f"Video downloaded successfully via yt-dlp ({size_mb:.2f} MB)")
                    return
            except Exception as e_yt:
                debug(f"[YTDLP] {e_yt}")

        hls_url = None

        # Strategy 2: Direct Embed Page HTML Extraction (Primary for Native Hotmart)
        if mediaUrl:
            print_color(f"[HTTP] Requesting embed page: {mediaUrl[:75]}...")
            ticket_resp = authMart.get(mediaUrl, headers=nav_headers)
            if ticket_resp.status_code == 200:
                try:
                    ticket_data = ticket_resp.json()
                    if isinstance(ticket_data, dict):
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
                    raw_text = ticket_resp.text
                    try:
                        raw_text = raw_text.encode('utf-8').decode('unicode_escape', errors='replace')
                    except Exception:
                        pass
                    raw_text = raw_text.replace('\\/', '/').replace('\\u0026', '&').replace('\\u003d', '=').replace('\\u003D', '=')
                    m3u8_matches = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', raw_text)
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
                        from urllib.parse import unquote
                        hls_url = unquote(hls_url)

        # Strategy 3: API Player Fallback (if embed page didn't yield m3u8)
        if not hls_url:
            jwt_in_url = None
            if mediaUrl and 'jwtToken=' in mediaUrl:
                try:
                    qs_m = parse_qs(urlparse(mediaUrl).query)
                    if 'jwtToken' in qs_m:
                        jwt_in_url = qs_m['jwtToken'][0]
                except Exception:
                    pass

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

                try:
                    resp_p = authMart.get(player_api_url, headers=player_api_headers)
                    if resp_p.status_code == 200:
                        p_data = resp_p.json()
                        assets = p_data.get('assets', [])
                        for a_item in assets:
                            if a_item.get('url') and 'm3u8' in a_item.get('url'):
                                hls_url = a_item.get('url')
                                break
                        if not hls_url:
                            hls_url = p_data.get('mediaSrcUrl') or p_data.get('url') or p_data.get('hlsUrl')
                        if hls_url:
                            break
                except Exception as e_papi:
                    debug(f"[API PLAYER] {e_papi}")

        # Strategy 4: Fallback ticket endpoints
        if not hls_url:
            ticket_endpoints = [
                f"https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/lessons/{aula[2]}/medias/{videoHash}/ticket",
                f"https://api-player.hotmart.com/v1/media/{videoHash}/ticket",
                f"https://api-club.hotmart.com/hot-club-api/rest/v3/media/{videoHash}/ticket"
            ]
            for ep in ticket_endpoints:
                print_color(f"[HTTP] Querying ticket endpoint: {ep[:70]}...")
                t_resp = authMart.get(ep, headers=nav_headers)
                if t_resp.status_code == 200:
                    try:
                        t_json = t_resp.json()
                        hls_url = t_json.get('mediaSrcUrl') or t_json.get('url') or t_json.get('hlsUrl')
                        if hls_url:
                            break
                    except Exception:
                        pass

        if not hls_url:
            print_color(f"[ERROR] Could not obtain HLS URL for {videoHash}. Please review debug.log inside the course folder.")
            loga(first_folder, "ERROR", f"No se obtuvo hls_url para videoHash={videoHash}")
            continue

        # Load master playlist and fetch highest quality segment URI
        player_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Origin': 'https://cf-embed.play.hotmart.com',
            'Referer': mediaUrl if mediaUrl else 'https://cf-embed.play.hotmart.com/'
        }

        print_color(f"[HTTP] Requesting master playlist from: {hls_url[:80]}...")
        teste = authMart.get(hls_url, headers=player_headers)
        if teste.status_code != 200:
            player_headers['Referer'] = f"https://{dominio}.club.hotmart.com/"
            teste = authMart.get(hls_url, headers=player_headers)

        if teste.status_code != 200:
            print_color(f"[ERROR] HTTP {teste.status_code} retrieving master playlist")
            continue

        masterPlaylist = m3u8.loads(teste.text)
        if masterPlaylist.playlists:
            masterPlaylist.playlists.sort(key=lambda p: p.stream_info.bandwidth if p.stream_info.bandwidth else 0, reverse=True)
            variant_url = urljoin(hls_url, masterPlaylist.playlists[0].uri)
            base_q = urlparse(hls_url).query
            if base_q and not urlparse(variant_url).query:
                variant_url = f"{variant_url}?{base_q}"
        else:
            variant_url = hls_url

        print_color(f"[HTTP] Downloading variant manifest from: {variant_url[:80]}...")
        highqual = authMart.get(variant_url, headers=player_headers)
        if highqual.status_code != 200:
            print_color(f"[ERROR] HTTP {highqual.status_code} obtaining variant quality playlist")
            continue

        targetm3u8 = m3u8.loads(highqual.text)
        total_segmentos = len(targetm3u8.segments)
        print_color(f"[INFO] Total video segments to download: {total_segmentos}")

        # Rewrite dump.m3u8 locally
        clean_lines = []
        for line in highqual.text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                clean_lines.append(os.path.basename(urlparse(stripped).path))
            elif stripped.startswith('#EXT-X-KEY') or stripped.startswith('#EXT-X-SESSION-KEY'):
                key_match = re.search(r'URI="([^"]+)"', stripped)
                if key_match:
                    key_local_name = os.path.basename(urlparse(key_match.group(1)).path)
                    line = re.sub(r'URI="[^"]+"', f'URI="{key_local_name}"', line)
                clean_lines.append(line)
            else:
                clean_lines.append(line)

        with open('temp/dump.m3u8', 'w', encoding='utf-8') as dump:
            dump.write("\n".join(clean_lines))

        # Download segments
        key_uri = None
        for idx_seg, segment in enumerate(targetm3u8.segments, 1):
            if segment.key and segment.key.uri:
                key_uri = segment.key.uri
            
            seg_rel_uri = segment.uri
            seg_url = seg_rel_uri if seg_rel_uri.startswith("http") else urljoin(variant_url, seg_rel_uri)
            var_q = urlparse(variant_url).query
            if var_q and not urlparse(seg_url).query:
                seg_url = f"{seg_url}?{var_q}"

            porcentaje = int((idx_seg / total_segmentos) * 100)
            print(f"\r[DESCARGA VIDEO] [{porcentaje:3d}%] Segment {idx_seg}/{total_segmentos}", end="", flush=True)
            if progress_callback:
                try:
                    progress_callback(idx_seg, total_segmentos, porcentaje, f"Segment {idx_seg}/{total_segmentos}")
                except Exception:
                    pass

            local_seg_filename = os.path.basename(urlparse(seg_rel_uri).path)
            frag = authMart.get(seg_url, headers=player_headers)
            with open("temp/" + local_seg_filename, 'wb') as sfrag:
                sfrag.write(frag.content)

        print()  # Finalize carriage return
        loga(first_folder, "INFO", f"All {total_segmentos} HLS segments downloaded successfully")

        # Download decryption key if exists
        if key_uri:
            print_color(f"[HTTP] Downloading decryption key: {key_uri[:60]}...")
            if progress_callback:
                try:
                    progress_callback(total_segmentos, total_segmentos, 95, "Downloading key...")
                except Exception:
                    pass
            key_url = key_uri if key_uri.startswith("http") else urljoin(variant_url, key_uri)
            var_q = urlparse(variant_url).query
            if var_q and not urlparse(key_url).query:
                key_url = f"{key_url}?{var_q}"
            
            local_key_filename = os.path.basename(urlparse(key_uri).path)
            fragkey = authMart.get(key_url, headers=player_headers)
            with open("temp/" + local_key_filename, 'wb') as skey:
                skey.write(fragkey.content)
            print_color("[INFO] Decryption key downloaded successfully")

        # FFMPEG assembly
        print_color("[FFMPEG] Assembling .mp4 video...")
        if progress_callback:
            try:
                progress_callback(total_segmentos, total_segmentos, 98, "Assembling with FFMPEG...")
            except Exception:
                pass
        dest_abs = os.path.abspath(folder_path_class_video)
        cwd_actual = os.getcwd()
        os.chdir("temp")
        ffmpegcmd = f'ffmpeg -y -hide_banner -loglevel warning -allowed_extensions ALL -protocol_whitelist file,http,https,tcp,tls,crypto -i dump.m3u8 -c copy "{dest_abs}"'

        loga(first_folder, "INFO", "Executing FFMPEG")
        try:
            proc = subprocess.run(ffmpegcmd, shell=True, capture_output=True, text=True)
            os.chdir(cwd_actual)
            if os.path.exists(dest_abs) and os.path.getsize(dest_abs) > 0:
                size_mb = os.path.getsize(dest_abs) / (1024 * 1024)
                print_color(f"[SUCCESS] Video downloaded and saved to: {dest_abs} ({size_mb:.2f} MB)")
                loga(first_folder, "INFO", f"Video saved ({size_mb:.2f} MB)")
            else:
                print_color(f"[ERROR] FFMPEG failed: {proc.stderr}")
                loga(first_folder, "ERROR", f"FFMPEG failed: {proc.stderr}")
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


def download_class_assets(aula, modulo, folder_path_class, first_folder, authMart, nav_headers, dominio, progress_callback=None):
    """
    Downloads description, video attachments, embedded files, and links for a class.
    """
    # 1. Fetch class details (HTML content description, attachments, readings)
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
        
        # Save HTML description
        if desct:
            aula[5]['html_content'] = desct
            with open(f"{folder_path_class}/description.html", 'w', encoding='utf-8') as dd:
                dd.write(str(desct))
                loga(first_folder, "INFO", f"Description saved successfully for class: {str(aula[0])}.{aula[1]}")
    except Exception as e_desc:
        loga(first_folder, "ERROR", f"Failed to save class description for {str(aula[0])}. {aula[1]}: {e_desc}")

    # 2. Process Video downloads
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

    download_class_video(aula, modulo, folder_path_class, first_folder, authMart, nav_headers, dominio, progress_callback=progress_callback)

    # 3. Native attachments downloads
    if not aula[4]['anexos'] and 'lesson_json' in locals():
        attachments = lesson_json.get('attachments', [])
        for anexo in attachments:
            aula[4]['anexos'].append([
                anexo.get('fileMembershipId') or anexo.get('id'), 
                re.sub(r'[<>:"/\\|?*]', '', anexo.get('fileName') or anexo.get('name') or 'anexo').strip()
            ])

    if aula[4]['anexos']:
        print_color(f"\n[INFO] {len(aula[4]['anexos'])} attachment(s) found for class: {aula[1]}")
        folder_path_class_attach = f"{folder_path_class}/Materials"
        if not os.path.exists(folder_path_class_attach):
            os.makedirs(folder_path_class_attach)
            loga(first_folder, "INFO", f"Materials directory created for class: {str(aula[0])}. {aula[1]}")
        
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
                        raise Exception(f"HTTP Error {response.status_code}")
                    
                    anexo_info = response.json()
                    if 'directDownloadUrl' in anexo_info:
                        anexo = requests.get(anexo_info['directDownloadUrl'], timeout=60)
                    elif 'lambdaUrl' in anexo_info:
                        vrum = requests.session()
                        vrum.headers.update(authMart.headers)
                        vrum.headers['token'] = anexo_info.get('token', '')
                        lambda_response = vrum.get(anexo_info['lambdaUrl'], timeout=30)
                        anexo = requests.get(lambda_response.text, timeout=60)
                    else:
                        raise Exception("Missing download URL in API response")
                    
                    if not anexo.content:
                        raise Exception("Empty content received")
                    
                    with open(folder_path_class_attach_file, 'wb') as ann:
                        ann.write(anexo.content)
                    
                    file_size = os.path.getsize(folder_path_class_attach_file)
                    print_color(f"      [OK] Downloaded successfully ({file_size} bytes)")
                    loga(first_folder, "INFO", f"Attachment downloaded: {anexo_nome} ({file_size} bytes)")
                    anexos_baixados += 1
                    sucesso = True
                    break
                except Exception as e:
                    erro_msg = str(e)
                    loga(first_folder, "ERROR", f"Error downloading attachment {anexo_nome}: {erro_msg}")
                    if tentativa == max_tentativas:
                        print_color(f"      [ERROR] FAILED after {max_tentativas} attempts: {erro_msg}")
                        anexos_falhos += 1
                        if os.path.exists(folder_path_class_attach_file):
                            try:
                                os.remove(folder_path_class_attach_file)
                            except:
                                pass
            if sucesso:
                time.sleep(0.5)

        print_color("\n  [SUMMARY] Attachments:")
        print(f"     Downloaded: {anexos_baixados}")
        print(f"     Skipped: {anexos_pulados}")
        if anexos_falhos > 0:
            print_color(f"     Failed: {anexos_falhos}")
        print()

    # 4. Process embedded Google Drive PDFs from HTML description
    if 'desct' in locals() and desct:
        try:
            google_drive_files = extrair_google_drive_urls(desct)
            if google_drive_files:
                print(f"\n{len(google_drive_files)} embedded Google Drive file(s) detected in the HTML content of the class")
                folder_path_class_attach = f"{folder_path_class}/Materials"
                if not os.path.exists(folder_path_class_attach):
                    os.makedirs(folder_path_class_attach)
                
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
                            print_color(f"      [OK] Already exists ({file_size} bytes) - skipping")
                            gdrive_pulados += 1
                            continue
                        else:
                            print_color("      [WARNING] File exists but is empty - re-downloading")
                            os.remove(output_path)
                    
                    print("      [DOWNLOAD] Downloading from Google Drive...")
                    if baixar_google_drive(file_id, download_url, output_path, first_folder):
                        print_color("      [OK] Downloaded successfully")
                        gdrive_baixados += 1
                    else:
                        print_color("      [ERROR] Download failed")
                        gdrive_falhos += 1
                    time.sleep(1)

                print("\n  [SUMMARY] Google Drive Files:")
                print(f"     Downloaded: {gdrive_baixados}")
                print(f"     Skipped: {gdrive_pulados}")
                if gdrive_falhos > 0:
                    print(f"     Failed: {gdrive_falhos}")
                print()
        except Exception as e_gd:
            loga(first_folder, "ERROR", f"Error processing Google Drive content: {e_gd}")

    # 5. Save external/complementary links in links.txt
    if not aula[5]['links'] and 'lesson_json' in locals():
        links = lesson_json.get('complementaryReadings') or lesson_json.get('links') or []
        for link in links:
            aula[5]['links'].append([
                re.sub(r'[<>:"/\\|?*]', '', link.get('articleName') or link.get('name') or 'link').strip(), 
                link.get('articleUrl') or link.get('url')
            ])

    if aula[5]['links']:
        folder_path_class_attach = f"{folder_path_class}/Materials"
        print(f"Saving links found for class in\n\t {folder_path_class_attach}")
        loga(first_folder, "INFO", f"Links detected for class {str(aula[0])} {aula[1]}")
        with open(f"{folder_path_class_attach}/links.txt", "a", encoding="utf-8") as linkz:
            for i in aula[5]['links']:
                linkz.write(f"{i[0]}: {i[1]}\n")
        loga(first_folder, "INFO", "Links saved successfully")


def listacursos(authMart, params):
    """
    Retrieves the list of courses associated with the user's Hotmart account.
    Then navigates the modules, classes, videos, and materials structure to download them.
    """
    check_token_response = authMart.get('https://api-sec-vlc.hotmart.com/security/oauth/check_token', params=params).json()
    
    with open("api_response_debug.json", "w", encoding="utf-8") as f:
        json.dump(check_token_response, f, indent=2, ensure_ascii=False)
    
    produtos = check_token_response.get('resources', [])
    
    if not produtos:
        loga(".", "WARN", "No se encontraron productos en check_token")
        print_color("\nWARNING: Hotmart API did not return courses automatically.")
        
        try:
            from config_cursos import CURSOS_SUBDOMINIOS
            if CURSOS_SUBDOMINIOS:
                print(f"\nFound {len(CURSOS_SUBDOMINIOS)} course(s) in config_cursos.py file")
                for item in CURSOS_SUBDOMINIOS:
                    sub = item.get("subdomain", "").strip() if isinstance(item, dict) else str(item).strip()
                    pid = str(item.get("productId", "")).strip() if isinstance(item, dict) else "1643794"
                    produtos.append({
                        'resource': {'subdomain': sub, 'productId': pid, 'status': 'ACTIVE'},
                        'roles': ['STUDENT']
                    })
        except ImportError:
            print_color("\nWARNING: config_cursos.py file not found.")

        if not produtos:
            subdominios_manuais = []
            while True:
                subdomain = input("Enter the course subdomain (or press Enter to finish): ").strip()
                if not subdomain:
                    if not subdominios_manuais:
                        print_color("WARNING: No course was added. Exiting...")
                        exit(0)
                    break
                subdominios_manuais.append(subdomain)
            
            for subdomain in subdominios_manuais:
                produtos.append({
                    'resource': {'subdomain': subdomain, 'status': 'ACTIVE'},
                    'roles': ['STUDENT']
                })

    cursosValidos = []
    for idx, i in enumerate(produtos):
        try:
            if i.get('resource', {}).get('status') == "ACTIVE" and "STUDENT" in i.get('roles', []):
                dominio = i['resource']['subdomain']
                authMart.headers['origin'] = f'https://{dominio}.club.hotmart.com'
                authMart.headers['referer'] = f'https://{dominio}.club.hotmart.com'
                authMart.headers['club'] = dominio
                
                try:
                    resp_membership = authMart.get(
                        f'https://api-club-course-consumption-gateway-ga.cb.hotmart.com/v1/user/{dominio}/status',
                        headers={'origin': 'https://hotmart.com', 'referer': 'https://hotmart.com/'},
                        timeout=10
                    )
                    if resp_membership.status_code == 200:
                        i["nome"] = dominio
                    else:
                        resp_legacy = authMart.get('https://api-club.hotmart.com/hot-club-api/rest/v3/membership?attach_token=false', timeout=10)
                        if resp_legacy.status_code == 200:
                            i["nome"] = re.sub(r'[<>:"/\\|?*]', '', resp_legacy.json().get('name', dominio)).strip()
                        else:
                            i["nome"] = dominio
                except Exception:
                    i["nome"] = dominio
                cursosValidos.append(i)
        except Exception:
            continue
    
    if not cursosValidos:
        print_color("\n[ERROR] Could not connect or validate membership for the provided subdomains.")
        exit(1)

    wizard_state = 1
    
    while True:
        if wizard_state == 1:
            cursor_opts = [f"{c['nome']} (subdomain: {c['resource']['subdomain']})" for c in cursosValidos]
            opcao = select_item_cli(cursor_opts, title=f"Cursos disponibles ({len(cursosValidos)} encontrado(s))")
            if opcao == -2:
                continue
            
            nmcurso = slugify(cursosValidos[opcao]['nome'])
            first_folder = f'{nmcurso}'
            if not os.path.exists(first_folder):
                os.makedirs(first_folder)
            
            set_debug_log(first_folder)
            debug(f"=== Starting download session for course: {nmcurso} ===")
                
            dominio = cursosValidos[opcao]['resource']['subdomain']
            authMart.headers['origin'] = f'https://{dominio}.club.hotmart.com/'
            authMart.headers['referer'] = f'https://{dominio}.club.hotmart.com/'
            authMart.headers['club'] = dominio

            nav_headers = {
                'origin': 'https://hotmart.com',
                'referer': 'https://hotmart.com/',
                'x-app-name': 'app-club-consumer_v1.357.2_production'
            }
            prod_id = cursosValidos[opcao].get('resource', {}).get('productId') or cursosValidos[opcao].get('productId') or "1643794"
            nav_headers['x-product-id'] = str(prod_id)

            curso = fetch_course_navigation(authMart, dominio, nav_headers)
            
            estrutura = {}
            x = 0
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
                    
                    aulas = [page_order, re.sub(r'[<>:"/\\|?*]', '', page_name).strip(), page_hash, {'videos': []},
                             {'anexos': []}, {'links': []}]
                             
                    medias = i.get('mediasSrc') or i.get('medias') or []
                    for video in medias:
                        v_name = video.get('mediaName') or video.get('name') or 'video'
                        v_code = video.get('mediaCode') or video.get('code') or video.get('id')
                        v_url = video.get('mediaSrcUrl') or video.get('url') or video.get('src')
                        aulas[3]['videos'].append([re.sub(r'[<>:"/\\|?*]', '', v_name).strip(), v_code, v_url])

                    estrutura[mod_order][mod_name_clean].append(aulas)

            with open(first_folder + '/debug.txt', 'a', encoding='utf-8') as debug_file:
                debug_file.write(str(curso['modules']) + '\n\n\n' + str(estrutura))

            loga(first_folder, "INFO", "Dictionary created successfully, exported as debug.txt")
            loga(first_folder, "INFO", f"Total classes in the course {nmcurso}: {str(x)}")
            
            wizard_state = 2

        elif wizard_state == 2:
            download_modes = [
                "Download ONLY 1 specific class/video (Step-by-step)",
                "Download the ENTIRE course",
                "Download a RANGE of classes (From X to Y)"
            ]
            selected_mode_idx = select_item_cli(download_modes, title="DOWNLOAD MODE")
            if selected_mode_idx == -2:
                wizard_state = 1
                continue
                
            modo_descarga = str(selected_mode_idx + 1)
            
            clases_a_descargar = []
            todas_las_clases = []
            for modulo in estrutura:
                for nome_mod in estrutura[modulo]:
                    for aula_item in estrutura[modulo][nome_mod]:
                        todas_las_clases.append((modulo, nome_mod, aula_item))
            
            wizard_state = 3

        elif wizard_state == 3:
            if modo_descarga == "1":
                class_options = [f"[{nome_mod}] {aula_item[1]}" for (modulo, nome_mod, aula_item) in todas_las_clases]
                idx_clase = select_item_cli(class_options, title="Available classes list")
                if idx_clase == -2:
                    wizard_state = 2
                    continue
                _, _, aula_sel = todas_las_clases[idx_clase]
                clases_a_descargar.append(aula_sel[2])
                print_color(f"[INFO] Starting download for class: '{aula_sel[1]}'")
                break
                
            elif modo_descarga == "3":
                total_clases = len(todas_las_clases)
                class_names = [f"[{nome_mod}] {aula_item[1]}" for (modulo, nome_mod, aula_item) in todas_las_clases]
                
                desde = input_number_cli(
                    f"Start downloading from class number? (1 to {total_clases}):",
                    1, total_clases, title="Class Range Selection", options=class_names
                )
                if desde == -2:
                    wizard_state = 2
                    continue
                desde = desde - 1
                
                hasta = input_number_cli(
                    f"Download up to class number? ({desde + 1} to {total_clases}):",
                    desde + 1, total_clases, title="Class Range Selection", options=class_names
                )
                if hasta == -2:
                    wizard_state = 2
                    continue
                hasta = hasta - 1
                
                for i in range(desde, hasta + 1):
                    _, _, aula_sel = todas_las_clases[i]
                    clases_a_descargar.append(aula_sel[2])
                break
            else:
                break

    # Loop through course components and download assets
    for moduloOrder in estrutura:
        for modName in estrutura[moduloOrder]:
            
            # Check if directory should be skipped in selective download
            if (modo_descarga == "1" or modo_descarga == "3"):
                clases_filtradas = [a for a in estrutura[moduloOrder][modName] if a[2] in clases_a_descargar]
                if not clases_filtradas:
                    continue
            
            folder_path = f'{first_folder}/{slugify(str(moduloOrder))}_{slugify(modName)}'
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                loga(first_folder, "INFO", f"Created module directory: {str(moduloOrder)}.{modName}")

            for aula in estrutura[moduloOrder][modName]:
                if (modo_descarga == "1" or modo_descarga == "3") and aula[2] not in clases_a_descargar:
                    continue

                folder_path_class = f"{folder_path}/{slugify(str(aula[0]))}.{slugify(aula[1])}"
                print_color(f"[INFO] Verifying class: {folder_path_class}")
                if not os.path.exists(folder_path_class):
                    os.makedirs(folder_path_class)
                    loga(first_folder, "INFO", f"Created class directory: {slugify(str(aula[0]))}.{slugify(aula[1])}")

                download_class_assets(aula, modName, folder_path_class, first_folder, authMart, nav_headers, dominio)


if __name__ == '__main__':
    listacursos(*autenticacao())
