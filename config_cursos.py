# Hotmart Course Configuration
# If the API cannot automatically list your courses, add them here.
# 
# To find your course subdomain:
# 1. Go to https://sun.hotmart.com/minhas-compras
# 2. Click "Access" on the desired course
# 3. Inside the URL you will see: https://hotmart.com/en/club/SUBDOMAIN/...
# 4. The "SUBDOMAIN" is what you must add below
#
# Example: if the URL is https://hotmart.com/en/club/punchneedlelucrativo/...
# then the subdomain is: punchneedlelucrativo

import os
from dotenv import load_dotenv

load_dotenv()

CURSOS_SUBDOMINIOS = [
    # {"subdomain": "example-course-subdomain", "productId": "1234567"},
]

env_subdomain = os.getenv("SUBDOMAIN", "").strip()
env_product_id = (os.getenv("PRODUCT_ID") or os.getenv("PRODUCTID") or "").strip()

if env_subdomain and not any(item.get("subdomain") == env_subdomain for item in CURSOS_SUBDOMINIOS):
    CURSOS_SUBDOMINIOS.append({"subdomain": env_subdomain, "productId": env_product_id})
