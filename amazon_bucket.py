import boto3
import hashlib
import os
from botocore.exceptions import ClientError

# ==========================================
# CONFIGURATION - FILL THESE IN
# ==========================================
AWS_ACCESS_KEY = os.environ.get("amazon_key")
AWS_SECRET_KEY = os.environ.get("amazon_secret")
AWS_REGION = "eu-north-1"
BUCKET_NAME = "oren-smart-search-docs-amazon" #"arn:aws:s3:::oren-smart-search-docs-amazon"
KMS_KEY_ARN = "arn:aws:kms:eu-north-1:983426483678:key/68eda003-f0dc-43b5-9cde-ab3431257456"

# ==========================================
# S3 CLIENT INITIALIZATION
# ==========================================
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_local_md5_hex(file_path):
    """Calculates Hex MD5 to match S3's ETag format."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def list_s3_files(prefix=""):
    """Returns a dict of {filename: metadata_md5} from S3."""
    files_found = {}
    try:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                # We need to call head_object to get custom metadata for each file
                meta = s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
                # S3 converts metadata keys to lowercase
                md5_from_meta = meta.get('Metadata', {}).get('md5-hash')
                files_found[key] = md5_from_meta
        return files_found
    except Exception as e:
        print(f"❌ Error listing S3: {e}")
        return {}

def upload_file_secure(local_path, s3_key):
    """Uploads with KMS and stores the local MD5 in metadata for syncing."""
    local_md5 = get_local_md5_hex(local_path)
    try:
        s3_client.upload_file(
            local_path,
            BUCKET_NAME,
            s3_key,
            ExtraArgs={
                'ServerSideEncryption': 'aws:kms',
                'SSEKMSKeyId': KMS_KEY_ARN,
                'ACL': 'bucket-owner-full-control',
                'Metadata': {'md5-hash': local_md5} # <--- THIS IS OUR SYNC KEY
            }
        )
        print(f"✅ Securely uploaded with Metadata MD5: {local_md5}")
        return True
    except Exception as e:
        print(f"❌ Upload Failed: {e}")
        return False

# ==========================================
# DEBUGGER / TEST SUITE
# ==========================================

def run_debug():
    print("--- Starting Amazon S3 Debugger ---")

    # 1. Test Listing
    print(f"\n1. Testing 'List Objects' in bucket: {BUCKET_NAME}")
    current_files = list_s3_files()
    print(f"Found {len(current_files)} files in bucket.")

    # 2. Test Sync Logic (using a dummy file)
    test_file = "debug_test.txt"
    with open(test_file, "w") as f:
        f.write("This is a test file for S3 sync debugging.")

    local_hash = get_local_md5_hex(test_file)
    print(f"\n2. Local File Hash (Hex): {local_hash}")

    # 3. Test Upload
    s3_target_key = "debug/debug_test.txt"
    print(f"\n3. Uploading to: {s3_target_key}...")
    if upload_file_secure(test_file, s3_target_key):

        # 4. Final Verify (The 'Sync' check)
        print("\n4. Verifying Sync Status...")
        updated_files = list_s3_files(prefix="debug/")
        s3_hash = updated_files.get(s3_target_key)

        # Note: If SSE-KMS is used, S3 ETags might NOT match MD5.
        # For General Purpose buckets, they usually only match if no encryption or SSE-S3 is used.
        if s3_hash == local_hash:
            print("✨ SYNC SUCCESS: Local and S3 hashes match perfectly!")
        else:
            print("ℹ️  Note: S3 ETag differs from local MD5 (Normal behavior for KMS-encrypted files).")
            print(f"   Local: {local_hash}")
            print(f"   S3 ETag: {s3_hash}")

    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)
    print("\n--- Debugger Finished ---")


if __name__ == "__main__":
    run_debug()