import re
import os
import requests
from bs4 import BeautifulSoup
from logger import loga

def extrair_google_drive_urls(html_content):
    """
    Scans class HTML content to detect embedded Google Drive files, sheets, docs, or presentations.
    Returns list of tuples: (file_id, url_preview, url_download, type_hint)
    """
    if not html_content:
        return []
    
    urls = []
    # Match various Google Drive item structures
    patterns = [
        (r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', 'file'),
        (r'drive\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)', 'spreadsheet'),
        (r'drive\.google\.com/document/d/([a-zA-Z0-9_-]+)', 'document'),
        (r'drive\.google\.com/presentation/d/([a-zA-Z0-9_-]+)', 'presentation')
    ]
    
    seen_ids = set()
    for pattern, type_hint in patterns:
        matches = re.findall(pattern, html_content)
        for file_id in matches:
            if file_id not in seen_ids:
                preview_url = f"https://drive.google.com/open?id={file_id}"
                if type_hint == 'spreadsheet':
                    download_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
                elif type_hint == 'document':
                    download_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
                elif type_hint == 'presentation':
                    download_url = f"https://docs.google.com/presentation/d/{file_id}/export?format=pptx"
                else:
                    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                
                urls.append((file_id, preview_url, download_url, type_hint))
                seen_ids.add(file_id)
    
    return urls

def baixar_google_drive(file_id, download_url, output_path_base, first_folder):
    """
    Downloads a public/embedded Google Drive file, resolving interstitial scans for large files.
    Determines correct extension dynamically from Content-Type headers.
    Returns (success_boolean, final_output_path)
    """
    try:
        loga(first_folder, "INFO", f"Starting Google Drive download: {file_id}")
        session = requests.Session()
        response = session.get(download_url, stream=True)
        
        # Resolve Google anti-virus warning screen if present
        if 'confirm' in response.text or 'virus scan warning' in response.text.lower():
            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if 'export=download' in href and 'confirm' in href:
                    download_url = 'https://drive.google.com' + href
                    response = session.get(download_url, stream=True)
                    break
        
        if response.status_code == 200:
            # Map content type to extension
            content_type = response.headers.get('Content-Type', '').lower()
            ext = ".pdf" # default fallback
            if 'spreadsheet' in content_type or 'excel' in content_type or 'openxmlformats-officedocument.spreadsheetml' in content_type:
                ext = ".xlsx"
            elif 'document' in content_type or 'word' in content_type or 'openxmlformats-officedocument.wordprocessingml' in content_type:
                ext = ".docx"
            elif 'presentation' in content_type or 'powerpoint' in content_type or 'openxmlformats-officedocument.presentationml' in content_type:
                ext = ".pptx"
            elif 'zip' in content_type:
                ext = ".zip"
            elif 'image/png' in content_type:
                ext = ".png"
            elif 'image/jpeg' in content_type:
                ext = ".jpg"

            output_path = f"{output_path_base}{ext}"

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                loga(first_folder, "INFO", f"Download finished: {output_path} ({os.path.getsize(output_path)} bytes)")
                return True, output_path
            else:
                loga(first_folder, "ERROR", f"Empty or missing Google Drive file: {output_path}")
                return False, None
        else:
            loga(first_folder, "ERROR", f"Failed Google Drive download HTTP status: {response.status_code}")
            return False, None
            
    except Exception as e:
        loga(first_folder, "ERROR", f"Exception downloading Google Drive {file_id}: {str(e)}")
        return False, None
