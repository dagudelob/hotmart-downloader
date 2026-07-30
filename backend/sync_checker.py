import os
import sys
import glob
import json
from dotenv import load_dotenv

# Ensure we can import from local files
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import slugify
from hotmark import fetch_course_navigation

load_dotenv()

def bootstrap_snapshot(first_folder, course_structure, snapshot_path):
    """
    Initializes the snapshot file mapping lesson_id to file_size and path
    by scanning the disk for matching files.
    """
    print("[INFO] Bootstrapping local download snapshot from existing disk files...")
    snapshot = {}
    
    # Cache all .mp4 files on disk with their sizes
    disk_files = {}
    for root, dirs, files in os.walk(first_folder):
        for f in files:
            if f.endswith(".mp4"):
                path = os.path.join(root, f)
                size = os.path.getsize(path)
                if size > 0:
                    disk_files[path] = size

    # Attempt to match API structure with disk files
    for mod_order in sorted(course_structure.keys()):
        for mod_name, lessons in course_structure[mod_order].items():
            mod_slug = f"{slugify(str(mod_order))}_{slugify(mod_name)}"
            for lesson in lessons:
                lesson_order = lesson[0]
                lesson_name = lesson[1]
                lesson_id = lesson[2]
                
                class_slug = f"{slugify(str(lesson_order))}.{slugify(lesson_name)}"
                expected_dir = os.path.join(first_folder, mod_slug, class_slug)
                
                # Look for direct match
                found_path = None
                if os.path.exists(expected_dir):
                    mp4s = glob.glob(os.path.join(expected_dir, "*.mp4"))
                    if mp4s:
                        found_path = mp4s[0]
                
                # Check candidate names if direct match wasn't found in directory
                if not found_path:
                    candidates = [
                        os.path.join(expected_dir, f"{slugify(str(lesson_order))}.{slugify(lesson_name)}.mp4"),
                        os.path.join(expected_dir, f"{slugify(mod_name)}.{slugify(str(lesson_order))}.mp4"),
                        os.path.join(expected_dir, f"aula-{slugify(str(lesson_order))}.mp4")
                    ]
                    for cand in candidates:
                        if os.path.exists(cand) and os.path.getsize(cand) > 0:
                            found_path = cand
                            break

                if found_path:
                    size = os.path.getsize(found_path)
                    snapshot[str(lesson_id)] = {
                        "lesson_name": lesson_name,
                        "file_size": size,
                        "relative_path": os.path.relpath(found_path, first_folder)
                    }

    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    print(f"[SUCCESS] Snapshot bootstrapped with {len(snapshot)} items.")
    return snapshot

