import re
import os
import requests
from bs4 import BeautifulSoup
from logger import loga

def extrair_google_drive_urls(html_content):
    """
    Scans class HTML content to detect embedded Google Drive files (iframes, views).
    Returns list of tuples: (file_id, url_preview, url_download)
    """
    if not html_content:
        return []
    
    urls = []
    pattern = r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)'
    matches = re.findall(pattern, html_content)
    
    for file_id in matches:
        preview_url = f"https://drive.google.com/file/d/{file_id}/preview"
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        urls.append((file_id, preview_url, download_url))
    
    return urls

def baixar_google_drive(file_id, download_url, output_path, first_folder):
    """
    Downloads a public/embedded Google Drive file, resolving interstitial scans for large files.
    Returns True if successfully downloaded and non-empty.
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
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                loga(first_folder, "INFO", f"Download finished: {output_path} ({os.path.getsize(output_path)} bytes)")
                return True
            else:
                loga(first_folder, "ERROR", f"Empty or missing Google Drive file: {output_path}")
                return False
        else:
            loga(first_folder, "ERROR", f"Failed Google Drive download HTTP status: {response.status_code}")
            return False
            
    except Exception as e:
        loga(first_folder, "ERROR", f"Exception downloading Google Drive {file_id}: {str(e)}")
        return False
