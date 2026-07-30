import os
import sys
import json
import shutil

def clean_empty_directories(path, base_limit):
    """Recursively removes empty directories up to the base limit."""
    if not os.path.exists(path) or not os.path.isdir(path):
        return
    if os.path.abspath(path) == os.path.abspath(base_limit):
        return
        
    try:
        if not os.listdir(path):
            os.rmdir(path)
            print(f"  [CLEANUP] Removed empty directory: {os.path.relpath(path, base_limit)}")
            # Try parent directory
            parent = os.path.dirname(path)
            clean_empty_directories(parent, base_limit)
    except Exception as e:
        print(f"  [WARNING] Failed to remove directory {path}: {e}")

def run_rename():
    from dotenv import load_dotenv
    load_dotenv()
    
    subdomain = os.getenv("SUBDOMAIN", "").strip()
    download_dir = os.getenv("DOWNLOAD_DIR", "").strip()

    if not subdomain:
        print("[ERROR] SUBDOMAIN must be set in .env")
        sys.exit(1)

    first_folder = subdomain if subdomain.startswith("universo-hot-") else f"universo-hot-{subdomain}"
    if download_dir:
        first_folder = os.path.join(download_dir, first_folder)

    if not os.path.exists(first_folder):
        print(f"[ERROR] Target folder '{first_folder}' does not exist.")
        sys.exit(1)

    actions_path = os.path.join(first_folder, "sync_actions.json")
    snapshot_path = os.path.join(first_folder, "download_snapshot.json")

    if not os.path.exists(actions_path):
        print("[ERROR] No sync action plan found. Please run 'python sync_checker.py' first.")
        sys.exit(1)

    try:
        with open(actions_path, "r", encoding="utf-8") as f:
            actions = json.load(f)
    except Exception as e:
        print(f"[ERROR] Could not load action plan: {e}")
        sys.exit(1)

    moves = actions.get("moves", [])
    if not moves:
        print("[INFO] No pending move actions to execute.")
        # Cleanup
        os.remove(actions_path)
        sys.exit(0)

    # Load snapshot to update it
    snapshot = {}
    if os.path.exists(snapshot_path):
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except Exception:
            pass

    print(f"[INFO] Commencing reorganization of {len(moves)} items...")
    print("=" * 80)

    successful_moves = 0
    directories_to_clean = set()

    for idx, move in enumerate(moves, 1):
        curr_rel = move["current_path"]
        exp_rel = move["expected_path"]
        lesson_id = move["lesson_id"]
        name = move["name"]

        curr_full = os.path.join(first_folder, curr_rel)
        exp_full = os.path.join(first_folder, exp_rel)

        if not os.path.exists(curr_full):
            print(f"  [SKIP] File not found: {curr_rel}")
            continue

        curr_dir = os.path.dirname(curr_full)
        exp_dir = os.path.dirname(exp_full)

        # Create expected directory structure
        if not os.path.exists(exp_dir):
            os.makedirs(exp_dir)

        print(f"  [{idx}/{len(moves)}] Moving files for: '{name}'")
        
        # Move all contents of the lesson folder (video, HTML description, Materials folder, etc.)
        try:
            for item in os.listdir(curr_dir):
                src_item = os.path.join(curr_dir, item)
                dst_item = os.path.join(exp_dir, item)
                
                if os.path.isdir(src_item) and item == "Materials":
                    # Merge materials folders if destination already exists
                    if os.path.exists(dst_item):
                        for file_in_mat in os.listdir(src_item):
                            shutil.move(os.path.join(src_item, file_in_mat), os.path.join(dst_item, file_in_mat))
                        os.rmdir(src_item)
                    else:
                        shutil.move(src_item, dst_item)
                else:
                    shutil.move(src_item, dst_item)

            # Update snapshot
            if os.path.exists(exp_full):
                snapshot[lesson_id] = {
                    "lesson_name": name,
                    "file_size": os.path.getsize(exp_full),
                    "relative_path": exp_rel
                }
            
            successful_moves += 1
            directories_to_clean.add(curr_dir)
        except Exception as e:
            print(f"    [ERROR] Failed to move '{name}': {e}")

    # Save updated snapshot
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    # Clean up empty parent directories
    print("\nCleaning up empty directories...")
    print("-" * 50)
    for d in directories_to_clean:
        clean_empty_directories(d, first_folder)

    # Delete actions plan file
    try:
        os.remove(actions_path)
    except Exception:
        pass

    print("=" * 80)
    print(f"[SUCCESS] Reorganization complete! {successful_moves} of {len(moves)} items updated.")

if __name__ == "__main__":
    run_rename()
