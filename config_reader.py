import os

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
                    return value

    # If the loop finishes without finding the key
    return None


BUCKET_NAME=read_setup("BUCKET_NAME")
GCS_OCR_OUTPUT_PATH = "gs://" + BUCKET_NAME + "/vision_ocr_output/"

API_main=read_setup("API_main")
API_search_url = API_main + read_setup("API_search_url")
API_simple_search_url = API_main + read_setup("API_simple_search_url")
API_start_cache_url = API_main + read_setup("API_start_cache_url")
API_cache_status_url = API_main + read_setup("API_cache_status_url")

CLIENT_PREFIX_TO_STRIP=read_setup("CLIENT_PREFIX_TO_STRIP")