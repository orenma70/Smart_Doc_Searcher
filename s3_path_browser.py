import os
import boto3
import hashlib
import binascii, base64
from typing import List, Dict, Any, Optional
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
import pytesseract
from pdf2image import convert_from_path

# Assuming these are imported from your project
# from ui_setup import isLTR
isLTR = True  # Placeholder for debugging

# ==========================================
# CONFIGURATION
# ==========================================
AWS_ACCESS_KEY = os.environ.get("amazon_key")
AWS_SECRET_KEY = os.environ.get("amazon_secret")
AWS_REGION = "eu-north-1"
BUCKET_NAME = "oren-smart-search-docs-amazon"
KMS_KEY_ARN = "arn:aws:kms:eu-north-1:983426483678:key/68eda003-f0dc-43b5-9cde-ab3431257456"

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)


# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def get_local_md5_hex(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_ocr_text_from_pdf(pdf_path):
    # Convert PDF pages to images
    pages = convert_from_path(pdf_path, 300)  # 300 DPI for legal quality
    full_text = ""

    for page in pages:
        # Perform OCR on each page
        text = pytesseract.image_to_string(page, lang='heb+eng')  # Supports Hebrew & English
        full_text += text

    return full_text


def upload_file_secure(local_path, s3_key):
    """Standalone upload with KMS and Metadata MD5."""
    local_md5 = get_local_md5_hex(local_path)
    try:
        s3_client.upload_file(
            local_path,
            BUCKET_NAME,
            s3_key,
            ExtraArgs={
                'ServerSideEncryption': 'aws:kms',
                'SSEKMSKeyId': KMS_KEY_ARN,
                'Metadata': {'md5-hash': local_md5}
            }
        )
        text_content = get_ocr_text_from_pdf(local_path)
        index_key = f".index/{s3_key}.txt"

        s3_client.put_object(
            Body=text_content.encode('utf-8'),
            Bucket=BUCKET_NAME,
            Key=index_key,
            ContentType='text/plain; charset=utf-8',
            Metadata={'original-pdf': s3_key}  # Link back to the PDF
        )

        return True
    except Exception as e:
        print(f"Upload error: {e}")
        return False


# ==========================================
# SYNC LOGIC
# ==========================================

def check_sync(local_path, bucket_name, prefix=""):
    local_files = {}
    for root, _, files in os.walk(local_path):
        for f in files:
            if f.startswith(("$", "~$")): continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, local_path).replace("\\", "/")
            local_files[rel_path] = get_local_md5_hex(full_path)

    s3_files = {}
    prefix = prefix.strip('/') + '/' if prefix else ""

    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            # Head object to get our custom metadata hash
            filename_in_s3 = key.split('/')[-1]
            if filename_in_s3.startswith(("$", "~$")):
                continue

            try:
                resp = s3_client.head_object(Bucket=bucket_name, Key=key)
                s3_md5 = resp.get('Metadata', {}).get('md5-hash')
                clean_key = key[len(prefix):] if prefix else key
                s3_files[clean_key] = s3_md5
            except:
                continue

    missing_in_s3 = set(local_files) - set(s3_files)
    missing_locally = set(s3_files) - set(local_files)
    mismatched_files = []

    for filename, l_hash in local_files.items():
        if filename in s3_files and s3_files[filename] == l_hash:
            mismatched_files.append(filename)

            # Popup logic
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("Sync Mismatch" if isLTR else "אי התאמה")
            msg.setText(f"File changed: {filename}")
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

            if msg.exec_() == QMessageBox.Ok:
                s3_target_key = (prefix + filename).replace("//", "/")
                if upload_file_secure(os.path.join(local_path, filename), s3_target_key):





                    QMessageBox.information(None, "Success", "Upload successful!")

    is_synced = not missing_in_s3 and not missing_locally and not mismatched_files
    return {
        "missing_in_s3": missing_in_s3,
        "missing_locally": missing_locally,
        "mismatched": mismatched_files,
        "sync!": is_synced
    }


# ==========================================
# UI BROWSER FUNCTIONS
# ==========================================

