import os, sys
from google.cloud import storage
from typing import List, Dict, Any, Optional, Union
# We assume PyQt5 is used based on QFileDialog in browse_directory
from PyQt5 import QtWidgets, QtCore, QtGui
from search_utilities import get_storage_client
from azure_search_utilities import browse_azure_path_logic
import time
import hashlib
import binascii, base64
from ui_setup import isLTR
from PyQt5.QtWidgets import QMessageBox
import boto3  # Make sure to pip install boto3
import pdfplumber
import io, re
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from docx import Document
import json
from azure.storage.blob import BlobServiceClient



# Set your flag here based on your environment



# Global client variables
gcs_client: Optional[storage.Client] = None
s3_client: Any = None
KMS_KEY_ARN = "arn:aws:kms:ap-southeast-2:038715112888:key/82ae7f3a-eb41-4f29-bd2c-85b9ab573023"




def get_azure_files_recursive(container_name, prefix):
    # התחברות ללקוח (יש להגדיר CONNECTION_STRING במערכת)
    connection_string = os.getenv("azuresmartsearch3key1conn")
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(container_name)

    cloud_files = {}

    # יצירת רשימת prefixes לסריקה
    prefixes_to_scan = [prefix]
    if prefix:
        clean_prefix = prefix.strip('/')
        prefixes_to_scan.append(f".index/{clean_prefix}")

    for current_scan_prefix in prefixes_to_scan:
        search_prefix = current_scan_prefix
        if search_prefix and not search_prefix.endswith('/'):
            search_prefix += '/'

        # ב-Azure, list_blobs מחזיר גנרטור שעושה Pagination אוטומטי
        blobs = container_client.list_blobs(name_starts_with=search_prefix)

        for blob in blobs:
            full_key = blob.name

            if full_key == search_prefix:
                continue

            # חילוץ שם הקובץ היחסי
            name = full_key[len(search_prefix):]

            # סינון קבצים זמניים (לפי הלוגיקה שלך)
            if any(pattern in name for pattern in ['$', '~$', '$~']):
                continue

            try:
                # ב-Azure ה-MD5 נמצא לרוב ב-blob.content_settings.content_md5
                # הוא מגיע בפורמט bytes של Base64, לכן נהפוך אותו לסטרינג
                md5_hash = None
                if blob.content_settings.content_md5:
                    import base64
                    md5_hash = base64.b64encode(blob.content_settings.content_md5).decode('utf-8')

                # אם ה-MD5 לא שם, אפשר לחפש ב-Metadata (אם שמרת אותו שם ידנית)
                if not md5_hash:
                    md5_hash = blob.metadata.get('md5_hash')

                # בניית המפתח למילון (תאימות ל-GUI)
                dict_key = name
                if full_key.startswith(".index/"):
                    clean_p = prefix.strip('/')
                    dict_key = f".index/{clean_p}/{name}".replace("//", "/")

                cloud_files[dict_key] = md5_hash

            except Exception as e:
                print(f"Error processing metadata for blob {full_key}: {e}")

    return cloud_files

def delete_from_cloud_with_index(self,filename, prefix=""):
    """
    מוחק מהענן (AWS או GCS) את הקובץ המקורי ואת האינדקס שלו
    """
    # 1. הגדרת הנתיבים (זהים לשני העננים)
    target_key = f"{prefix}/{filename}".replace("//", "/").strip("/")
    base_name = os.path.splitext(filename)[0]
    index_key = f".index/{prefix}/{base_name}.json".replace("//", "/").strip("/")


    try:
        if self.cloud_provider == "Amazon":
            # --- מחיקה מ-AWS S3 ---
            client = get_s3_client()

            # מחיקה של שני האובייקטים בבת אחת (יעיל יותר)
            client.delete_objects(
                Bucket=self.bucket_name,
                Delete={
                    'Objects': [
                        {'Key': target_key},
                        {'Key': index_key}
                    ],
                    'Quiet': True
                }
            )
            print(f"🗑️ AWS: Deleted {target_key} and its index.")

        elif self.cloud_provider == "Google":
            # --- מחיקה מ-Google Cloud Storage ---
            global gcs_client
            if gcs_client is None:
                gcs_client = get_storage_client()
            bucket = gcs_client.bucket(self.bucket_name)

            # ב-GCS מוחקים כל אובייקט בנפרד
            blob = bucket.blob(target_key)
            if blob.exists():
                blob.delete()

            index_blob = bucket.blob(index_key)
            if index_blob.exists():
                index_blob.delete()

            print(f"🗑️ GCS: Deleted {target_key} and its index.")
        elif self.cloud_provider == "Microsoft":
            # --- מחיקה מ-Microsoft Azure Blob Storage ---

            connection_string = os.getenv("azuresmartsearch3key1conn")
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            container_client = blob_service_client.get_container_client(self.bucket_name)
            # מחיקה של הקובץ המקורי
            blob_file = container_client.get_blob_client(target_key)
            if blob_file.exists():
                blob_file.delete_blob()

            # מחיקה של האינדקס
            blob_index = container_client.get_blob_client(index_key)
            if blob_index.exists():
                blob_index.delete_blob()

            print(f"🗑️ Azure: Deleted {target_key} and its index.")



    except Exception as e:
        print(f"❌ Error during cloud deletion of {filename}: {e}")
        return False


