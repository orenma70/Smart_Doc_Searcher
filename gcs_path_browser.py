import os, sys
from google.cloud import storage
from typing import List, Dict, Any, Optional, Union
# We assume PyQt5 is used based on QFileDialog in browse_directory
from PyQt5 import QtWidgets, QtCore, QtGui
from config_reader import  BUCKET_NAME
from search_utilities import get_storage_client
import time
import hashlib
import binascii, base64
from ui_setup import isLTR
from PyQt5.QtWidgets import QMessageBox
from config_reader import cloud_storage_provider
import boto3  # Make sure to pip install boto3
from botocore.exceptions import ClientError
#arn:aws:iam::038715112888:user/Admin
# Add a flag to your config or class
USE_AWS = cloud_storage_provider == "Amazon"  # Your existing flag
# Set your flag here based on your environment



# Global client variables
gcs_client: Optional[storage.Client] = None
s3_client: Any = None
KMS_KEY_ARN = "arn:aws:kms:ap-southeast-2:038715112888:key/82ae7f3a-eb41-4f29-bd2c-85b9ab573023"



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
    normalized_prefix = self.current_path.strip('/').replace('\\', '/')
    if normalized_prefix and not normalized_prefix.endswith('/'):
        normalized_prefix += '/'

    if USE_AWS:
        return browse_s3_path_logic(normalized_prefix)
    else:
        return browse_gcs_path(self)


