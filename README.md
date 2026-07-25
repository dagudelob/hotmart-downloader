# Hotmart Course Downloader

A robust Python script to download and backup complete course materials from your purchased Hotmart products. It automatically downloads videos, attachments, complementary links, class descriptions, and embedded Google Drive PDFs.

This script was fully tested and verified working as of **July 2026**.

---

## What This Tool Does

* **Native Hotmart Videos (HLS)**: Resolves CDN token validation, decodes signed master playlist manifests, downloads HLS segments, and merges them using `ffmpeg`.
* **Dynamic Naming**: Saves videos using a clean structure: `{module_number}.{class_number}.mp4` (e.g., `9.1.mp4`).
* **Flexible Download Modes**:
  1. Download **ONLY 1 specific class/video** (step-by-step).
  2. Download **the ENTIRE course**.
  3. Download **a RANGE of classes** (e.g., from class 13 to class 30).
* **Vimeo & YouTube Videos**: Automatically detects and downloads external video hosts embedded inside classes.
* **Class Descriptions**: Saves the class descriptions as `.html` files.
* **Normal Attachments**: Downloads files attached directly to lessons (PDFs, ZIPs, images, etc.).
* **Embedded Google Drive PDFs**: Detects and downloads PDFs embedded inside iframe previewers.
* **Detailed Debug Logs**: Generates a local `debug.log` within the course folder to inspect HTTP request/response payloads if issues arise.

---

## Prerequisites

Ensure you have the following installed on your system:

1. **Python 3.10+** (Recommended).
2. **FFmpeg**: Must be installed and added to your system's `PATH`.
   * *Verify by running:* `ffmpeg -version` in your terminal.
3. **yt-dlp**: Required for handling external embeds.

---

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/dagudelob/hotmart-downloader.git
   cd hotmart-downloader
   ```

2. **Install dependencies**:
   Using `uv` (recommended for fast execution) or `pip`:
   ```bash
   # Using uv:
   uv pip install -r requirements.txt
   
   # Or using standard pip:
   pip install -r requirements.txt
   ```

3. **Configure your course subdomains**:
   Hotmart's API structure changed in 2026; the `check_token` endpoint often returns an empty `resources: []` list. To work around this, you must manually define the subdomain(s) of your course in `config_cursos.py`:
   ```python
   # config_cursos.py
   CURSOS_SUBDOMINIOS = ["universo-hot-jamin"]
   ```

   **How to find the subdomain**:
   1. Log in to [Hotmart My Purchases](https://sun.hotmart.com/minhas-compras).
   2. Click on your course to access the player area.
   3. Look at your browser's address bar. The URL looks like this: `https://hotmart.com/en/club/universo-hot-jamin/products/...`
   4. The subdomain is the name after `/club/` and before `/products/` (in this case: `universo-hot-jamin`).

---

## Authentication: How to Get the Bearer Token 🔑

Hotmart uses a strict authentication workflow. To bypass login blocks, you should provide a **JWT Authorization Token** inside a `.env` file.

### How to extract your Token:
1. Open your course in the browser (Google Chrome, Firefox, etc.).
2. Press **F12** (or right-click and choose **Inspect**) to open the Developer Tools.
3. Go to the **Network** (Red) tab.
4. Refresh the page (`F5`).
5. In the filter box, type `/v1/navigation` or `/v1/lessons`.
6. Click on any of the filtered requests and look for the **Headers** (Cabeceras) tab.
7. Under **Request Headers**, find the `authorization` header. It will look like this:
   `Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6...`
8. Copy the long string value of the token (exclude the word `Bearer `).

### Create your `.env` file:
In the root directory of the repository, create a file named `.env` and add the following content:
```env
email: "your-email@example.com"
password: "your-hotmart-password"
token: "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJUR1Qt..."
```

---

## How to Run

Execute the main script:
```bash
# Using uv (recommended):
uv run python hotmark.py

# Using standard python:
python hotmark.py
```

### Script Execution Flow:
1. The script will automatically load the JWT token from the `.env` file.
2. Select your course from the list.
3. Choose the **Download Mode**:
   * Select `1` to download a single class.
   * Select `2` to download everything.
   * Select `3` to input a custom range (e.g., from class `13` to `30`).
4. Sit back and watch the progress bars as it downloads your content!

---

## Warnings & Disclaimer

* **Personal Backups Only**: Use this script solely to back up content you have legally purchased. Sharing or distributing downloaded course files is illegal.
* **Account Safety**: Avoid making hundreds of consecutive downloads in a short period to prevent triggers on Hotmart's rate-limiting firewalls. Downloading in smaller custom ranges (Option 3) is the safest practice.
* **Project Status**: Educational project. Use at your own responsibility.