def extract_text_for_indexing(file_bytes, file_ext):
    used_ocr = False
    file_ext = file_ext.lower()
    pages_data = []  # נשמור כאן רשימת אובייקטים של עמודים

    try:
        if file_ext == '.pdf':
            pages_data = []
            used_ocr = False
            fitz_flag = False  # שנה ל-False כדי לבדוק את pdfplumber

            # פתרון לבעיית ה-with: נפתח את הקובץ לפי הפלאג
            if fitz_flag:
                doc_context = fitz.open(stream=file_bytes, filetype="pdf")
                pages_iterator = doc_context
            else:
                doc_context = pdfplumber.open(io.BytesIO(file_bytes))
                pages_iterator = doc_context.pages

            with doc_context as doc:
                for p_num_zero, page in enumerate(pages_iterator):
                    p_num = p_num_zero + 1  # מספור עמודים אנושי (1, 2, 3...)

                    # 1. חילוץ טקסט ראשוני
                    if fitz_flag:
                        current_text = page.get_text().strip()
                    else:
                        current_text = page.extract_text() or ""

                    # 2. בדיקה אם צריך OCR
                    if len(current_text.strip()) < 100:
                        print(f"Page {p_num}: Running OCR...")
                        used_ocr = True

                        if fitz_flag:
                            # שימוש ב-Fitz לרנדור תמונה
                            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert('L')
                        else:
                            # שימוש ב-pdfplumber לרנדור תמונה
                            img = page.to_image(resolution=220).original
                            img = img.convert('L')

                        # הרצת ה-OCR
                        lang = 'eng' if isLTR else 'heb'
                        page_text = pytesseract.image_to_string(img, lang=lang)
                    else:
                        # אם הטקסט חולץ בהצלחה ללא OCR
                        page_text = current_text

                    # 3. שמירת הנתונים ל-JSON
                    if page_text.strip():
                        lines = [l.strip() for l in page_text.split('\n') if l.strip()]
                        pages_data.append({"page": p_num, "lines": lines})


        elif file_ext == '.docx':
            doc = Document(io.BytesIO(file_bytes))
            # ב-DOCX נתייחס להכל כעמוד 1 או נחלק לפי פסקאות
            text_lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            if text_lines:
                pages_data.append({"page": 1, "lines": text_lines})

            # OCR לתמונות בתוך ה-DOCX
            current_page = 2
            for rel in doc.part.rels.values():
                if "image" in rel.target_ref:
                    try:
                        img = Image.open(io.BytesIO(rel.target_part.blob))
                        ocr_text = pytesseract.image_to_string(img.convert('L'), lang='heb+eng')
                        if ocr_text.strip():
                            pages_data.append({
                                "page": current_page,
                                "lines": [l.strip() for l in ocr_text.split('\n') if l.strip()]
                            })
                            current_page += 1
                            used_ocr = True
                    except:
                        continue

    except Exception as e:
        print(f"ERROR in extraction: {e}")
        return [], False

    return pages_data, used_ocr


