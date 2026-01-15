import os, re
#import tkinter as tk
#from tkinter import filedialog


def read_setup(key_name, config_file="setup.txt"):
    # ... (function start)
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    # --- CHANGE THIS LINE ---
    with open(config_file, 'r', encoding='utf-8') as f: # <--- ADD encoding='utf-8'
        for line in f:
            # 1. Strip whitespace and ignore comments
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # 2. Check for the '=' delimiter
            if '=' in line:
                key, value = line.split('=', 1)

                # 3. Clean up the key and value
                key = key.strip()
                value = value.strip()

                # 4. Return the value if the key matches
                if key == key_name:
                    value = re.sub(r'#.*', '', value)
                    return value.strip()

    # If the loop finishes without finding the key
    return None


email_used=read_setup("email_used")
email_str=read_setup(email_used+"_address")


cloud_storage_provider=read_setup("cloud_storage_provider")


if cloud_storage_provider == "Amazon":
    API_main = read_setup("API_main_amazon")
    API_simple_search_url = API_main + read_setup("API_simple_search_url")
    API_search_url = API_main + read_setup("API_search_url")
    API_get_version_url = API_main + read_setup("API_get_version_url")
    API_cache_status_url = API_main + read_setup("API_cache_status_url")
    BUCKET_NAME = read_setup("BUCKET_NAME_Amazon")
    CLIENT_PREFIX_TO_STRIP = read_setup("CLIENT_PREFIX_TO_STRIP_Amazon")
elif cloud_storage_provider == "Google":
    API_main = read_setup("API_main_google")
    API_simple_search_url = API_main + read_setup("API_simple_search_url")
    API_search_url = API_main + read_setup("API_search_url")
    API_get_version_url = API_main + read_setup("API_cache_status_url")
    API_cache_status_url = API_main + read_setup("API_cache_status_url")
    BUCKET_NAME = read_setup("BUCKET_NAME_Google")
    CLIENT_PREFIX_TO_STRIP = read_setup("CLIENT_PREFIX_TO_STRIP_Google")
elif cloud_storage_provider == "Microsoft":
    API_main = read_setup("API_main_microsoft")
    API_simple_search_url = API_main + read_setup("API_simple_search_url")
    API_search_url = API_main + read_setup("API_search_url")
    API_get_version_url = API_main + read_setup("API_get_version_url")
    API_cache_status_url = API_main + read_setup("API_cache_status_url")
    BUCKET_NAME=read_setup("BUCKET_NAME_Microsoft")
    CLIENT_PREFIX_TO_STRIP = read_setup("CLIENT_PREFIX_TO_STRIP_Microsoft")
else:
    BUCKET_NAME = ""


LOCAL_MODE=read_setup("LOCAL_MODE")


emailsec=read_setup("emailsec")
Language=read_setup("Language")
Voice_recognition_mode=read_setup("Voice_recognition_mode")
hd_cloud_auto_toggle=read_setup("hd_cloud_auto_toggle")



GCS_OCR_OUTPUT_PATH = "gs://" + BUCKET_NAME + "/vision_ocr_output/"