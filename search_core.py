import os
import time
import re
import json
import io
import traceback  # Ensure this is imported for logging stack traces
from google.cloud import storage
from google.cloud import vision_v1 as vision
from google import genai
from google.genai import errors
from flask import Flask, request, jsonify
#import  pdfplumber
from docx import Document
from pypdf import PdfReader
from typing import List, Dict, Any, Tuple
import threading


from search_utilities import (get_gcs_files_context_cache, initialize_document_cache, initialize_all_clients, get_gcs_bucket, get_storage_client_instance,
                              get_vision_client_instance, get_gemini_client_instance)
from config_reader import BUCKET_NAME

# ==============================================================================
# --- GLOBAL STATE FOR FALLBACK CACHING ---
# ==============================================================================


from document_parsers import extract_docx_with_lines, find_all_word_positions_in_pdf, split_into_paragraphs, match_line, highlight_matches_html, find_paragraph_position_in_pages
# ... existing configurations ...

#

DOCUMENT_CACHE = {} # <-- NEW: This will store extracted text to prevent re-downloading

# --- Global Shared State ---

# 3. CACHE_STATUS: Flag to track the readiness of the cache.
# Possible values: "PENDING", "READY", "FAILED".
CACHE_STATUS = "PENDING"  # To track the state
cache_lock = threading.Lock() # To safely manage global state updates
cache_thread: threading.Thread | None = None # To hold the background thread instance
timer1 = 0




def simple_keyword_search(query: str,
                          directory_path: str = "",
                          mode="any",
                          match_type="partial",
                          show_mode="line"):
    """
    Simple non-AI keyword search:
    - mode: 'any' or 'all'
    - match_type: 'partial' or 'full'
    - show_mode: 'line' or 'paragraph'
    """
    documents = get_gcs_files_context_cache(directory_path, BUCKET_NAME, query)


    if not documents:
        return {
            "status": "ok",
            "details": f"No usable documents found in '{directory_path}'.",
            "matches": []
        }
    debug_str = ""
    # Split query into separate words
    words = [w.strip() for w in query.split() if w.strip()]
    if not words:
        return {"status": "ok", "details": "Empty query", "matches": []}

    results = []

    for doc in documents:
        matched_items = []          # text (line or paragraph)
        matched_items_html = []     # highlighted HTML
        match_positions = []        # {"page": p, "line": line_idx}

        # --- Normalize pages defensively (so we don't crash) ---
        raw_pages = doc.get("pages")

        pages = []

        if isinstance(raw_pages, list):
            if raw_pages and isinstance(raw_pages[0], dict) and "lines" in raw_pages[0]:
                pages = raw_pages
            elif raw_pages and isinstance(raw_pages[0], str):
                pages = [{"page": 1, "lines": raw_pages}]
        elif isinstance(raw_pages, str):
            pages = [{"page": 1, "lines": raw_pages.split("\n")}]

        if not pages:
            content = doc.get("content", "")
            pages = [{"page": 1, "lines": content.split("\n")}]

        # =========================
        #   LINE MODE (unchanged)
        # =========================
        if show_mode == "line":

            for page_entry in pages:
                page_num = page_entry.get("page", 1)
                lines = page_entry.get("lines", []) or []

                for line_idx, line in enumerate(lines, start=1):
                    if match_line(line, words, mode=mode, match_type=match_type):
                        matched_items.append(line)
                        matched_items_html.append(
                            highlight_matches_html(line, words, match_type=match_type)
                        )
                        match_positions.append({
                            "page": page_num,
                            "line": line_idx
                        })
        # =========================
        #   PARAGRAPH MODE
        # =========================
        else:
            # Restore ORIGINAL behavior: use your split_into_paragraphs on doc["content"]
            content = doc.get("content", "")
            paragraphs = split_into_paragraphs(content)

            for paragraph in paragraphs:
                if match_line(paragraph, words, mode=mode, match_type=match_type):
                    matched_items.append(paragraph)
                    matched_items_html.append(
                        highlight_matches_html(paragraph, words, match_type=match_type)
                    )

                    # NEW: find (page, line) for this paragraph using pages
                    page_num, line_idx = find_paragraph_position_in_pages(paragraph, pages)
                    match_positions.append({
                        "page": page_num,
                        "line": line_idx
                    })

        if matched_items:
            results.append({
                "file": doc["name"],
                "full_path": doc["full_path"],
                "matches": matched_items,
                "matches_html": matched_items_html,
                "match_positions": match_positions
            })

    return {
        "debug": debug_str,
        "status": "ok",
        "query": query,
        "directory_path": directory_path,
        "mode": mode,
        "match_type": match_type,
        "show_mode": show_mode,
        "matches": results
    }