def upload_to_cloud(self,local_folder, filename, base_folder):
    # נרמול נתיבים
    cloud_provider = self.provider_info["cloud_provider"]
    use_mode_aws = cloud_provider == "Amazon"
    use_mode_azr = cloud_provider == "Microsoft"
    use_mode_clr = cloud_provider == "Google"

    local_folder = os.path.normpath(local_folder)
    base_folder = os.path.normpath(base_folder)
    pdf_path = os.path.join(local_folder, filename)

    # חילוץ נתיבים יחסיים
    relative_dir = os.path.relpath(local_folder, base_folder).replace("\\", "/")
    relative_file_path = f"{relative_dir}/{filename}".replace("//", "/")

    base_name = os.path.splitext(filename)[0]
    local_index_path = os.path.join(base_folder, ".index", relative_dir, f"{base_name}.json")
    cloud_index_key = f".index/{relative_dir}/{base_name}.json".replace("//", "/")

    os.makedirs(os.path.dirname(local_index_path), exist_ok=True)

    try:
        pages_data = None
        if os.path.exists(local_index_path):
            try:
                with open(local_index_path, "r", encoding="utf-8") as f:
                    pages_data = json.load(f)
                    was_ocr_needed = True
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()

                print(f"--- [Fast Path] Loaded existing index for {filename} ---")
            except Exception as e:
                print(f"Error reading existing index: {e}, re-indexing...")

        # --- רק אם לא מצאנו JSON מוכן, נריץ את החילוץ הכבד ---
        if pages_data is None:

            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            file_ext = os.path.splitext(filename)[1].lower()
            pages_data, was_ocr_needed = extract_text_for_indexing(pdf_bytes, file_ext)

        # Hash של ה-PDF
        pdf_hex_md5 = hashlib.md5(pdf_bytes).hexdigest()
        hex_md5, b64_md5 = get_local_hashes(pdf_path)
        index_data = {
            "filename": filename,
            "pages": pages_data,
            "ocr_used": was_ocr_needed,
            "md5_hash": pdf_hex_md5,
            "timestamp": time.time()
        }

        # יצירת ה-JSON כ-Bytes (למניעת בעיות Encoding/Newline בווינדוס)
        json_payload = json.dumps(index_data, ensure_ascii=False, indent=4).encode('utf-8')
        json_hex_md5 = hashlib.md5(json_payload).hexdigest()

        # שמירה כבינארי (wb)
        with open(local_index_path, "wb") as f:
            f.write(json_payload)

        if use_mode_aws:
            client = get_s3_client()
            # העלאת PDF
            client.upload_file(pdf_path, self.provider_info["BUCKET_NAME"], relative_file_path, ExtraArgs={
                'Metadata': {'md5-hash': pdf_hex_md5}
            })
            # העלאת JSON
            client.put_object(
                Body=json_payload,
                Bucket=self.provider_info["BUCKET_NAME"],
                Key=cloud_index_key,
                ContentType='application/json',
                Metadata={'md5-hash': json_hex_md5}
            )
            print(f"✅ Uploaded: {filename} (JSON MD5: {json_hex_md5})")
        elif use_mode_clr:
            client = get_storage_client()
            bucket = client.bucket(self.provider_info["BUCKET_NAME"])

            blob_file = bucket.blob(relative_file_path)
            blob_file.md5_hash = b64_md5
            blob_file.metadata = {'md5-hash': pdf_hex_md5}  # שומרים גם Hex למען האחידות עם AWS
            blob_file.upload_from_filename(pdf_path)

            blob_index = bucket.blob(cloud_index_key)
            import base64
            json_b64_md5 = base64.b64encode(hashlib.md5(json_payload).digest()).decode('utf-8')
            blob_index.md5_hash = json_b64_md5

            blob_index.metadata = {'md5-hash': json_hex_md5}

            blob_index.content_type = 'application/json'

            # העלאה ישירות מהזיכרון (כמו put_object)

            blob_index.upload_from_string(json_payload, content_type='application/json')

            print(f"✅ Uploaded to Google: {filename} (JSON MD5: {json_hex_md5})")
        elif use_mode_azr:
            connection_string = os.getenv("azuresmartsearch3key1conn")
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            container_client = blob_service_client.get_container_client(self.provider_info["BUCKET_NAME"])

            # 1. העלאת קובץ ה-PDF
            blob_file = container_client.get_blob_client(relative_file_path)

            import base64
            # Azure דורש את ה-MD5 בפורמט Bytes לצורך אימות (Integrity check)
            md5_bytes = base64.b64decode(b64_md5)

            from azure.storage.blob import ContentSettings

            with open(pdf_path, "rb") as data:
                blob_file.upload_blob(
                    data,
                    overwrite=True,
                    content_settings=ContentSettings(content_md5=md5_bytes),
                    # שומרים את ה-Hex ב-Metadata כדי שיהיה לך קל להשוות עם AWS
                    metadata={'md5_hash': pdf_hex_md5}
                )

            # 2. העלאת קובץ ה-JSON (האינדקס)
            blob_index = container_client.get_blob_client(cloud_index_key)

            # חישוב MD5 ל-JSON (בפורמט Bytes עבור Azure)
            json_md5_bytes = hashlib.md5(json_payload).digest()

            blob_index.upload_blob(
                json_payload,
                overwrite=True,
                content_settings=ContentSettings(
                    content_type='application/json; charset=utf-8',  # מונע ג'יבריש בעברית
                    content_md5=json_md5_bytes
                ),
                metadata={'md5_hash': json_hex_md5}
            )

            print(f"✅ Uploaded to Azure: {filename} (JSON MD5: {json_hex_md5})")

    except Exception as e:
        print(f"❌ Error in upload: {e}")

