import ast
import os
import re
import unicodedata
import sys
from urllib.parse import urlparse

# Forzar salida en utf-8 para evitar errores de codificación en consolas Windows
sys.stdout.reconfigure(encoding='utf-8')

def slugify(value):
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

def main():
    if not os.path.exists('universo-hot-jamin/debug.txt'):
        print("No se encontró el archivo de estructura debug.txt")
        return

    with open('universo-hot-jamin/debug.txt', 'r', encoding='utf-8') as f:
        modules = ast.literal_eval(f.read().split('\n\n\n')[0])

    class_counter = 1
    downloaded = 0
    missing = []
    
    # Escanear qué archivos existen físicamente en la carpeta
    existing_videos = set()
    for root, dirs, files in os.walk('universo-hot-jamin'):
        for file in files:
            if file.endswith('.mp4'):
                # Guardamos la ruta relativa limpia usando barras normales
                rel_path = os.path.relpath(os.path.join(root, file), 'universo-hot-jamin').replace('\\', '/')
                existing_videos.add(rel_path)

    for mod_idx, mod in enumerate(modules, start=1):
        mod_name_clean = slugify(mod['name'])
        
        # Encontrar cómo se nombró la carpeta del módulo físicamente
        mod_dir_name = None
        if os.path.exists('universo-hot-jamin'):
            for name in os.listdir('universo-hot-jamin'):
                if os.path.isdir(os.path.join('universo-hot-jamin', name)):
                    if name.startswith(f"{mod_idx}_") or name == mod_name_clean:
                        mod_dir_name = name
                        break
        
        if not mod_dir_name:
            mod_dir_name = f"{mod_idx}_{mod_name_clean}"

        for page in mod.get('pages', []):
            if page.get('hasPlayerMedia') and page.get('firstMediaType') == 'VIDEO':
                name_clean = slugify(page['name'])
                
                # Nombre esperado de la carpeta de la clase
                expected_class_dir = f"{slugify(str(class_counter))}.{name_clean}"
                
                # Comprobar si existe el archivo aula-1.mp4
                exists = False
                test_path = f"{mod_dir_name}/{expected_class_dir}/aula-1.mp4"
                if test_path in existing_videos:
                    exists = True
                else:
                    # Búsqueda flexible por si cambia ligeramente el slug
                    for ev in existing_videos:
                        if ev.startswith(f"{mod_dir_name}/") and (f"/{expected_class_dir}/" in f"/{ev}" or f"/{slugify(str(class_counter))}." in f"/{ev}"):
                            exists = True
                            break

                if exists:
                    downloaded += 1
                else:
                    missing.append((class_counter, mod['name'], page['name']))
                
                class_counter += 1

    print(f"Total Clases con Video: {class_counter - 1}")
    print(f"Descargados exitosamente: {downloaded}")
    print(f"Faltantes por descargar: {len(missing)}")
    
    if missing:
        print("\n--- CLASES FALTANTES POR DESCARGAR (Primeras 30) ---")
        for num, mod_n, page_n in missing[:30]:
            print(f"Clase {num:3d} | Mod: {mod_n[:30]:<30} | {page_n}")

if __name__ == '__main__':
    main()
