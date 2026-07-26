import os
import glob
from utils import slugify

def rename_to_descriptive_format(course_subdomain="universo-hot-jamin"):
    target_dir = course_subdomain
    if not os.path.exists(target_dir):
        print(f"Error: La carpeta de descargas '{target_dir}' no existe.")
        return

    print(f"Buscando videos con nombres antiguos en: {os.path.abspath(target_dir)}")
    print("=" * 70)
    
    renamed_count = 0

    # Walk through modules
    modules = [d for d in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, d))]
    for mod in modules:
        # Extraer orden del módulo y nombre
        # mod suele ser "1_modulo-name"
        mod_parts = mod.split("_", 1)
        mod_name = mod_parts[1] if len(mod_parts) > 1 else mod
        
        mod_path = os.path.join(target_dir, mod)
        classes = [c for c in os.listdir(mod_path) if os.path.isdir(os.path.join(mod_path, c))]
        
        for cl in classes:
            cl_path = os.path.join(mod_path, cl)
            # cl suele ser "1.clase-name" o similar
            cl_parts = cl.split(".", 1)
            if len(cl_parts) < 2:
                continue
            
            lesson_order = cl_parts[0]
            lesson_name = cl_parts[1]
            
            # Formato descriptivo objetivo: {lesson_order}.{lesson_name}.mp4
            descriptive_name = f"{slugify(lesson_order)}.{slugify(lesson_name)}.mp4"
            descriptive_path = os.path.join(cl_path, descriptive_name)
            
            if os.path.exists(descriptive_path) and os.path.getsize(descriptive_path) > 0:
                # Ya tiene el nombre descriptivo correcto, buscar otros duplicados antiguos y eliminarlos
                for f in glob.glob(os.path.join(cl_path, "*.mp4")):
                    if os.path.basename(f) != descriptive_name:
                        print(f"[LIMPIEZA] Eliminando duplicado antiguo: {os.path.basename(f)}")
                        try:
                            os.remove(f)
                        except Exception as e:
                            print(f"Error removiendo duplicado: {e}")
                continue

            # Buscar archivos .mp4 que no coincidan con el nombre correcto
            mp4_files = glob.glob(os.path.join(cl_path, "*.mp4"))
            for f in mp4_files:
                filename = os.path.basename(f)
                if filename != descriptive_name:
                    print(f"[RENOMBRAR] {filename} -> {descriptive_name}")
                    try:
                        os.rename(f, descriptive_path)
                        renamed_count += 1
                    except Exception as e:
                        print(f"Error renombrando {filename}: {e}")

    print("=" * 70)
    print(f"FINALIZADO: Se renombraron/normalizaron {renamed_count} videos al formato descriptivo.")

if __name__ == "__main__":
    rename_to_descriptive_format()