def get_s3_client():
    """Initializes AWS S3 client using environment variables."""
    global s3_client
    if s3_client is None:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_KEY"),
            region_name="ap-southeast-2"
        )
    return s3_client


# ==============================================================================
# UNIFIED CLOUD BROWSER
# ==============================================================================

def browse_cloud_path(self) -> Dict[str, List[str]]:
    """Entry point for the GUI to fetch folder lists."""


    use_mode_aws = self.provider == "Amazon"
    use_mode_azr = self.provider == "Microsoft"
    use_mode_clr = self.provider == "Google"

    if use_mode_aws:
        return browse_s3_path_logic(self)
    elif use_mode_clr:
        return browse_gcs_path(self)
    elif use_mode_azr:
        return browse_azure_path_logic(self)
    else:
        return False

def browse_s3_path_logic(self) -> Dict[str, List[str]]:
    """AWS S3 implementation: returns a list of folder names just like GCS."""

    path_prefix = self.current_path
    # Example usage
    path_prefix = f"{path_prefix}"
    # 1. Normalize the prefix path
    normalized_prefix = path_prefix.strip('/').replace('\\', '/')
    if normalized_prefix and not normalized_prefix.endswith('/'):
        normalized_prefix += '/'

    prefix = normalized_prefix

    client = get_s3_client()
    try:
        # Delimiter='/' tells S3 to group files into virtual folders
        response = client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=prefix,
            Delimiter='/'
        )

        folders = []
        # In S3, 'CommonPrefixes' are what we call folders
        if 'CommonPrefixes' in response:
            for cp in response['CommonPrefixes']:
                # Example: 'photos/vacation/' -> strip last '/' -> split -> get 'vacation'
                full_path = cp['Prefix'].rstrip('/')
                folder_name = full_path.split('/')[-1]
                folders.append(folder_name)

        return {"folders": sorted(folders)}
    except Exception as e:
        print(f"S3 Browse Error: {e}")
        return {"folders": []}


def browse_gcs_path_logic(self,prefix: str) -> Dict[str, List[str]]:
    """Your original GCS logic wrapped for the switchboard."""
    global gcs_client
    if gcs_client is None:
        gcs_client = get_storage_client()

    try:
        bucket = gcs_client.bucket(self.bucket_name)
        blobs_iterator = bucket.list_blobs(prefix=prefix, delimiter='/')
        # GCS returns folders in the 'prefixes' attribute when delimiter is used
        folders = [p.rstrip('/').split('/')[-1] for p in blobs_iterator.prefixes]
        return {"folders": sorted(folders)}
    except Exception as e:
        print(f"GCS Browse Error: {e}")
        return {"folders": []}


# ==============================================================================
# UNIFIED SYNC & UPLOAD
# ==============================================================================