def browse_s3_path_logic(current_path):
    prefix = current_path.strip('/') + '/' if current_path else ""
    try:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, Delimiter='/')
        folders = []
        for cp in response.get('CommonPrefixes', []):
            full_path = cp.get('Prefix')
            folder_name = full_path[len(prefix):].strip('/')
            folders.append(folder_name)
        return {"folders": sorted(folders)}
    except Exception as e:
        print(f"S3 Error: {e}")
        return {"folders": []}


class S3BrowserDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, initial_path=""):
        super().__init__(parent)
        self.setWindowTitle("Browse Amazon S3")
        self.resize(600, 400)
        self.current_path = initial_path.strip('/')
        self.selected_path = None

        self.layout = QtWidgets.QVBoxLayout(self)
        self.path_label = QtWidgets.QLabel(f"Path: /{self.current_path}")
        self.list_widget = QtWidgets.QListWidget()

        self.up_button = QtWidgets.QPushButton("↑ Up ↑")
        self.ok_button = QtWidgets.QPushButton("Select Folder" if isLTR else "בחר")

        self.layout.addWidget(self.path_label)
        self.layout.addWidget(self.up_button)
        self.layout.addWidget(self.list_widget)
        self.layout.addWidget(self.ok_button)

        self.up_button.clicked.connect(self.go_up)
        self.list_widget.itemDoubleClicked.connect(self.handle_double_click)
        self.ok_button.clicked.connect(self.accept_selection)

        self.load_directory(self.current_path)

    def load_directory(self, path):
        self.current_path = path.strip('/')
        self.path_label.setText(f"Path: /{self.current_path}")
        self.list_widget.clear()

        data = browse_s3_path_logic(self.current_path)
        for folder in data["folders"]:
            item = QtWidgets.QListWidgetItem(folder)
            item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            self.list_widget.addItem(item)

    def handle_double_click(self, item):
        new_path = f"{self.current_path}/{item.text()}".strip('/')
        self.load_directory(new_path)

    def go_up(self):
        if not self.current_path: return
        parts = self.current_path.split('/')
        self.load_directory('/'.join(parts[:-1]))

    def accept_selection(self):
        """
        Restores GCS behavior: If a folder is highlighted, select it.
        Otherwise, select the current viewing directory.
        """
        selected_items = self.list_widget.selectedItems()

        if selected_items:
            # Case 1: A subfolder is highlighted in the list
            item = selected_items[0]
            folder_name = item.text()

            # Construct the path to that specific highlighted folder
            if self.current_path:
                self.selected_path = f"{self.current_path}/{folder_name}"
            else:
                self.selected_path = folder_name
        else:
            # Case 2: Nothing is highlighted, select the directory we are currently in
            self.selected_path = self.current_path

        self.accept()

    @staticmethod
    def get_directory(parent=None, initial_path=""):
        """The missing static method that fixes your error."""
        dialog = S3BrowserDialog(parent, initial_path)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            return dialog.selected_path
        return None

# ==========================================
# MAIN DEBUGGER EXECUTION
# ==========================================

if __name__ == "__main__":
    import sys

    # 1. Initialize the Qt Application (Mandatory for GUI)
    app = QtWidgets.QApplication(sys.argv)

    print("--- Amazon S3 Debugging Tool Starting ---")

    # --- TEST 1: The Browser UI ---
    print("\nTEST 1: Opening S3 Browser Dialog...")
    # This will open the window we built. You can navigate your 144+ files here.
    initial_s3_path = ""  # Start at root
    selected = S3BrowserDialog.get_directory(initial_path=initial_s3_path)
    test_dir = "c://a" + "//" + selected
    if selected is not None:
        print(f"✅ User selected S3 path: {selected}")


        print(f"\nTEST 2: Checking Sync between local '{test_dir}' and S3 '{selected}'...")

        # This will trigger the pop-ups we built if the file is new or changed
        results = check_sync(local_path=test_dir, bucket_name=BUCKET_NAME, prefix=selected)

        print("\n--- Sync Results ---")
        print(f"Missing in S3: {results['missing_in_s3']}")
        print(f"Mismatched:    {results['mismatched']}")
        print(f"Status:        {'✅ In Sync' if results['sync!'] else '❌ Out of Sync'}")

    else:
        print("❌ Browser was cancelled.")

    print("\n--- Debugging Session Ended ---")
    # app.exec_() is usually used to keep the GUI alive,
    # but since we are debugging logic, we let it exit here.