def perform_search(query: str, directory_path: str = ""):
    """
    Performs the RAG search, now using the cache and context filtering
    to drastically improve speed.
    """
    global CACHE_STATUS, cache_lock
    timer = time.time()  # Start timer
    gemini_client = get_gemini_client_instance()

    if not gemini_client:
        return {"status": "Fallback", "details": "Gemini client not initialized. Check API Key."}

    # 1. CHECK CACHE STATUS
    with cache_lock:
        cache_is_ready = CACHE_STATUS in ["READY", "EMPTY_SUCCESS"]

    # 2. DOCUMENT RETRIEVAL (FAST CACHE PATH vs. SLOW FALLBACK)
    documents = get_gcs_files_context_cache(directory_path, BUCKET_NAME, "")

    if not documents:
        return {
            "query": query,
            "status": "Success",
            "response": "אין מסמכים.",  # Hebrew Fallback
            "sources": [],
            "debug": f"No relevant context found by keyword pre-filter. Time: {round(time.time() - timer, 2)}s."
        }
    final_prompt_context = documents

    document_context = ""
    for doc in documents:
        document_context += f"File: {doc['name']}\nFull Path: {doc['full_path']}\nContent:\n{doc['content']}\n---\n"

        final_prompt_context = document_context
        sources_list = [doc['name'] for doc in documents]

    # 3. Prepare Final Prompt for Gemini (Same as your old logic)
    system_instruction = (
        "You are a helpful assistant. Provide the answer in Hebrew (עברית). "
        "Use ONLY the provided document text as context "
        "to answer the question. If the information is not in the text, reply #$$$#"
    )

    final_prompt = (
        f"DOCUMENT CONTEXT:\n---\n{final_prompt_context}\n---\n\n"
        f"QUESTION: {query}"
    )

    # 4. Call Gemini API with Fallback Logic (Your working code)
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[final_prompt],
            config={"system_instruction": system_instruction}
        )
        print("✅ Response received from gemini-2.5-flash.")

    except errors.APIError as e:
        if '503 UNAVAILABLE' not in str(e) and '500' not in str(e):
            print(f"Non-503/500 Gemini API Error: {e}")
            traceback.print_exc()
            return {
                "status": "API Error",
                "details": f"Check your request or API configuration. Error: {e}"
            }

        # Attempt 2: gemini-2.5-pro (Fallback)
        print("⚠️ gemini-2.5-flash overloaded. Falling back to gemini-2.5-pro...")
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=[final_prompt],
                config={"system_instruction": system_instruction}
            )
            print("✅ Response received from gemini-2.5-pro (Fallback Success).")
        except Exception as fallback_e:
            print(f"❌ Fallback to gemini-2.5-pro failed: {fallback_e}")
            traceback.print_exc()
            return {
                "status": "API Error",
                "details": f"Both models are unavailable. Error: {fallback_e}"
            }

    except Exception as e:
        print(f"Unhandled non-API error: {e}")
        return {
            "status": "API Error",
            "details": f"An unknown error occurred: {e}"
        }

    # Success: Return the result
    response_text = response.text.replace("#$$$#", "המידע אינו נמצא במסמכים שסופקו.")
    return {
        "query": query,
        "status": "Success (RAG)",
        "response": response_text,
        "sources": sources_list,  # Use the list generated in Step 2
        "debug": f"Search mode: {search_mode if cache_is_ready else 'SLOW FALLBACK'}. Total time: {round(time.time() - timer, 2)}s."
    }



def start_cache_thread(directory_path: str):
    """
    Starts the background thread responsible for populating the cache ONLY IF
    it is not already running or finished successfully.
    """
    global cache_thread, CACHE_STATUS

    with cache_lock:
        print(f"START-CACHE: Lock acquired. Current Status: {CACHE_STATUS}. Thread Alive: {cache_thread and cache_thread.is_alive()}")

        # Check if the existing thread is dead (stale)
        is_thread_stale = cache_thread and not cache_thread.is_alive()

        # Condition to start the thread:
        # 1. Status is an initial/failure state (PENDING, FAILED, EMPTY_SUCCESS)
        # 2. OR the thread is stale AND the status is stuck on WARMING_UP (retry needed)
        if CACHE_STATUS in ["PENDING", "FAILED", "EMPTY_SUCCESS"] or (is_thread_stale and CACHE_STATUS == "WARMING_UP"):

            if is_thread_stale and CACHE_STATUS != "READY":
                print("START-CACHE: Previous thread finished with non-READY status or stalled. Retrying initialization.")

            CACHE_STATUS = "WARMING_UP"
            print(f"START-CACHE: Setting Status to WARMING_UP and launching thread...")

            # Directory path is currently ignored in initialize_document_cache as per your setup, but kept for future proofing.
            cache_thread = threading.Thread(
                target=initialize_document_cache,
                args=(directory_path,),
                daemon=False
            )
            cache_thread.start()
            print("START-CACHE: Thread launched successfully.")
            return True
        else:
            print(f"START-CACHE: Cache thread already running or ready (Status: {CACHE_STATUS}). Skipping launch.")
            return False
