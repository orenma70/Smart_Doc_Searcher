import os, re
CLOUD_PROVIDERS = ["Google", "Amazon", "Microsoft"]


def set_provider_config(cloud_provider):
    PROVIDER_CONFIG = {
        "cloud_provider": cloud_provider,
        "BUCKET_NAME": "",
        "API_search_url": "",
        "API_simple_search_url": "",
        "API_get_version_url": "",
        "API_cache_status_url": "",
        "CLIENT_PREFIX_TO_STRIP": ""
    }

    if cloud_provider in CLOUD_PROVIDERS:
        # שליפת ה-prefix (למשל _microsoft, _google) כדי לחסוך שכפול קוד
        suffix = "_" + cloud_provider.lower()
        API_main = read_setup(f"API_main{suffix}")

        PROVIDER_CONFIG.update({
            "API_main": API_main,
            "API_simple_search_url": API_main + read_setup("API_simple_search_url"),
            "API_search_url": API_main + read_setup("API_search_url"),
            "API_get_version_url": API_main + read_setup("API_get_version_url"),
            "API_cache_status_url": API_main + read_setup("API_cache_status_url"),
            "BUCKET_NAME": read_setup(f"BUCKET_NAME_{cloud_provider}"),
            "CLIENT_PREFIX_TO_STRIP": read_setup(f"CLIENT_PREFIX_TO_STRIP_{cloud_provider}")
        })

        # תוספת מיוחדת לגוגל
        if cloud_provider == "Google":
            PROVIDER_CONFIG["GCS_OCR_OUTPUT_PATH"] = f"gs://{PROVIDER_CONFIG['BUCKET_NAME']}/vision_ocr_output/"


        return PROVIDER_CONFIG

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


cloud_provider=read_setup("cloud_provider")
PROVIDER_CONFIG=set_provider_config(cloud_provider)

LOCAL_MODE=read_setup("LOCAL_MODE")


emailsec=read_setup("emailsec")
Language=read_setup("Language")
Voice_recognition_mode=read_setup("Voice_recognition_mode")
hd_cloud_auto_toggle=read_setup("hd_cloud_auto_toggle")



