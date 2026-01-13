import os
from typing import Dict, List, Any
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from config_reader import BUCKET_NAME  # וודא שזה מיובא


def get_azure_client():
    """Initializes and returns the Azure Blob Storage client."""
    try:
        # שים לב: וודא שהשם של משתנה הסביבה תואם למה שהגדרת ב-App Runner/OS
        connection_string = os.getenv("Azuresmartsearch3key1conn")

        if not connection_string:
            print("FATAL: AZURE_STORAGE_CONNECTION_STRING is not set.")
            return None

        return BlobServiceClient.from_connection_string(connection_string)
    except Exception as e:
        print(f"FATAL: Could not initialize Azure client. Error: {e}")
        return None


def browse_azure_path_logic(prefix: str) -> Dict[str, List[str]]:
    """Azure implementation: returns a list of virtual folders."""
    client = get_azure_client()
    if not client:
        return {"folders": []}

    container_client = client.get_container_client(BUCKET_NAME)

    try:
        # ב-Azure walk_blobs מחזיר Blobs וגם BlobPrefix (שזה התיקיות)
        blobs = container_client.walk_blobs(name_starts_with=prefix, delimiter='/')

        folders = []
        for blob in blobs:
            # ב-walk_blobs, תיקייה היא אובייקט שאין לו תכונות של Blob רגיל
            # או שהשם שלו מסתיים ב-/
            if hasattr(blob, 'name') and blob.name.endswith('/'):
                folder_full_path = blob.name.rstrip('/')
                folder_name = folder_full_path.split('/')[-1]
                if folder_name:
                    folders.append(folder_name)
            # דרך נוספת לזהות תיקייה ב-walk_blobs:
            elif not hasattr(blob, 'size'):  # BlobPrefix object
                folder_full_path = blob.name.rstrip('/')
                folder_name = folder_full_path.split('/')[-1]
                folders.append(folder_name)

        return {"folders": sorted(list(set(folders)))}  # הסרת כפילויות ומיון
    except Exception as e:
        print(f"Azure Browse Error: {e}")
        return {"folders": []}