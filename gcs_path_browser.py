import os
from google.cloud import storage
from typing import List, Dict, Any, Optional, Union
# We assume PyQt5 is used based on QFileDialog in browse_directory
from PyQt5 import QtWidgets, QtCore, QtGui
from config_reader import  BUCKET_NAME
from search_utilities import get_storage_client
import time


# ==============================================================================
# GCS CORE BROWSER FUNCTION
# ==============================================================================
gcs_client: Optional[storage.Client] = None

def browse_gcs_path(path_prefix: str = "") -> Dict[str, List[str]]:
    """
    Lists the virtual directories (prefixes) and  (blobs) at a given GCS path.
    """

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
        self.setWindowTitle("Browse GCS Bucket")
        self.setGeometry(100, 100, 600, 400)
        self.current_path = initial_path.strip('/').replace('\\', '/')
        self.selected_path = None

        # Widgets
        self.path_label = QtWidgets.QLabel("Path: /")
        self.list_widget = QtWidgets.QListWidget()
        self.ok_button = QtWidgets.QPushButton("Select Folder")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.up_button = QtWidgets.QPushButton("Up")

        # Layout
        path_layout = QtWidgets.QHBoxLayout()
        path_layout.addWidget(self.up_button)
        path_layout.addWidget(self.path_label)

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
        self.path_label.setText(f"Path: {display_path}/")

        contents = browse_gcs_path(self.current_path)

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

