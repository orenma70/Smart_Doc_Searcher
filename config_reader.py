import os, re
import tkinter as tk
from tkinter import filedialog


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
    API_main = read_setup("API_main_google")
    API_search_url = API_main + read_setup("API_search_url")
    API_start_cache_url = API_main + read_setup("API_start_cache_url")
    API_cache_status_url = API_main + read_setup("API_cache_status_url")
else:
    API_main = read_setup("API_main_google")
    API_simple_search_url = API_main + read_setup("API_simple_search_url")
    API_search_url = API_main + read_setup("API_search_url")
    API_start_cache_url = API_main + read_setup("API_start_cache_url")
    API_cache_status_url = API_main + read_setup("API_cache_status_url")




CLIENT_PREFIX_TO_STRIP=read_setup("CLIENT_PREFIX_TO_STRIP")
LOCAL_MODE=read_setup("LOCAL_MODE")

if CLIENT_PREFIX_TO_STRIP is None:
    # 1. Create the main tkinter window instance (the 'root')
    root = tk.Tk()

    # 2. Hide the root window. This keeps the file dialog looking clean and native.
    root.withdraw()

    # 3. Open the native directory selection dialog
    directory_path = filedialog.askdirectory(
        title="Select Directory for CLIENT_PREFIX_TO_STRIP"
    )

    # 4. Check if the user selected a directory or cancelled
    if directory_path:
        # Update the variable with the selected path
        CLIENT_PREFIX_TO_STRIP = directory_path
        # You would then call a function here to save this path for next time
        # save_setup("CLIENT_PREFIX_TO_STRIP", CLIENT_PREFIX_TO_STRIP)
        print(f"CLIENT_PREFIX_TO_STRIP updated to: {CLIENT_PREFIX_TO_STRIP}")
    else:
        print("Directory selection cancelled. CLIENT_PREFIX_TO_STRIP remains None.")

# Example of using the variable later
if CLIENT_PREFIX_TO_STRIP:
    print(f"Current working path: {CLIENT_PREFIX_TO_STRIP}")

emailsec=read_setup("emailsec")
Language=read_setup("Language")
Voice_recognition_mode=read_setup("Voice_recognition_mode")
hd_cloud_auto_toggle=read_setup("hd_cloud_auto_toggle")


if cloud_storage_provider == "Amazon":
    BUCKET_NAME=read_setup("BUCKET_NAME_Amazon")
elif cloud_storage_provider == "Google":
    BUCKET_NAME=read_setup("BUCKET_NAME_Google")
else:
    BUCKET_NAME=""

GCS_OCR_OUTPUT_PATH = "gs://" + BUCKET_NAME + "/vision_ocr_output/"