def browse_s3_path_logic(prefix: str) -> Dict[str, List[str]]:
    """AWS S3 implementation: returns a list of folder names just like GCS."""
    client = get_s3_client()
    try:
        # Delimiter='/' tells S3 to group files into virtual folders
        response = client.list_objects_v2(
            Bucket=BUCKET_NAME,
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


def browse_gcs_path_logic(prefix: str) -> Dict[str, List[str]]:
    """Your original GCS logic wrapped for the switchboard."""
    global gcs_client
    if gcs_client is None:
        gcs_client = get_storage_client()

    try:
        bucket = gcs_client.bucket(BUCKET_NAME)
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



def upload_to_cloud(local_folder, filename, prefix=""):
    """Securely uploads to the active cloud."""
    local_path = os.path.join(local_folder, filename)
    target_key = f"{prefix}/{filename}".replace("//", "/")
    hex_md5, b64_md5 = get_local_hashes(local_path)

    if USE_AWS:
        client = get_s3_client()
        client.upload_file(
            local_path, BUCKET_NAME, target_key,
            ExtraArgs={
                'ServerSideEncryption': 'aws:kms',
                'SSEKMSKeyId': KMS_KEY_ARN,
                'Metadata': {'md5-hash': hex_md5}
            }
        )
    else:
        # Existing GCS Upload logic
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(target_key)
        blob.md5_hash = b64_md5
        blob.upload_from_filename(local_path)



def browse_s3_logic(prefix: str) -> Dict[str, List[str]]:
    """AWS S3 implementation of folder browsing."""
    try:
        # Note: Boto3 uses 'CommonPrefixes' for virtual folders
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
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


def browse_s3_path(prefix: str) -> Dict[str, List[str]]:
    """AWS S3 implementation of folder browsing."""
    try:
        s3_client = boto3.client('s3')  # Uses your aws configure credentials
        # Delimiter='/' is what tells S3 to 'act' like a folder system
        response = s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
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

def check_sync(local_path, bucket_name, prefix=""):
    if USE_AWS:
        res = check_sync_s3(local_path, bucket_name, prefix=prefix)
    else:
        res = check_sync_gcs(local_path, bucket_name, prefix=prefix)

    return res

def check_sync_gcs(local_path, bucket_name, prefix=""):
    """Compare local files with GCS bucket contents."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # Collect local files
    local_files = {}
    for root, _, files in os.walk(local_path):
        for f in files:
            if f.startswith("$") or f.startswith("~$"):  # skip hidden/temp files
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, local_path).replace("\\", "/")
            local_files[rel_path] = md5_of_file(full_path)

    # Collect GCS blobs
    gcs_files = {}
    for blob in bucket.list_blobs(prefix=prefix):
        # GCS md5Hash is base64-encoded; decode to hex
        name1= blob.name
        name1 = name1.replace(prefix, "")
        name1 = name1.rstrip("/")
        name1 = name1.lstrip("/")

        if blob.md5_hash:
            gcs_files[name1] = blob.md5_hash

    # Compare sets
    missing_in_gcs = set(local_files) - set(gcs_files)
    missing_locally = set(gcs_files) - set(local_files)
    #mismatched = [f for f in local_files if f in gcs_files and local_files[f] != gcs_files[f]]

    # Use a regular for loop for clarity
    mismatched_files = []  # Track mismatches for the return dict

    for filename in local_files:
        if filename in gcs_files:
            if local_files[filename] != gcs_files[filename]:
                mismatched_files.append(filename)  # Keep track of the mismatch

                # 1. Create the Pop-up Box
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Question)
                # Ensure text direction follows your LTR setting
                msg.setLayoutDirection(QtCore.Qt.LeftToRight if isLTR else QtCore.Qt.RightToLeft)

                msg.setWindowTitle("Sync Mismatch" if isLTR else "אי התאמה בסנכרון")
                msg.setText(f"File changed: {filename}" if isLTR else f"קובץ השתנה: {filename}")
                msg.setInformativeText("Upload to bucket?" if isLTR else "להעלות לענן?")
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

                # 2. Handle the User's Choice
                if msg.exec_() == QMessageBox.Ok:
                    # 3. Call the updated function with the bucket object
                    upload_to_bucket(bucket, local_path, filename, prefix)

                    success_msg = QMessageBox()
                    success_msg.setText("Upload successful!" if isLTR else "העלאה הצליחה!")
                    success_msg.exec_()
                else:
                    print(f"Upload cancelled for {filename}")

    sync1 = not missing_locally and not missing_in_gcs and not mismatched_files

    return {
        "missing_in_gcs": missing_in_gcs,
        "missing_locally": missing_locally,
        "mismatched": mismatched_files,  # Now correctly populated
        "sync!": sync1
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

    if prefix and not prefix.endswith('/'):
        prefix += '/'

    paginator = s3_client.get_paginator('list_objects_v2')

    # REMOVED Delimiter='/' to allow recursion into subfolders
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get('Contents', []):
            full_key = obj['Key']

            if full_key == prefix:
                continue

            # This now preserves the subfolder path:
            # e.g., '2022/file.pdf' instead of just 'file.pdf'
            name = full_key[len(prefix):]

            if name.startswith('$') or name.startswith('~$') or name.startswith('$~') or '~$' in name or '$~' in name:
                continue

            try:
                head = s3_client.head_object(Bucket=bucket_name, Key=full_key)
                md5_hash = head.get('Metadata', {}).get('md5-hash')
                cloud_files[name] = md5_hash

            except Exception as e:
                print(f"Error fetching metadata for {full_key}: {e}")

    return cloud_files

# Usage
def get_cloud_files_with_metadata(bucket_name, prefix):
    # Use your authenticated client
    s3_client = get_s3_client()
    cloud_files = {}

    # Ensure prefix ends with /
    if prefix and not prefix.endswith('/'):
        prefix += '/'

    # 1. List all objects in the prefix
    paginator = s3_client.get_paginator('list_objects_v2')

    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix, Delimiter='/'):
        # Process files (Contents)
        for obj in page.get('Contents', []):
            full_key = obj['Key']

            # Skip the folder placeholder itself
            if full_key == prefix:
                continue

            # Extract the clean filename (abc.pdf instead of גירושין/abc.pdf)
            name = full_key[len(prefix):]

            # Filter out temporary/system files
            if name.startswith('$') or name.startswith('~$'):
                continue

            try:
                # 2. Fetch the MD5 stored in metadata during upload
                #head = s3_client.head_object(Bucket=bucket_name, Key=full_key)

                # S3 returns metadata keys in lowercase
                #md5_hash = head.get('Metadata', {}).get('md5-hash')
                etag_md5 = obj.get('ETag').strip('"')
                # Add to our dictionary
                cloud_files[name] = etag_md5

            except Exception as e:
                print(f"Error fetching metadata for {full_key}: {e}")

    return cloud_files

def check_sync_s3(local_path, bucket_name, prefix=""):
    """Compare local files with Cloud contents (GCS or S3) keeping original return format."""


    client = get_s3_client()

    # 1. Collect local files (Hex for S3, B64 for GCS)
    local_files = {}
    for root, _, files in os.walk(local_path):
        for f in files:
            if f.startswith("$") or f.startswith("~$"):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, local_path).replace("\\", "/")

            # Using your existing get_local_hashes function
            hex_md5, b64_md5 = get_local_hashes(full_path)
            local_files[rel_path] = hex_md5

    # 2. Collect Cloud files
    cloud_files1 = get_cloud_files_with_metadata(bucket_name, prefix)
    cloud_files = get_cloud_files_recursive(bucket_name, prefix)
    # 3. Compare sets using YOUR original keys
    missing_in_gcs = set(local_files) - set(cloud_files)  # "GCS" name kept for your UI
    missing_locally = set(cloud_files) - set(local_files)

    mismatched_files = []

    for filename in local_files:
        if filename in cloud_files:
            if local_files[filename] != cloud_files[filename]:
                #mismatched_files.append(filename)

                # YOUR original Popup Logic

                msg = QMessageBox()
                msg.setIcon(QMessageBox.Question)
                msg.setLayoutDirection(QtCore.Qt.LeftToRight if isLTR else QtCore.Qt.RightToLeft)
                msg.setWindowTitle("Sync Mismatch" if isLTR else "אי התאמה בסנכרון")
                msg.setText(f"File changed: {filename}" if isLTR else f"קובץ השתנה: {filename}")
                msg.setInformativeText("Upload to bucket?" if isLTR else "להעלות לענן?")
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

                if msg.exec_() == QMessageBox.Ok:
                    # Uses the unified uploader we fixed earlier
                    upload_to_cloud(local_path, filename, prefix)
                    success_msg = QMessageBox()
                    success_msg.setText("Upload successful!" if isLTR else "העלאה הצליחה!")
                    success_msg.exec_()

    sync1 = not missing_locally and not missing_in_gcs and not mismatched_files

    # RETURNS YOUR ORIGINAL DICT KEYS
    return {
        "missing_in_gcs": missing_in_gcs,
        "missing_locally": missing_locally,
        "mismatched": mismatched_files,
        "sync!": sync1
    }

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
    timer0 = time.time()

    global gcs_client

    # Check 1: If the client already exists, return it instantly (0 seconds)
    if gcs_client is None:
        gcs_client = get_storage_client()

    if gcs_client is None:
        return {"folders": []}

    # 1. Normalize the prefix path
    normalized_prefix = path_prefix.strip('/').replace('\\', '/')
    if normalized_prefix and not normalized_prefix.endswith('/'):
        normalized_prefix += '/'

    try:

        bucket = gcs_client.bucket(BUCKET_NAME)
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
        provider = "Amazon S3" if USE_AWS else "Google Cloud"
        self.setWindowTitle(f"Browse {provider} Bucket")
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

    print(f"Starting test with USE_AWS={USE_AWS} on Bucket: {BUCKET_NAME}")

    dialog = GCSBrowserDialog()
    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        final_path = dialog.selected_path()
        print(f"USER SELECTED PATH: {final_path}")
        QtWidgets.QMessageBox.information(None, "Selection", f"You chose: {final_path}")
    else:
        print("User cancelled selection.")

    sys.exit(0)