def get_local_hashes(file_path):
    """Generates both Hex (S3) and Base64 (GCS) MD5 hashes."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    hex_digest = hash_md5.hexdigest()
    b64_digest = base64.b64encode(binascii.unhexlify(hex_digest)).decode("utf-8")
    return hex_digest, b64_digest

def browse_s3_logic(self,prefix: str) -> Dict[str, List[str]]:
    """AWS S3 implementation of folder browsing."""
    try:
        # Note: Boto3 uses 'CommonPrefixes' for virtual folders
        response = s3_client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=prefix,
            Delimiter='/'
        )
        folders = []
        if 'CommonPrefixes' in response:
            for cp in response['CommonPrefixes']:
                # Strip the prefix to get just the folder name for the UI
                full_path = cp['Prefix'].rstrip('/')
                folder_name = full_path.split('/')[-1]
                folders.append(folder_name)
        return {"folders": sorted(folders)}
    except Exception as e:
        print(f"S3 Error: {e}")
        return {"folders": []}


def get_file_hash(path):
    """Returns (Hex_Hash, Base64_Hash) to support both clouds."""
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)

    hex_md5 = hash_md5.hexdigest()
    base64_md5 = base64.b64encode(binascii.unhexlify(hex_md5)).decode("utf-8")
    return hex_md5, base64_md5


def browse_s3_path(self,prefix: str) -> Dict[str, List[str]]:
    """AWS S3 implementation of folder browsing."""
    try:
        s3_client = boto3.client('s3')  # Uses your aws configure credentials
        # Delimiter='/' is what tells S3 to 'act' like a folder system
        response = s3_client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=prefix,
            Delimiter='/'
        )

        folders = []
        # S3 returns 'folders' in the CommonPrefixes key
        if 'CommonPrefixes' in response:
            for cp in response['CommonPrefixes']:
                # S3 returns full path 'folder/sub/', we strip to get just 'sub'
                full_name = cp['Prefix'].rstrip('/')
                folder_name = full_name.split('/')[-1]
                folders.append(folder_name)

        return {"folders": sorted(folders)}
    except Exception as e:
        print(f"S3 Error: {e}")
        return {"folders": []}



def upload_to_bucket(bucket, local_folder, filename, prefix=""):
    local_path = os.path.join(local_folder, filename)
    if prefix and not prefix.endswith('/'):
        gcs_path = f"{prefix}/{filename}"
    else:
        gcs_path = f"{prefix}{filename}"

    blob = bucket.blob(gcs_path)

    # 1. Disable "smart" content-type guessing
    # 2. Upload as a raw stream to ensure MD5 matches the HD perfectly
    blob.content_type = 'application/octet-stream'

    #with open(local_path, "rb") as f:
    blob.upload_from_filename(local_path)

def md5_of_file(path):
    """Compute MD5 checksum of a local file."""
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return base64.b64encode(binascii.unhexlify(hash_md5.hexdigest())).decode("utf-8")


def check_sync(self,local_path, bucket_name, prefix=""):
    """
    גרסה מעודכנת המבוססת על הקוד המקורי - שואלת פעם אחת על הכל.
    """
    # 1. איסוף קבצים מקומיים וה-Hashes שלהם (ללא שינוי)
    cloud_provider = self.provider_info["cloud_provider"]
    use_mode_aws = cloud_provider  == "Amazon"
    use_mode_azr = cloud_provider == "Microsoft"
    use_mode_clr = cloud_provider == "Google"

    local_files = {}
    for root, _, files in os.walk(local_path):
        for f in files:
            if f.startswith("$") or f.startswith("~$"): continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, local_path).replace("\\", "/")
            hex_md5, b64_md5 = get_local_hashes(full_path)
            local_files[rel_path] = hex_md5 if use_mode_aws else b64_md5

    index_root = os.path.join(self.provider_info["CLIENT_PREFIX_TO_STRIP"], ".index")
    if os.path.exists(index_root):
        for root, _, files in os.walk(index_root):
            for f in files:
                if not f.endswith(".json"): continue
                full_path = os.path.join(root, f)
                rel_to_index = os.path.relpath(full_path, index_root).replace("\\", "/")
                rel_path = f".index/{rel_to_index}"
                hex_md5, b64_md5 = get_local_hashes(full_path)
                local_files[rel_path] = hex_md5 if use_mode_aws else b64_md5

    # 2. איסוף קבצים מהענן (ללא שינוי)
    cloud_files = {}
    if use_mode_aws:
        cloud_files = get_cloud_files_recursive(bucket_name, prefix)
    elif use_mode_azr:
        cloud_files = get_azure_files_recursive(bucket_name, prefix)
    elif use_mode_clr:
        global gcs_client
        if gcs_client is None: gcs_client = get_storage_client()
        bucket = gcs_client.bucket(bucket_name)
        for blob in bucket.list_blobs(prefix=prefix):
            name = blob.name[len(prefix):].lstrip("/")
            if name: cloud_files[name] = blob.md5_hash
        index_prefix = f".index/{prefix}".replace("//", "/")
        for blob in bucket.list_blobs(prefix=index_prefix):
            name = blob.name
            if name: cloud_files[name] = blob.md5_hash

    # 3. השוואת סטים (הלוגיקה המקורית שלך)
    missing_in_cloud = set(local_files) - set(cloud_files)
    missing_locally = set(cloud_files) - set(local_files)

    # רשימות לאיסוף הקבצים במקום שאלות מיידיות
    files_to_upload = []
    mismatched_files = []

    # לוגיקה לזיהוי קבצים להעלאה/עדכון
    for filename in local_files:
        is_missing = filename in missing_in_cloud
        is_json = filename.lower().endswith('.json')
        is_mismatched = False
        if not is_json:
            is_mismatched = (filename in cloud_files and local_files[filename] != cloud_files[filename])

        if is_missing or is_mismatched:
            files_to_upload.append(filename)
            if is_mismatched:
                mismatched_files.append(filename)


    # --- שאלה אחת וביצוע העלאה ---
    if files_to_upload:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("סנכרון קבצים" if not isLTR else "Sync Files")
        msg.setText(
            f"נמצאו {len(files_to_upload)} קבצים להעלאה/עדכון. לבצע?" if not isLTR else f"Update {len(files_to_upload)} files?")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if msg.exec_() == QMessageBox.Ok:
            for filename in files_to_upload:
                upload_to_cloud(self,local_path, filename, base_folder=self.provider_info["CLIENT_PREFIX_TO_STRIP"])

                if filename in missing_in_cloud:
                    missing_in_cloud.remove(filename)  # הקובץ כבר לא חסר בענן

                if filename in mismatched_files:
                    mismatched_files.remove(filename)  # הקו
    # --- שאלה אחת וביצוע מחיקה ---
    files_to_delete = [f for f in missing_locally if not f.startswith(".index/")]
    if files_to_delete:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("מחיקה מהענן" if not isLTR else "Cloud Delete")
        msg.setText(f"נמצאו {len(files_to_delete)} קבצים למחיקה מהענן. לבצע?" if not isLTR else f"Delete {len(files_to_delete)} files from cloud?")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if msg.exec_() == QMessageBox.Ok:
            for filename in files_to_delete:
                delete_from_cloud_with_index(self,filename, prefix=prefix)

    sync_status = not missing_locally and not missing_in_cloud and not mismatched_files
    return {
        "missing_in_gcs": missing_in_cloud,
        "missing_locally": missing_locally,
        "mismatched": mismatched_files,
        "sync!": sync_status
    }



def list_s3_contents(bucket, prefix):
    s3 = boto3.client('s3')

    # Ensure prefix ends with / to look INSIDE the folder
    if prefix and not prefix.endswith('/'):
        prefix += '/'
    s3_client= get_s3_client()
    #response = s3.list_objects_v2(
    #    Bucket=bucket,
    #    Prefix=prefix,
    #    Delimiter='/'  # This is the magic "folder" creator
    #)
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter='/')
    # 1. Look at Sub-folders (CommonPrefixes)
    print("--- Folders ---")
    for content in response.get('CommonPrefixes', []):
        print(f"Folder: {content.get('Prefix')}")

    # 2. Look at Files (Contents)
    print("\n--- Files ---")
    for obj in response.get('Contents', []):
        if obj['Key'] != prefix:  # Skip the folder object itself
            print(f"File: {obj['Key']} | Size: {obj['Size']} bytes")


def get_cloud_files_recursive(bucket_name, prefix):
    s3_client = get_s3_client()
    cloud_files = {}

    # יצירת רשימת prefixes: המקורי שלך, והמקביל לו בתוך .index
    # אם prefix הוא "גירושין", נסרוק גם את ".index/גירושין"
    prefixes_to_scan = [prefix]
    if prefix:
        # מוודא שהנתיב לאינדקס נבנה נכון
        clean_prefix = prefix.strip('/')
        prefixes_to_scan.append(f".index/{clean_prefix}")

    for current_scan_prefix in prefixes_to_scan:
        # --- תחילת הקוד המקורי שלך (ללא שינוי בשורות) ---
        search_prefix = current_scan_prefix
        if search_prefix and not search_prefix.endswith('/'):
            search_prefix += '/'

        paginator = s3_client.get_paginator('list_objects_v2')

        for page in paginator.paginate(Bucket=bucket_name, Prefix=search_prefix):
            for obj in page.get('Contents', []):
                full_key = obj['Key']

                if full_key == search_prefix:
                    continue

                # שמירה על הלוגיקה המקורית שלך לחילוץ השם
                name = full_key[len(search_prefix):]

                # סינון קבצים זמניים בדיוק כפי שהגדרת
                if name.startswith('$') or name.startswith('~$') or name.startswith(
                        '$~') or '~$' in name or '$~' in name:
                    continue

                try:
                    head = s3_client.head_object(Bucket=bucket_name, Key=full_key)
                    md5_hash = head.get('Metadata', {}).get('md5-hash')

                    # אם אנחנו בסריקה של אינדקס, נשמור את השם עם הקידומת המתאימה
                    # כדי שה-GUI יזהה שמדובר בקובץ מהתיקייה הנסתרת
                    dict_key = name
                    if full_key.startswith(".index/"):
                        # בונה את השם כך שיכלול את המבנה שה-GUI מצפה לו ב-.index
                        dict_key = f".index/{clean_prefix}/{name}".replace("//", "/")

                    cloud_files[dict_key] = md5_hash

                except Exception as e:
                    print(f"Error fetching metadata for {full_key}: {e}")
        # --- סוף הקוד המקורי שלך ---

    return cloud_files

# ==============================================================================
# GCS CORE BROWSER FUNCTION
# ==============================================================================


def browse_gcs_path(self) -> Dict[str, List[str]]:
    """
    Lists the virtual directories (prefixes) and  (blobs) at a given GCS path.
    """
    path_prefix = self.current_path
    # Example usage
    path_prefix = f"{path_prefix}"
    # 1. Normalize the prefix path
    normalized_prefix = path_prefix.strip('/').replace('\\', '/')
    if normalized_prefix and not normalized_prefix.endswith('/'):
        normalized_prefix += '/'


    timer0 = time.time()

    global gcs_client

    # Check 1: If the client already exists, return it instantly (0 seconds)
    if gcs_client is None:
        gcs_client = get_storage_client()

    if gcs_client is None:
        return {"folders": []}



    try:

        bucket = gcs_client.bucket(self.bucket_name)
        blobs_iterator = bucket.list_blobs(prefix=normalized_prefix)

        folders = set()
        timer1 = time.time()
        for blob in blobs_iterator:
            file_path = blob.name

            # 2. Get the path segment AFTER the current normalized_prefix
            relative_path = file_path[len(normalized_prefix):]

            if not relative_path:
                continue

                # 3. Manually find the next level folder
            if '/' in relative_path:
                # If the object path contains a slash, the part before the first slash is the folder name.
                top_level_folder = relative_path.split('/')[0]
                folders.add(top_level_folder)

            # Note: We ignore files at this level (objects without a slash) because the dialog only browses folders.

        final_folders = list(folders)
        time1= timer1-timer0
        time2 = time.time() - timer1
        print(f"DEBUG: Inferred {len(final_folders)} virtual folders successfully. time={time1}:{time2}")

        # Return sorted folders
        return {"folders": final_folders}



    except Exception as e:
        print(f"Error browsing GCS path '{path_prefix}': {e}")
        return {"folders": []}


# ==============================================================================
# GCS BROWSER DIALOG (GUI IMPLEMENTATION)
# ==============================================================================

class GCSBrowserDialog(QtWidgets.QDialog):
    """
    A custom dialog window for navigating GCS virtual directories.
    """

    def __init__(self, parent=None, initial_path=""):
        super().__init__(parent)

        self.provider = parent.provider_info["cloud_provider"]
        self.bucket_name = parent.provider_info["BUCKET_NAME"]
        self.setWindowTitle(f"Browse {self.provider} Bucket")
        self.setGeometry(100, 100, 600, 400)
        self.current_path = initial_path.strip('/').replace('\\', '/')
        self.selected_path = None

        # Widgets
        self.path_label = QtWidgets.QLabel("Path: /")
        self.list_widget = QtWidgets.QListWidget()

        self.up_button = QtWidgets.QPushButton("↑ Up ↑")
        self.up_button.setFixedWidth(120)
        self.up_button.setStyleSheet("padding: 5px 10px; font-size: 18pt;width: 60px; height: 30px;")

        if isLTR:
            self.ok_button = QtWidgets.QPushButton("Select Folder 📂")
            self.cancel_button = QtWidgets.QPushButton("Cancel")
        else:
            self.ok_button = QtWidgets.QPushButton("📂 בחר ספרייה")
            self.cancel_button = QtWidgets.QPushButton("בטל x")


        # Layout
        path_layout = QtWidgets.QHBoxLayout()
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.up_button)


        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(path_layout)
        main_layout.addWidget(self.list_widget)
        main_layout.addLayout(button_layout)

        # Signals
        self.ok_button.clicked.connect(self.accept_selection)
        self.cancel_button.clicked.connect(self.reject)
        self.up_button.clicked.connect(self.go_up_directory)
        self.list_widget.itemDoubleClicked.connect(self.handle_double_click)

        # Initial load
        self.load_directory(self.current_path)


    def load_directory(self, path: str):
        """Fetches contents from GCS and updates the list widget."""
        self.list_widget.clear()

        provider = self.provider
        # Strip trailing slash for display, but keep it internal for logic
        self.current_path = path.strip('/').replace('\\', '/')
        display_path = self.current_path if self.current_path else " (Root)"
        self.path_label.setText(f" {display_path} 📂")
        self.path_label.setStyleSheet("font-size: 20pt; color: black;")

        #contents = browse_gcs_path(self)
        contents = browse_cloud_path(self)

        # 1. Add Folders (with folder icon)
        for folder in contents["folders"]:
            item = QtWidgets.QListWidgetItem(f"{folder}")
            item.setData(QtCore.Qt.UserRole, folder)  # Store the name
            item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            self.list_widget.addItem(item)



        self.list_widget.sortItems()

    def handle_double_click(self, item: QtWidgets.QListWidgetItem):
        """Handles double-click event: navigate down into a folder."""
        folder_name = item.data(QtCore.Qt.UserRole)

        if folder_name is not None:  # It's a folder, not a file
            new_path = f"{self.current_path}/{folder_name}" if self.current_path else folder_name
            self.load_directory(new_path)

    def go_up_directory(self):
        """Handles the 'Up' button click: navigate one level up."""
        if not self.current_path:
            return  # Already at root

        # Split path and remove the last element
        path_parts = self.current_path.split('/')
        parent_path = '/'.join(path_parts[:-1])

        self.load_directory(parent_path)

    def accept_selection(self):
        """
        Sets the selected path. Prioritizes a highlighted item in the list
        over the current viewing directory (self.current_path).
        """
        selected_items = self.list_widget.selectedItems()

        if selected_items:
            # Case 1: An item (subfolder) is highlighted in the list.
            item = selected_items[0]
            folder_name = item.data(QtCore.Qt.UserRole)

            if folder_name is not None:
                # Construct the path to the SELECTED subfolder
                new_path = f"{self.current_path}/{folder_name}" if self.current_path else folder_name
                self.selected_path = new_path
            else:
                # If the selected item is not a folder (e.g., the 'No Subfolders' text), default to current path.
                self.selected_path = self.current_path
        else:
            # Case 2: Nothing is highlighted, select the current directory (self.current_path).
            self.selected_path = self.current_path

        self.accept()

    @staticmethod
    def get_directory(parent=None, initial_path=""):
        """Static method to show the dialog and return the selected path."""
        dialog = GCSBrowserDialog(parent, initial_path)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            return dialog.selected_path
        return None


# ==============================================================================
# STANDALONE TEST ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    # To run this, ensure environment variables are set:
    # os.environ["amazon_key"] = "..."
    # os.environ["amazon_secret"] = "..."
    # os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "path_to_json"

    app = QtWidgets.QApplication(sys.argv)

    # Optional: Set a dark theme or style
    app.setStyle("Fusion")
    BUCKET_NAME =""
    print(f" on Bucket: {BUCKET_NAME}") #Starting test with use_mode_aws={use_mode_aws}

    dialog = GCSBrowserDialog()
    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        final_path = dialog.selected_path()
        print(f"USER SELECTED PATH: {final_path}")
        QtWidgets.QMessageBox.information(None, "Selection", f"You chose: {final_path}")
    else:
        print("User cancelled selection.")

    sys.exit(0)