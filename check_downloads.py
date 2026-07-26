import os
import glob
from utils import slugify

def check_missing_downloads(course_subdomain="universo-hot-jamin"):
    target_dir = course_subdomain
    if not os.path.exists(target_dir):
        print(f"Error: La carpeta de descargas '{target_dir}' no existe.")
        return

    print(f"Auditoría de Descargas en: {os.path.abspath(target_dir)}")
    print("=" * 70)
    
    total_folders = 0
    missing_videos = 0
    empty_videos = 0
    ok_videos = 0

    # Walk through modules
    modules = [d for d in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, d))]
    for mod in modules:
        mod_path = os.path.join(target_dir, mod)
        classes = [c for c in os.listdir(mod_path) if os.path.isdir(os.path.join(mod_path, c))]
        
        for cl in classes:
            total_folders += 1
            cl_path = os.path.join(mod_path, cl)
            
            # Find any .mp4 files inside the class folder
            mp4_files = glob.glob(os.path.join(cl_path, "*.mp4"))
            
            if not mp4_files:
                print(f"[FALTA VIDEO] Modulo: {mod} | Clase: {cl}")
                missing_videos += 1
            else:
                for f in mp4_files:
                    size = os.path.getsize(f)
                    if size == 0:
                        print(f"[VIDEO VACÍO] Modulo: {mod} | Clase: {cl} ({f})")
                        empty_videos += 1
                    else:
                        ok_videos += 1

    print("=" * 70)
    print("RESUMEN DE AUDITORÍA:")
    print(f"  Carpetas de clases analizadas : {total_folders}")
    print(f"  Clases con video OK            : {ok_videos}")
    print(f"  Clases sin video (.mp4)        : {missing_videos}")
    print(f"  Clases con video corrupto (0B) : {empty_videos}")
    if missing_videos == 0 and empty_videos == 0:
        print("\n¡Todo descargado con éxito! 🎉")
    else:
        print("\nSe requiere re-descargar los elementos indicados arriba.")

if __name__ == "__main__":
    check_missing_downloads()