def check_sync():
    token = os.getenv("TOKEN", "").strip()
    if token.startswith("TOKEN="):
        token = token.split("=", 1)[1].strip().strip("\"'")
    if token.startswith("Bearer "):
        token = token.replace("Bearer ", "").strip()
        
    subdomain = os.getenv("SUBDOMAIN", "").strip()
    product_id = os.getenv("PRODUCT_ID", "").strip()
    download_dir = os.getenv("DOWNLOAD_DIR", "").strip()

    if not token or not subdomain:
        print("[ERROR] TOKEN and SUBDOMAIN must be set in .env")
        sys.exit(1)

    first_folder = subdomain if subdomain.startswith("universo-hot-") else f"universo-hot-{subdomain}"
    if download_dir:
        first_folder = os.path.join(download_dir, first_folder)

    if not os.path.exists(first_folder):
        print(f"[ERROR] Target download folder '{first_folder}' does not exist.")
        sys.exit(1)

    snapshot_path = os.path.join(first_folder, "download_snapshot.json")
    actions_path = os.path.join(first_folder, "sync_actions.json")

    # Fetch latest structure from API
    import requests
    auth_session = requests.Session()
    auth_session.headers.update({
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "authorization": f"Bearer {token}",
        "origin": f"https://{subdomain}.club.hotmart.com",
        "referer": f"https://{subdomain}.club.hotmart.com/",
        "club": subdomain
    })

    nav_headers = {
        "authority": "api-club-course-consumption-gateway-ga.cb.hotmart.com",
        "accept": "application/json, text/plain, */*",
        "origin": f"https://{subdomain}.club.hotmart.com",
        "referer": f"https://{subdomain}.club.hotmart.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "authorization": f"Bearer {token}",
        "x-product-id": product_id
    }

    print("[INFO] Fetching latest course structure from Hotmart API...")
    try:
        curso = fetch_course_navigation(auth_session, subdomain, nav_headers)
    except Exception as e:
        print(f"[ERROR] API fetch failed: {e}")
        sys.exit(1)

    # Parse newest API structure
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
            course_structure[mod_order][mod_name].append([
                page_order, page_name, page_hash, {"videos": []}, {"anexos": []}, {"links": []},
                {"has_video_meta": bool(page.get('hasVideo')), "has_attachment_meta": bool(page.get('hasAttachment'))}
            ])

    # Load or bootstrap snapshot
    if os.path.exists(snapshot_path):
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except Exception:
            snapshot = bootstrap_snapshot(first_folder, course_structure, snapshot_path)
    else:
        snapshot = bootstrap_snapshot(first_folder, course_structure, snapshot_path)

    # Scan current filesystem for all available MP4 files and sizes
    print("[INFO] Scanning filesystem to locate files by size...")
    disk_files_by_size = {}
    for root, dirs, files in os.walk(first_folder):
        for f in files:
            if f.endswith(".mp4"):
                p = os.path.join(root, f)
                sz = os.path.getsize(p)
                if sz > 0:
                    if sz not in disk_files_by_size:
                        disk_files_by_size[sz] = []
                    disk_files_by_size[sz].append(p)

    actions = {
        "moves": [],       # Files that need to be renamed/moved
        "missing": [],     # Not found anywhere
        "ok": []           # Correctly positioned
    }

    print("\nAuditing files...")
    print("=" * 80)

    for mod_order in sorted(course_structure.keys()):
        for mod_name, lessons in course_structure[mod_order].items():
            mod_slug = f"{slugify(str(mod_order))}_{slugify(mod_name)}"
            
            for lesson in lessons:
                lesson_order = lesson[0]
                lesson_name = lesson[1]
                lesson_id = str(lesson[2])
                
                class_slug = f"{slugify(str(lesson_order))}.{slugify(lesson_name)}"
                expected_filename = f"{slugify(str(lesson_order))}.{slugify(lesson_name)}.mp4"
                expected_file_path = os.path.join(first_folder, mod_slug, class_slug, expected_filename)
                
                # 1. Check if file is already correctly placed
                if os.path.exists(expected_file_path) and os.path.getsize(expected_file_path) > 0:
                    # Update snapshot size/path dynamically
                    size = os.path.getsize(expected_file_path)
                    snapshot[lesson_id] = {
                        "lesson_name": lesson_name,
                        "file_size": size,
                        "relative_path": os.path.relpath(expected_file_path, first_folder)
                    }
                    actions["ok"].append({
                        "lesson_id": lesson_id,
                        "name": lesson_name,
                        "path": os.path.relpath(expected_file_path, first_folder)
                    })
                    continue

                # 2. Check if it was moved/renamed
                found_match = False
                
                # Attempt to find it by ID lookup in snapshot
                if lesson_id in snapshot:
                    recorded_size = snapshot[lesson_id]["file_size"]
                    # Look up by file size on disk
                    if recorded_size in disk_files_by_size:
                        candidates = disk_files_by_size[recorded_size]
                        if candidates:
                            # Found a match!
                            actual_path = candidates[0]
                            # Record move action
                            actions["moves"].append({
                                "lesson_id": lesson_id,
                                "name": lesson_name,
                                "current_path": os.path.relpath(actual_path, first_folder),
                                "expected_path": os.path.relpath(expected_file_path, first_folder)
                            })
                            found_match = True
                            
                # Fallback: Match by name slug if not matched by size (handles newly downloaded files with no size history)
                if not found_match:
                    for sz, paths in disk_files_by_size.items():
                        for p in paths:
                            if expected_filename in p or slugify(lesson_name) in slugify(os.path.basename(p)):
                                actions["moves"].append({
                                    "lesson_id": lesson_id,
                                    "name": lesson_name,
                                    "current_path": os.path.relpath(p, first_folder),
                                    "expected_path": os.path.relpath(expected_file_path, first_folder)
                                })
                                found_match = True
                                break
                        if found_match:
                            break

                if not found_match:
                    actions["missing"].append({
                        "lesson_id": lesson_id,
                        "name": lesson_name,
                        "expected_path": os.path.relpath(expected_file_path, first_folder)
                    })

    # Save active snapshot updates
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    # Save action plans
    with open(actions_path, "w", encoding="utf-8") as f:
        json.dump(actions, f, indent=2, ensure_ascii=False)

    # Report results
    print("=" * 80)
    print("SYNC REPORT SUMMARY:")
    print(f"  OK (Correct Position)  : {len(actions['ok'])}")
    print(f"  To Move / Reorganize   : {len(actions['moves'])}")
    print(f"  Missing (To Download)  : {len(actions['missing'])}")
    print("=" * 80)

    if actions["moves"]:
        print("\nPROPOSED MOVES:")
        for move in actions["moves"][:15]:
            print(f"  • [MOVE] '{move['name']}'")
            print(f"    From: {move['current_path']}")
            print(f"    To  : {move['expected_path']}")
        if len(actions["moves"]) > 15:
            print(f"  ... and {len(actions['moves']) - 15} more move actions.")
        print(f"\n[INFO] Action plan saved to: {actions_path}")
        print("[ACTION REQUIRED] Execute 'python sync_rename.py' to apply these changes.")
    else:
        print("\n[SUCCESS] No organizational changes detected. Files are perfectly in sync with Hotmart web layout!")

if __name__ == "__main__":
    check_sync()
