import os, re
from typing import Dict, List, Any
from config_reader import BUCKET_NAME  # וודא שזה מיובא
from azure.storage.blob import BlobServiceClient
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential



class AzureManager:
    def __init__(self):
        # טעינת המפתחות ממשתני הסביבה
        self.blob_conn_str = os.getenv("azuresmartsearch3key1conn")
        self.search_endpoint = "https://smart-search-service3.search.windows.net" #os.getenv("AZURE_SEARCH_ENDPOINT")
        self.search_key = os.getenv("azure-key-search")
        self.index_name = os.getenv("AZURE_SEARCH_INDEX", "ocr-index")



    def get_blob_service(self):
        """מחליף את get_azure_client הישנה - לצורך העלאת קבצים"""
        try:
            if not self.blob_conn_str:
                print("⚠️ Missing Blob Connection String")
                return None
            return BlobServiceClient.from_connection_string(self.blob_conn_str)
        except Exception as e:
            print(f"❌ Error initializing Blob Client: {e}")
            return None

    def get_search_client(self):
        """מחליף את get_azure_search_client - לצורך חיפוש ב-Endpoint"""
        try:
            if not all([self.search_endpoint, self.search_key]):
                print("⚠️ Missing Search Credentials (Endpoint or Key)")
                return None
            return SearchClient(
                self.search_endpoint,
                self.index_name,
                AzureKeyCredential(self.search_key)
            )
        except Exception as e:
            print(f"❌ Error initializing Search Client: {e}")
            return None

# יצירת המופע שבו נשתמש בכל האפליקציה
azure_provider = AzureManager()

def browse_azure_path_logic(prefix: str) -> Dict[str, List[str]]:
    """Azure implementation: returns a list of virtual folders."""
    client = azure_provider.get_blob_service()
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


def match_line(text, words, mode="any", match_type="partial"):
    if not words: return False
    # Handle Full vs Partial match
    if match_type == "full":
        patterns = [rf'\b{re.escape(w)}\b' for w in words]
    else:
        patterns = [re.escape(w) for w in words]

    # Handle All vs Any logic
    if mode == "all":
        return all(re.search(p, text, re.IGNORECASE) for p in patterns)
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def highlight_matches_html(text, words, match_type="partial"):
    highlighted = text
    for w in words:
        pattern = rf'\b{re.escape(w)}\b' if match_type == "full" else re.escape(w)
        highlighted = re.sub(pattern, lambda m: f"<mark>{m.group()}</mark>", highlighted, flags=re.IGNORECASE)
    return highlighted


def split_into_paragraphs(text):
    return [p.strip() for p in text.split('\n\n') if p.strip()]


def find_paragraph_position_in_pages(paragraph, pages):
    # ניקוי רווחים מיותרים מהפסקה לחיפוש גמיש יותר
    clean_para = re.sub(r'\s+', ' ', paragraph).strip()

    for page_entry in pages:
        full_page_text = " ".join(page_entry.get("lines", []))
        clean_page = re.sub(r'\s+', ' ', full_page_text)

        if clean_para in clean_page:
            return page_entry.get("page", 1), 1
    return 1, 1

'''
def get_azure_ai_response(query):
    # This setup connects the AI model directly to your Blob storage index
    endpoint = "https://your-resource-name.openai.azure.com/"
    api_key = os.environ.get("AZURE_OPENAI_KEY")
    #https: // orenma - smartsearch - resource.services.ai.azure.com / api / projects / orenma - smartsearch
    client = openai.AzureOpenAI(
        base_url=f"{endpoint}/openai/deployments/gpt-4o/extensions",
        api_key=api_key,
        api_version="2024-02-15-preview",
    )

    response = client.chat.completions.create(
        model="gpt-4o",  # Your deployment name
        messages=[{"role": "user", "content": query}],
        extra_body={
            "data_sources": [
                {
                    "type": "azure_search",
                    "parameters": {
                        "endpoint": "https://smart-search-service3.search.windows.net",
                        "index_name": os.getenv("AZURE_SEARCH_INDEX", "ocr-index"),
                        "authentication": {
                            "type": "api_key",
                            "key": os.environ.get("AZURE_SEARCH_KEY")
                        },
                        "query_type": "vector_simple_hybrid",  # Best for finding JSON/Docs
                        "in_scope": True,
                        "strictness": 3,
                        "top_n_documents": 5
                    }
                }
            ]
        }
    )

    return response.choices[0].message.content
'''

def search_in_json_content(path, pages_list, words, mode, search_mode):
    results = []
    for p_idx, page_data in enumerate(pages_list):
        pnum = page_data.get("page_number") or page_data.get("page", p_idx + 1)
        lines = page_data.get("lines", [])
        l = len(lines)
        i = 0
        while i < l:
            ln = lines[i]
            if match_line(ln, words, 'any', search_mode):  # שימוש ב-match_line הקיים שלך
                start_index = max(0, i - 1)
                end_index = min(i + 2, l)
                context_lines = lines[start_index:end_index]
                context_text = " ".join(context_lines)

                if match_line(context_text, words, mode, search_mode):
                    # יצירת ה-HTML המעוצב
                    pre = f"<span style='color:blue;'>— עמוד {pnum} — שורות {start_index + 1}-{end_index}</span>"
                    path_url = path.replace('\\', '/')
                    # הלינק מותאם למה שה-GUI שלך מצפה
                    open_link = f"<a href='filepage:///{path_url}?page={pnum}' style='color:green; text-decoration: none;'>[פתח קובץ]</a>"

                    full_paragraph = (
                            f"{path}  {pre} {open_link}<br><br>" +
                            "<br>".join(context_lines).replace(".₪", "₪.").replace(",₪", "₪,") + "<br>"
                    )
                    results.append(full_paragraph)
                    i += 2
            i += 1
    return results