# --- Flask Application Setup ---

app = Flask(__name__)

if not initialize_all_clients():
    print("LOG: Request failed - Service initialization failed. Check server logs for IAM/API Key errors.")

timer0 = time.time()
@app.route('/cache_status', methods=['GET'])
def get_cache_status():
    """Returns the current status of the document cache."""


    with cache_lock:
        current_status = CACHE_STATUS
        doc_count = len(DOCUMENT_CACHE)
        cPROCESS_PROGRESS = PROCESS_PROGRESS
        cGLOBAL_CACHE_PROGRESS = GLOBAL_CACHE_PROGRESS

    status_data = {
        "status": current_status,
        "document_count": doc_count,
        "time_since_app_start_s": round(time.time() - timer1, 2),
        "cache": cGLOBAL_CACHE_PROGRESS,
        "process": cPROCESS_PROGRESS
    }
    return jsonify(status_data)


@app.route('/simple_search', methods=['POST'])


def simple_search_endpoint():
    # 1. Ensure the cache thread is started non-blocking (if needed)
    global timer1
    start_cache_thread("")

    timer1 = time.time()
    time_stamp = ""

    # --- Setup and Validation ---
    data = request.get_json(silent=True) or {}
    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()
    config = data.get("search_config", {})

    mode = config.get("word_logic", "any")
    match_type = config.get("match_type", "partial")
    show_mode = config.get("show_mode", "paragraph")

    if not query or not directory_path:
        return jsonify({"error": "Missing 'query' or 'directory_path' in request."}), 400

    global CACHE_STATUS

    # 2. Acquire status safely to decide the path
    with cache_lock:
        current_status = CACHE_STATUS
        cache_is_ready = current_status in ["READY", "EMPTY_SUCCESS"]

    # 3. Decision Tree: Fallback (Slow) or Cache (Fast)?
    cache_is_ready = True
    if cache_is_ready:

        # --- SLOW FALLBACK PATH (Synchronous GCS Call) ---
        print(f"LOG: Cache Status: '{current_status}'. Executing slow GCS search.")
        try:
            result = simple_keyword_search(
                query,
                directory_path,
                mode=mode,
                match_type=match_type,
                show_mode=show_mode
            )

            time_stamp += f"{round(100 * (time.time() - timer1)) / 100} sec "
            time_stamp += f" new simple_keyword_search={round(100 * (time.time() - timer1)) / 100},"
            time_stamp += CACHE_STATUS

            if "debug" in result:
                result["debug"] += time_stamp
            else:
                result["debug"] = time_stamp

            return jsonify(result), 200

        except Exception as e:
            print(f"ERROR in simple_keyword_search fallback: {e}")
            traceback.print_exc()
            return jsonify({"error": f"Fallback search failed: {str(e)}"}), 500

    else:
        # --- FAST CACHED PATH (In-memory Call) ---
        print(f"LOG: Cache Status: '{current_status}'. Executing fast cached search.")
        try:
            return jsonify({"error": f"Cached not ready"}), 500

        except Exception as e:
            print(f"ERROR in simple_search_endpoint (cached search): {e}")
            traceback.print_exc()
            return jsonify({"error": f"Cached search failed: {str(e)}"}), 500



@app.route('/search', methods=['POST'])
def search_endpoint():
    start_cache_thread("")
    data = request.get_json(silent=True)

    if data is None:
        print("LOG: Request failed - Invalid JSON or missing Content-Type header.")
        return jsonify({"error": "Invalid JSON or missing 'Content-Type: application/json' header."}), 400

    query = data.get('query', '').strip()
    directory_path = data.get('directory_path', '').strip()

    if not query:
        print(f"LOG: Request failed - Query missing. Received data: {data}")
        return jsonify({"error": "No search query ('query') provided."}), 400

    try:
        results = perform_search(query, directory_path)
        print(f"LOG: Successful search for query: '{query}' in path: '{directory_path}'")

        if results.get("status") in ["API Error", "Fallback"]:
            return jsonify(results), 500

        return jsonify(results), 200

    except Exception as e:
        print(f"--- ERROR IN search_endpoint ---")
        print(traceback.format_exc())
        print(f"-------------------------------")
        return jsonify({"error": "Internal server error during search process. Check server logs for details."}), 500