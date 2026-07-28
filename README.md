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
   You can set up the project environment using one of the following two options (using **`uv`** is highly recommended for speed and convenience):

   ### Option A: Using `uv` (Recommended 🚀)
   If you have [uv](https://github.com/astral-sh/uv) installed, it will automatically handle virtual environment creation and package installation instantly:
   ```bash
   # Run the script directly with uv (it will handle dependencies and virtualenv automatically)
   uv run python hotmark.py
   ```
   *Alternatively, to sync dependencies inside uv manually:*
   ```bash
   uv pip install -r requirements.txt
   ```

   ### Option B: Using a Traditional Virtual Environment (`venv`)
   If you prefer using standard Python built-in tools:
   ```bash
   # Create a virtual environment
   python -m venv .venv

   # Activate it (Windows PowerShell)
   .venv\Scripts\Activate.ps1

   # Activate it (macOS/Linux)
   source .venv/bin/activate

   # Install the requirements
   pip install -r requirements.txt
   ```


3. **Configure your course subdomains**:
   Hotmart's API structure changed in 2026; the `check_token` endpoint often returns an empty `resources: []` list. To work around this, you must manually define the subdomain(s) of your course in `config_cursos.py`:
   ```python
   # config_cursos.py
   CURSOS_SUBDOMINIOS = ["your-course-subdomain"]
   ```

   **How to find the subdomain**:
   1. Log in to [Hotmart My Purchases](https://sun.hotmart.com/minhas-compras).
   2. Click on your course to access the player area.
   3. Look at your browser's address bar. The URL looks like this: `https://hotmart.com/en/club/your-course-subdomain/products/...`
   4. The subdomain is the name after `/club/` and before `/products/` (e.g.: `your-course-subdomain`).

---

## Authentication: How to Get the Bearer Token 🔑

Hotmart uses a strict authentication workflow. To access your courses, you must provide a **Bearer Authorization Token**. 

You can extract your token in seconds using either of the two methods below.

---

### Method 1: Automatic Configuration Block Extraction (Recommended & Fastest 🚀)

This method automatically extracts your **Bearer Token**, **Subdomain**, and **Product ID** all at once and formats them into a ready-to-use configuration block.

1. **Log in to your Course**:
   Open Google Chrome, Mozilla Firefox, or Microsoft Edge, and navigate to your purchased course player area.
2. **Open Developer Tools**:
   Press **`F12`** (or right-click anywhere on the page and select **Inspect**).
3. **Go to the Console Tab**:
   Click on the **Console** tab at the top of the Developer Tools panel.
   
   > [!IMPORTANT]
   > **Browser Paste Protection Security Warning**:
   > Modern browsers block pasting code into the Console by default to protect you from attacks. If you cannot paste:
   > * **Chrome / Edge**: Type `allow pasting` in the console input, press **`Enter`**, and then try to paste again.
   > * **Firefox**: Type `allow pasting` in the console input, press **`Enter`**, and then try to paste again.

4. **Run the Extraction Script**:
   Copy the contents of `Get_Token.js` (or copy the code block below), paste it into the Console, and press **`Enter`**:

   ```javascript
   (function () {
       let tokenFound = null;
       for (let i = 0; i < localStorage.length; i++) {
           const value = localStorage.getItem(localStorage.key(i));
           if (value && value.includes("eyJ")) {
               const match = value.match(/eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*/);
               if (match) { tokenFound = match[0]; break; }
           }
       }
       if (!tokenFound) {
           for (let i = 0; i < sessionStorage.length; i++) {
               const value = sessionStorage.getItem(sessionStorage.key(i));
               if (value && value.includes("eyJ")) {
                   const match = value.match(/eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*/);
                   if (match) { tokenFound = match[0]; break; }
               }
           }
       }

       if (!tokenFound) {
           alert("Token not found. Make sure you are logged into your Hotmart course player page.");
           return;
       }

       let subdomain = "";
       const hostname = window.location.hostname;
       const pathname = window.location.pathname;

       if (hostname.includes(".club.hotmart.com")) {
           subdomain = hostname.split(".")[0];
       } else {
           const clubMatch = pathname.match(/\/club\/([^/]+)/);
           if (clubMatch) {
               subdomain = clubMatch[1];
           }
       }

       let productId = "";
       const prodMatch = pathname.match(/\/(?:products|player)\/([0-9]+)/);
       if (prodMatch) {
           productId = prodMatch[1];
       } else {
           for (let i = 0; i < localStorage.length; i++) {
               const key = localStorage.key(i);
               if (key && (key.includes("productId") || key.includes("product-id"))) {
                   productId = localStorage.getItem(key);
                   break;
               }
           }
       }

       const output = `TOKEN="${tokenFound}"\nSUBDOMAIN="${subdomain}"\nPRODUCT_ID="${productId}"`;
       copy(output);
       alert("Token configuration successfully copied to clipboard!\n\nPaste it directly inside the 'Bearer Token or SSO Token' box in the Web app.");
   })();
   ```

5. **Paste into the Web App**:
   A pop-up will confirm that the configuration was copied. Go to your local Web application (**`http://localhost:8000`**), paste the entire multi-line block into the **"Bearer Token or SSO Token"** textarea, and click **"Load Course and Connect"**. The app will automatically parse all variables and configure your `.env` file!

---

### Method 2: Manual Extraction via Network Tab (F12)

If you prefer to find the token manually:

1. Open your course in the browser.
2. Press **`F12`** to open Developer Tools and select the **Network** tab.
3. Refresh the page (`F5`) or click on any lesson.
4. Filter by typing `api-club.hotmart.com` or `navigation` in the search bar.
5. Click on any matching network request and select the **Headers** tab.
6. Under **Request Headers**, locate the `authorization` header:
   `Authorization: Bearer eyJ...`
7. Copy the entire token string.

---

### `.env` File Configuration

When you paste your token into the CLI, it automatically creates or updates your `.env` file for future runs. You can also edit `.env` manually:

```env
TOKEN="ey....."
DOWNLOAD_DIR="/mnt/c/Users/user/code/hotmart"
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
