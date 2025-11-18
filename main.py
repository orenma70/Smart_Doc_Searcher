import sys
import os
import json
import requests
from PyQt5 import QtWidgets, QtCore, QtGui
from pdf2image import convert_from_path
from PIL import Image # Used to handle the image object
from docx import Document
#   from PyPDF2 import PdfReader
import pypdf
import re
import docx2txt
import ui_setup  # import your setup module
import win32com.client as win32
import pdfplumber
import unicodedata
from typing import List, Any, Set, Dict
import subprocess
import ctypes  # <-- NEW: Import ctypes for low-level Windows API call
from urllib.parse import urlparse, unquote
import mimetypes
from dotenv import load_dotenv
import time
import shutil

from google import genai
from google.genai.errors import APIError
from google.genai import types
import fitz  # PyMuPDF
import tempfile


# --- CONCEPTS (These would be filled by your UI state) ---
# Imagine these variables capture the user's selection from radio buttons or checkboxes.

# The server receives this JSON, reads "match_type": "fuzzy", and runs
# an algorithm that ignores the misspelling 'polisy' and matches it to 'policy'.


chat_gpt = False

api_key = os.environ.get("GEMINI_API_KEY")  # $Env:OPENAI_API_KEY = "sk-proj-vf-..."  echo $Env:OPENAI_API_KEY in power shell
MODEL_NAME = 'gemini-2.5-flash'
chat_mode = 'gemini'

CLIENT_PREFIX_TO_STRIP = "C:/a/מצרפי"

RLO = u"\u202e"
CONFIG_FILE = "config.txt"
HEADER_MARGIN = 50
FOOTER_MARGIN = 50

chatgptallfile = True #False True
# Combined pattern for any character considered a 'letter' (Latin or Hebrew)
LETTER_PATTERN = re.compile(r'[a-zA-Z\u0590-\u05FF]')
# Define a pattern to find any Hebrew character
HEBREW_PATTERN = re.compile(r'[\u0590-\u05FF]')
ENGLISH_PATTERN = re.compile(r'[a-zA-Z]')

# Pre-compile the pattern for performance
LATIN_LETTER_PATTERN = re.compile(r'[a-zA-Z]')
sequence_pattern = re.compile(r'\d+')
LATIN_LETTER_PATTERNnNum = re.compile(r'[a-zA-Z]+|\d+')

from config_reader import read_setup
API_search_URL=read_setup("API_SEARCH_URL")
API_simple_search_URL=read_setup("API_SIMPLE_SEARCH_URL")

# Function to implement in your class:
def display_keyword_matches(self, match_results):
    display_text = "<h3>Keyword Search Results</h3>"

    if not match_results:
        display_text += "<p>No matches found with the current configuration.</p>"

    for match in match_results:
        doc_name = match.get('document_name', 'Unknown Document')
        match_type = match.get('match_type', 'N/A')
        snippets = match.get('snippets', [])

        display_text += f"<hr><h4>File: {doc_name}</h4>"
        display_text += f"<p>Match Type: <b>{match_type}</b></p>"

        # Display up to the first 5 snippets for brevity
        for i, snippet in enumerate(snippets[:5]):
            display_text += f"<p>— Snippet {i + 1}: {snippet}</p>"

    return display_text

def format_simple_search_results(results_data):
    if results_data.get("status") != "ok":
        return f"🛑 שגיאה: {results_data}"

    matches = results_data.get("matches", [])
    if not matches:
        return "לא נמצאו תוצאות."

    output_lines = []

    for doc in matches:
        file_name = doc.get("file", "ללא שם")
        full_path = doc.get("full_path", "")
        match_positions = doc.get("match_positions","")
        if match_positions:
            first = match_positions[0]
            line = first["line"]
            page = first["page"]
        else:
            line = None
            page = None

        dir_only = os.path.dirname(full_path)

        lines = doc.get("matches_html", [])

        output_lines.append(f" שורה:  {line}  עמוד: {page}  📄 קובץ: {file_name}  📄 ספריה: {dir_only}   <br>")

        #output_lines.append(f"נתיב מלא: {full_path} <br>")


        for line in lines:
            output_lines.append(f"   • {line}<br>")



    return "\n".join(output_lines)


def on_search_button_clicked(self, query, directory_path):
    # הפונקציה המדויקת ששלחת, בתוספת לוגיקת עיבוד התוצאה.

    try:
        # 1. שליחת הבקשה ל-Cloud Run API

        if self.gemini_radio.isChecked():
            url = API_search_URL
            payload = {
                "query": query,
                "directory_path": directory_path
            }
        else:

            url = API_simple_search_URL
            if self.all_word_search_radio.isChecked():
                str2_mode = "all"
            else:
                str2_mode = "any"

            if self.exact_search_radio.isChecked():
                str1_mode = "full"
            else:
                str1_mode = "partial"

            if self.show_line_mode_radio.isChecked():
                str3_mode = "line"
            else:
                str3_mode = "paragraph"


            payload = {
                "query": query,
                "directory_path": directory_path,
                "search_config": {
                    "mode": "keyword",
                    "match_type": str1_mode,
                    "word_logic": str2_mode,
                    "show_mode": str3_mode
                }
            }

        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()  # לזרוק שגיאה אם הסטטוס הוא 4xx/5xx

        # 2. עיבוד התוצאה
        results_data = response.json()

        # 3. בודק אם הסטטוס הוא RAG (מ-Gemini) או Fallback (חיפוש פשוט)
        status = results_data.get('status', 'Unknown')

        formatted_output = ""

        if status.endswith('(RAG)'):
            # --- פורמט RAG (תשובה אנליטית מ-Gemini) ---
            response_text = results_data.get('response', 'הבינה המלאכותית לא סיפקה תשובה ברורה.')

            formatted_output = (
                f"✅ **תשובה אנליטית (Gemini AI)**\n"
                f"----------------------------------------\n"
                f"{response_text}\n\n"
            )

            # אם יש מקורות, ניתן להוסיף אותם כאן (כרגע הקוד לא מוציא אותם)
        elif status == "ok":

            # --- Keyword Search Mode ---
            formatted_output = format_simple_search_results(results_data)


        elif status.endswith('(Fallback)'):
            # --- פורמט Fallback (חיפוש מילות מפתח) ---

            # עדיף להציג הודעת שגיאה ברורה למה ה-RAG נכשל
            formatted_output = (
                f"⚠️ **כשל ב-RAG: המערכת נפלה לחיפוש מילות מפתח.**\n"
                f"----------------------------------------------------\n"
                f"הודעת מערכת: {results_data.get('message', 'לא נמצאו מסמכים.')}\n\n"
            )

            # הוספת הסניפטים מה-Fallback
            if results_data.get('results'):
                for result in results_data['results']:
                    formatted_output += (
                        f"📄 **{result['filename']}** (קטע רלוונטי):\n"
                        f"   {result['snippet']}\n"
                        f"----------------------------------------\n"
                    )

        else:
            # טיפול בשגיאות מה-API עצמו
            formatted_output = f"🛑 **שגיאת API או סטטוס לא ידוע:**\n{results_data.get('message', 'לא התקבלה הודעת שגיאה.')}"

        # עדכון תיבת הטקסט ב-GUI
        # (יש לוודא שאובייקט זה קיים במחלקת ה-GUI שלך)
        #self.results_text_area.setText(formatted_output)
        return formatted_output

    except requests.exceptions.RequestException as e:
        # טיפול בשגיאות חיבור לרשת או שגיאות HTTP
        error_message = f"שגיאת תקשורת עם שירות החיפוש (API):\n{e}"
        print(error_message)

        # הצגת הודעה קריטית למשתמש
        QtWidgets.QMessageBox.critical(self, "שגיאה", error_message)

def convert_pdf_page_to_pixmap(page, page_number: int):
    """
    Converts a single PDF page to a PNG byte string (pixmap)
    which can be used by PIL or sent to Gemini.
    """
    try:
        # Open the PDF document


        # Define rendering resolution (e.g., 300 DPI)
        zoom = 300 / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        # Convert page to a pixmap object (contains image data)
        pix = page.get_pixmap(matrix=matrix)

        # --- FIX IS HERE ---
        # 1. Ensure the colorspace is RGB (Crucial for robust PNG conversion)
        if pix.n > 4:  # check if the number of components is > 4
            pix = fitz.Pixmap(fitz.csRGB, pix)

        # 2. Get the raw image data as PNG bytes using the save() method
        #    and reading the bytes back, or by using a dedicated method

        # Method A: Using a dedicated method for PNG bytes (Older fitz)
        # Note: This might still raise an error, depending on your exact version.
        png_bytes = pix.tobytes()


        print(f"✅ Successfully created PNG data for page {page_number} using PyMuPDF.")
        return png_bytes

    except Exception as e:
        print(f"❌ Error converting page with PyMuPDF: {e}")
        return None


# To send to Gemini, you would use:
# image_bytes = convert_pdf_page_to_pixmap(pdf_path, 4)
# client.models.generate_content(contents=[{"mime_type": "image/png", "data": image_bytes}, question])

def convert_pdf_page_to_image(pdf_path: str, page_number: int, poppler_path: str = None) -> Image.Image:
    """
    Converts a single page of a PDF to a PIL Image object.

    Args:
        pdf_path: The full path to the PDF file.
        page_number: The 1-based index of the page to convert (e.g., 1 for the first page).
        poppler_path: Optional path to the Poppler 'bin' directory if not in system PATH.

    Returns:
        A PIL Image object of the page, or None on failure.
    """
    if not os.path.exists(pdf_path):
        print(f"❌ Error: PDF file not found at {pdf_path}.")
        return None

    doc = None
    try:
        doc = fitz.open(pdf_path)

        # fitz uses 0-based indexing, so load page_number - 1
        page = doc.load_page(page_number - 1)

        # get_images() returns a list of image objects found on the page.
        # This list includes raster images that might contain scanned text.
        image_list = page.get_images(full=True)

        if len(image_list) > 0:
            return convert_pdf_page_to_pixmap(page, page_number)
        else:
            return None
    finally:
        if doc:
            doc.close()


def should_skip_file(filename: str) -> bool:
    """Checks if a filename indicates a temporary Word lock file."""

    # The standard temporary lock file prefix is '~$', but sometimes
    # the order might vary slightly due to OS or application behavior.

    # Check for the primary temporary file prefixes:
    if filename.startswith('~$'):
        return True

    # Check for the alternate temporary file prefix (less common but good practice)
    if filename.startswith('~$'):
        return True

    return False

def display_gemini_result(self, results_area: QtWidgets.QTextEdit, answer: str, path: str):
    """
    Handles displaying the Gemini answer in the results area.

    Appends an asterisk inline if the answer is a skip condition ('#$$$#' or 'None'),
    otherwise, appends the full formatted answer in a new RTL block.

    Args:
        self: The main class instance (needed for moveCursor/insertHtml).
        results_area: The QTextEdit widget where results are displayed.
        answer: The text response from the Gemini model.
        path: The file path used for context.
    """

    # Check for skip conditions: flag or explicit 'None' string
    if ('#$$$#' in answer) or answer == 'None':
        # --- Handle Skip Condition (Insert Asterisk Inline) ---

        # Use a <span> tag (inline element) with bolding
        html_content = f"<span dir='rtl'><b>*</b></span>"

        # Move cursor to the end and insert content without a newline
        results_area.moveCursor(results_area.textCursor().End)
        results_area.insertHtml(html_content)

    else:
        # --- Handle Successful Answer (Insert Full Block) ---

        # Use <p> tags for clear line separation, relying on append() for the initial block
        formatted_html = (
            f"<p dir='rtl'><b>    Gemini :  </b></p>"
            f"<p dir='rtl'><b>  {path}   </b></p>"
            f"<p dir='rtl'>{answer}</p>"
            f"<p dir='rtl'><b>    +++++++++++++++++++++ :  </b></p>"
        )
        # The append() method creates a new block for the formatted HTML content.
        results_area.append(formatted_html)



def extract_text_from_doc(doc_path: str) -> str:
    """Extracts text from a local .doc file using textract."""
    if not os.path.exists(doc_path):
        print(f"❌ Error: File not found at {doc_path}.")
        return None

    try:
        # textract returns bytes, so decode to string
        text_bytes = textract.process(doc_path)
        return text_bytes.decode('utf-8')

    except Exception as e:
        print(f"❌ Error reading .doc file (requires external tool like antiword): {e}")
        return None






def extract_text_from_docx(docx_path: str) -> str:
    """Extracts all text from a local .docx file."""
    if not os.path.exists(docx_path):
        print(f"❌ Error: File not found at {docx_path}.")
        return None

    try:
        # Load the document
        document = Document(docx_path)
        text = []

        # Iterate through all paragraphs and append text
        for paragraph in document.paragraphs:
            text.append(paragraph.text)

        print(f"✅ Successfully extracted {len(' '.join(text).split())} words from the DOCX.")

        # Join all paragraph text into a single string
        return "\n".join(text)

    except Exception as e:
        print(f"❌ Error reading .docx file: {e}")
        return None


def extract_docx_content(docx_path: str, question: str):
    """
    Extracts text and embedded images from a DOCX file and prepares the Gemini contents list.
    """
    contents_list = []

    # 1. Create a temporary directory to save the extracted images
    with tempfile.TemporaryDirectory() as temp_dir:
        # 2. Extract text and save images to the temp directory
        try:
            full_text = docx2txt.process(docx_path, temp_dir)
        except Exception as e:
            print(f"Error during docx extraction: {e}")
            return [types.Part.from_text(f"Could not process document. Question: {question}")]

        # 3. Process and append images to the contents_list
        # FIX 1: Exclude Word lock files (starting with ~$)
        image_files = [
            f for f in os.listdir(temp_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
            and not f.startswith('~$')
        ]

        for image_file in sorted(image_files):
            image_path = os.path.join(temp_dir, image_file)

            # 🛑 FIX 2 (CRITICAL): Defensive check MUST be done BEFORE opening the file.
            # This handles the phantom second execution failure.
            if not os.path.exists(image_path):
                print(f"Skipping file {image_file}: File not found during execution.")
                continue

            # Use a try/except for *each individual image*
            try:
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()

                    # Determine MIME type
                    mime_type = 'image/jpeg' if image_file.lower().endswith(('.jpg', '.jpeg')) else 'image/png'

                    # Add the image part
                    contents_list.append(
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                    )

                    # Add the text marker
                    # FIX 3: Removed redundant 'text =' keyword for clarity.
                    contents_list.append(types.Part.from_text(text = f"--- Embedded Image: {image_file} ---"))

            except Exception as e:
                print(f"Failed to process image {image_file}: {e}")

        # --- END OF LOOP ---

        # 4. Define and append the final text prompt (only once, outside the loop)
        final_prompt = (
            f"--- EXTRACTED DOCX TEXT ---\n"
            f"{full_text}\n"
            f"--- INSTRUCTIONS ---\n"
            f"QUESTION: {question}"
        )
        a = types.Part.from_text(text = final_prompt)
        contents_list.append(a)

        # 5. Return the result (This must be the last line inside the 'with' block)
        return contents_list

def extract_text_and_images_from_pdf(pdf_path: str) -> tuple[str, list]:
    """
    Extracts all text from a local PDF file and collects image data for each page.

    Returns:
        A tuple containing (full_text_string, list_of_image_objects).
    """
    try:
        reader = pypdf.PdfReader(pdf_path)
        full_text = ""
        page_images = []  # 👈 1. Initialize an empty list to store the images

        # Iterate over pages (pypdf uses 0-based index)
        for p_index, page in enumerate(reader.pages):
            page_number = p_index + 1  # Convert to 1-based index for your converter function

            # 1. Extract Text
            full_text += page.extract_text()

            # 2. Extract Image Data for this page
            page_image = convert_pdf_page_to_image(pdf_path, page_number)

            # 3. Save the Image if the conversion was successful
            if page_image is not None:
                # Append the image object (PIL.Image or bytes) to the list
                page_images.append(page_image)
            else:
                # Optional: Log which page failed to convert
                print(f"⚠️ Warning: Image conversion failed for page {page_number}. Skipping image.")

        # Return both the text and the list of images
        return full_text, page_images

    except Exception as e:
        print(f"❌ Error during PDF processing: {e}")
        return "", []


# --- Example Usage ---
# full_doc_text, image_list = extract_text_and_images_from_pdf("my_scanned_document.pdf")
# print(f"Extracted {len(full_doc_text.split())} words and {len(image_list)} images.")
# Assuming you have the image data loaded into a variable named 'page_image_data'

'''
contents = [
    # 1. The image data (the scanned page)
    page_image_data,

    # 2. The text prompt containing the instructions and the question
    "DOCUMENT CONTEXT: Use the following image to answer the question below. QUESTION: what is the father's name"
]

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=contents
)
'''

def ask_gemini_with_context(context: str, question: str):
    """Asks Gemini a question using the PDF text as context."""
    if not context:
        return "Could not read the document to provide context."

    # 1. Construct the RAG Prompt
    # This prompt tells Gemini to use the provided text as its sole source of truth.
    system_instruction = (
        "You are a helpful assistant. Use ONLY the provided document text as context "
        "to answer the question. If the information is not in the text, reply #$$$# "
        #"the answer cannot be found in the provided document."
    )

    full_prompt = (
        f"DOCUMENT CONTEXT:\n---\n{context}\n---\n\n"
        f"QUESTION: {question}"
    )

    try:
        client = genai.Client()

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_prompt,
            config={"system_instruction": system_instruction}
        )

        return response.text.strip()
        print("\n--- Gemini's Answer (Based on the PDF) ---")
        print(response.text.strip())
        print("------------------------------------------")

    except APIError as e:
        print(f"\n❌ API Error: Check your GEMINI_API_KEY and API access. Details: {e}")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")

def ask_gemini_with_contextNimage(context: str, image_list, question: str):
    """Asks Gemini a question using the PDF text as context."""
    if not context:
        return "Could not read the document to provide context."

    contents_for_gemini = []

    # Convert each PIL Image object into the required 'Part' format
    for image in image_list:
        # Use image.tobytes() if it's a PIL Image object
        # OR use the image bytes directly if your converter returns bytes
        # This example assumes the image object can be saved to bytes:
        #from io import BytesIO
        #img_byte_arr = BytesIO()
        #image.save(img_byte_arr, format='PNG')
        #img_bytes = img_byte_arr.getvalue()

        contents_for_gemini.append(
            types.Part.from_bytes(data=image, mime_type='image/png')
        )

    # 1. Construct the RAG Prompt
    # This prompt tells Gemini to use the provided text as its sole source of truth.

    system_instruction = (
        "You are a helpful assistant. Use ONLY the provided document text as context and the images"
        "to answer the question. If the information is not in the text, reply #$$$# "
        #"the answer cannot be found in the provided document."
    )

    final_prompt = (
        f"DOCUMENT CONTEXT:\n---\n{context}\n---\n\n"
        f"QUESTION: {question}"
    )

    contents_for_gemini.append(final_prompt)
    try:
        client = genai.Client()

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents_for_gemini,
            config={"system_instruction": system_instruction}
        )

        return response.text.strip()
        print("\n--- Gemini's Answer (Based on the PDF) ---")
        print(response.text.strip())
        print("------------------------------------------")

    except APIError as e:
        print(f"\n❌ API Error: Check your GEMINI_API_KEY and API access. Details: {e}")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")

def read_pdf_with_pypdf2(file_path):
    try:
        reader = PdfReader(file_path)
        full_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        return full_text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def open_pdf_page(pdf_path, page_number):
    sumatra_path = r"C:\Users\orenm\AppData\Local\SumatraPDF\SumatraPDF.exe"  # change this to your installation
    subprocess.Popen([sumatra_path, "-page", str(page_number), pdf_path])

def is_mostly_english(word: str, threshold: float = 0.75) -> bool:
    """
    Checks if a word is composed of at least 75% Latin letters (a-Z).
    """
    if not word:
        return False

    # 1. Find all Latin letters
    latin_count = len(LATIN_LETTER_PATTERN.findall(word))
    num_count = len(sequence_pattern.findall(word))

    # 2. Total length of the word
    total_chars = len(word)

    # 3. Calculate the ratio
    ratio = (latin_count+num_count) / total_chars

    return ratio >= threshold


def contains_hebrew(text: str) -> bool:
    """Checks if the string contains any Hebrew characters."""
    return bool(HEBREW_PATTERN.search(text))


def contains_english(text: str) -> bool:
    """Checks if the string contains any Hebrew characters."""
    return bool(ENGLISH_PATTERN.search(text))


def reverse_first_to_last_non_letter_span(word: str) -> str:
    """
    Finds the first and last non-letter characters in a word and reverses
    the entire substring between those two points (inclusive).
    """
    first_idx = -1
    last_idx = -1

    # 1. Find the index of the first non-letter character
    for i, char in enumerate(word):
        if not LETTER_PATTERN.match(char):
            first_idx = i
            break

    # 2. Find the index of the last non-letter character (iterate backward)
    for i in range(len(word) - 1, -1, -1):
        if not LETTER_PATTERN.match(word[i]):
            last_idx = i
            break

    # If no non-letters were found, return the original word
    if first_idx == -1:
        return word

    # 3. Define the three parts of the word: prefix, span, and suffix
    prefix = word[:first_idx]
    span_to_reverse = word[first_idx: last_idx + 1]
    suffix = word[last_idx + 1:]

    # 4. Reverse the span and reconstruct the word
    reversed_span = span_to_reverse[::-1]

    return prefix + reversed_span + suffix


def fix_hebrew_reversal(text):
    """
    Applies the advanced, surgical fix:
    1. Always reverses characters within each word.
    2. Then, surgically reverses non-letter segments (numbers/punctuation)
       back to LTR order to fix corruption.
    3. Finally, reverses the word order in the sentence.
    """
    if not text:
        return ""

    def is_hebrew_letter(char):
        # Checks if a character is a standard Hebrew letter
        return 'HEBREW' in unicodedata.name(char, '')

        corrected_segments = []
        for non_letter_segment, letter_segment in segments:
            if letter_segment:
                # If it's a letter segment (Hebrew or Latin), keep it as-is (it's already reversed)
                corrected_segments.append(letter_segment)
            elif non_letter_segment:
                # If it's a non-letter segment (numbers, punctuation), reverse it back
                # Example: '321' needs to be reversed back to '123'
                corrected_segments.append(non_letter_segment[::-1])

        return "".join(corrected_segments)

    # 1. Split the text into words by whitespace
    words = text.split()

    surgically_corrected_words = []
    for word in words:
        # Step 1: Always apply full character reversal first

        # if ~contains_english(word):
        #    fully_reversed_word = word[::-1]
        # else:
        #    fully_reversed_word = word
        if is_mostly_english(word):
            fixed_word = word
        else:
            fully_reversed_word = word[::-1]

            fully_reversed_word = fully_reversed_word.replace(')', 'zzzz').replace('(', 'xxxx').replace('"', 'cccc').replace('.', 'dddd')
            #fully_reversed_word = fully_reversed_word.replace('"', 'cccc')
            fixed_word = reverse_first_to_last_non_letter_span(fully_reversed_word)
            #fixed_word = fixed_word.replace('cccc', '"')
            fixed_word = fixed_word.replace('zzzz', ')').replace('xxxx', '(').replace('cccc', '"').replace('dddd', '.')

        surgically_corrected_words.append(fixed_word)

    # 3. Reverse the order of the words in the list (fixes RTL sentence order)
    surgically_corrected_words.reverse()

    # 4. Join the words back with spaces
    return " ".join(surgically_corrected_words)


def paragraph_matches(text, words, mode='any', search_mode='partial'):
    # text_lower = text.lower()
    text_lower = text
    if search_mode == 'full':
        # Match only whole words
        found = 0
        for w in words:
            pattern = r'\b{}\b'.format(re.escape(w.lower()))
            if re.search(pattern, text_lower):
                found += 1

        return (mode == 'all' and found == len(words)) or (mode != 'all' and found > 0)
    else:
        # substring match
        if mode == 'all':
            return all(w.lower() in text_lower for w in words)
        else:
            return any(w.lower() in text_lower for w in words)


def replace_with_bold(text, regex):
    # Use QRegExp to find matches and replace with <b> tags
    pattern = regex
    start = 0
    result = ""
    while True:
        index = pattern.indexIn(text, start)
        if index == -1:
            result += text[start:]
            break
        # Append text before match
        result += text[start:index]
        # Append bolded match
        match_text = pattern.cap(0)
        result += f"<b>{match_text}</b>"
        start = index + len(match_text)
    return result


def highlight_terms(text, search_terms):
    # Highlight each search term in the text (case-insensitive)
    for term in search_terms:
        # Use regex for case-insensitive replacement
        pattern = QtCore.QRegExp(term, QtCore.Qt.CaseInsensitive)
        text = replace_with_bold(text, pattern)
    return text


def convert_docx2pdf(docx_path, pdf_path):
    word = win32.Dispatch('Word.Application')
    word.Visible = False
    try:
        doc = word.Documents.Open(os.path.abspath(docx_path))
        # doc = Document(os.path.abspath(docx_path))
        doc.SaveAs(pdf_path, FileFormat=17)  # 17 = wdFormatPDF
        doc.Close()
    except Exception as e:
        print("Error:", e)
    finally:
        word.Quit()


def docx2pdf_search(path, words, mode='any', search_mode='partial'):
    pdf_path = os.path.join(os.getcwd(), "tempXX.pdf")
    convert_docx2pdf(path, pdf_path)
    results = pdf_search( path, words, mode, search_mode, pdf_path)
    # Optionally delete the temp.pdf here if not done inside pdf_search
    try:
        os.remove(pdf_path)
    except:
        pass
    return results


def pypdf_search(self, path, words, mode='any', search_mode='partial', read_from_temp=""):
    results = []

    # extract_hebrew_pdf_fully_corrected(path, "c:\\a\\a.text")
    try:
        reader = pypdf.PdfReader(path)

        previous_page_trailer = []
        for pnum, page in enumerate(reader.pages, start=1):

            context_text = page.extract_text()
            start_index = 1
            end_index = 2
            if paragraph_matches(context_text, words, mode, search_mode):
                            # Get neighboring lines to form a paragraph
                    # If both checks pass, format the 3-line context as the result

                    # Descriptive text for the user (Context is still important)
                    pre = f"<span style='color:blue;'>— עמוד {pnum} — שורות {start_index + 1}-{end_index}</span>"

                    # HTML Link definition (Uses fileonly:// to skip page jump)
                    path_for_url = path.replace('\\', '/')
                    fileonly_url = f"file:///{path_for_url}"  # Three slashes for file protocol on Windows

                    # Ensure the custom protocol signal is used if you need to differentiate the link types
                    fileonly_url = f"fileonly:///{path_for_url}"  # Use three slashes for consistency
                    file_url_with_page = f"filepage:///{path_for_url}?page={pnum}"
                    open_link = f"<a href='{file_url_with_page}' style='color:green; text-decoration: none;'>[פתח קובץ]</a>"

                    # Assemble the final HTML paragraph
                    full_paragraph = (
                            " ".join([path]) + "  " +
                            pre + " " + open_link + "<br><br>" +
                            context_text + "<br>"
                    )

                    results.append(full_paragraph)

    except:
        pass


    finally:
        # Delete temp PDF if it was used
        if read_from_temp and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception as e:
                print(f"Error deleting temp PDF: {e}")
    return results

def pdf_search(self, path, words, mode='any', search_mode='partial', read_from_temp=""):
    results = []

    # extract_hebrew_pdf_fully_corrected(path, "c:\\a\\a.text")
    try:
        if read_from_temp.strip():
            pdf_path = read_from_temp
            if os.path.exists(pdf_path):
                reader = pdfplumber.open(pdf_path)
            else:
                print("Temporary PDF not found.")
                return results
        else:
            reader = pdfplumber.open(path)
            reader2 = pypdf.PdfReader(path)

        previous_page_trailer = []
        for pnum, page in enumerate(reader.pages, start=1):

            page_height = page.height
            header_limit = HEADER_MARGIN
            footer_limit = page_height - FOOTER_MARGIN

            # Extract structured text blocks with coordinates (CRITICAL for line order)

            blocks: List[Dict] = page.extract_text_lines(
                return_chars=False,
                return_textbox=True,
                strip=False
            )
            # --- NEW HEADER/FOOTER FILTERING LOGIC ---
            # Keep only the blocks whose vertical position is between the margins
            filtered_blocks = [
                block for block in blocks
                if block['top'] > header_limit and block['bottom'] < footer_limit
            ]
            # --- END FILTERING LOGIC ---

            # Sort blocks by vertical (top) then horizontal (x0) position
            sorted_blocks = sorted(filtered_blocks, key=lambda b: (b['top'], b['x0']))

            page_raw_text_lines = [block['text'] for block in sorted_blocks]

            # Apply the full surgical reversal fix to each line
            lines = [fix_hebrew_reversal(line) for line in page_raw_text_lines]
            lines = previous_page_trailer + lines

            l = len(lines)

            i = 0
            if search_mode == 'chatgpt':

                content_summary = "\n".join(lines)

                # Create prompt

                query = self.search_input.text().strip()
                prompt = f"כתוב את התשובה בשפה העברית על בסיס הטקסט הבא רק אם יש לך תשובה החלטית אחרת השב $$$$:\n{content_summary}\nשאלה: {query}"
                pre = f"<span style='color:blue;'>— עמוד {pnum}</span>"
                # Call GPT API
                time.sleep(2)
                answer = self.ask_chatgpt(prompt)
                pre = f"<span style='color:blue;'> — עמוד {pnum}  </span>"

                full_paragraph = (
                        " ".join([path]) + "  " +
                        pre + "<br><br>" +
                        answer + "<br>"
                )

                if "error" in answer.lower() or "אין מספיק מידע" in answer.lower() or "$$$$" in answer.lower() or "לא מספק מידע" in answer.lower() or "אני מצטער" in answer.lower() or "בטקסט שסופק" in answer.lower():
                    full_paragraph = ""

                results.append(full_paragraph)
            else:

                while i < l:
                    # lnum is the 1-based index (i + 1)

                        lnum = i + 1
                        ln = lines[i]

                        # 1. First Check: Does the current line match ANY of the search words?
                        if paragraph_matches(ln, words, 'any', search_mode):

                            # 2. Safely gather the 3-line context: [line before], [match line], [line after]
                            start_index = max(0, lnum - 2)
                            end_index = min(lnum + 2, l)
                            if (lnum + 2) > l:
                                previous_page_trailer = lines[lnum - 1:]
                            else:
                                previous_page_trailer = []

                            context_lines = lines[start_index:end_index]
                            context_lines = [line.replace(".₪", "₪.") for line in context_lines]
                            context_lines = [line.replace(",₪", "₪,") for line in context_lines]
                            #context_lines = [re.sub( r' ,\\1', r'(.), ',line) for line in context_lines]
                            #context_lines = [re.sub(r' .\\1', r'(.). ', line) for line in context_lines]


                            # 3. Concatenate lines into a single searchable string
                            context_text = " ".join(context_lines)

                            # 4. Second Check: Does the 3-line context match the FULL user criteria (e.g., ALL words)?
                            # We use the original 'mode' (which is 'all' if the user used '+' or '&')
                            if paragraph_matches(context_text, words, mode, search_mode):
                                # Get neighboring lines to form a paragraph
                                # If both checks pass, format the 3-line context as the result

                                # Descriptive text for the user (Context is still important)
                                pre = f"<span style='color:blue;'>— עמוד {pnum} — שורות {start_index + 1}-{end_index}</span>"

                                # HTML Link definition (Uses fileonly:// to skip page jump)
                                path_for_url = path.replace('\\', '/')
                                fileonly_url = f"file:///{path_for_url}"  # Three slashes for file protocol on Windows

                                # Ensure the custom protocol signal is used if you need to differentiate the link types
                                fileonly_url = f"fileonly:///{path_for_url}"  # Use three slashes for consistency
                                file_url_with_page = f"filepage:///{path_for_url}?page={pnum}"
                                open_link = f"<a href='{file_url_with_page}' style='color:green; text-decoration: none;'>[פתח קובץ]</a>"

                                # Assemble the final HTML paragraph
                                full_paragraph = (
                                        " ".join([path]) + "  " +
                                        pre + " " + open_link + "<br><br>" +
                                        "<br>".join(context_lines) + "<br>"
                                )

                                results.append(full_paragraph)

                                # Advance loop index to skip context lines
                                i += 2

                        i = i + 1
    except:
        pass


    finally:
        # Delete temp PDF if it was used
        if read_from_temp and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except Exception as e:
                print(f"Error deleting temp PDF: {e}")
    return results


def docx_search(path, words, mode='any', search_mode='partial'):
    results = []
    try:
        doc = Document(path)
        for para in doc.paragraphs:
            full_text = para.text or ""
            if paragraph_matches(full_text, words, mode, search_mode):
                #results = docx2pdf_search(path, words, mode, search_mode)
                #return results

                full_paragraph = (
                    f"{path}  <br><br> {full_text} <br>"
                )
                results.append(full_paragraph)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text = cell.text or ""
                    full_paragraph = (
                            " ".join([path]) + "  " +
                            "<br><br>" +
                            "<br>".join(full_text) + "<br>"
                    )

                    if paragraph_matches(full_text, words, mode, search_mode):
                        results.append(full_paragraph)
    except:
        pass

    return results





class SearchApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("הדס לוי -  עורך דין - תוכנת חיפוש")
        self.resize(1700, 1200)
        ui_setup.setup_ui(self)

    def prepare_content_summary(self, folder):
        summaries = []

        for root, _, files in os.walk(folder):



            for filename in files:


                if filename.startswith('~$'):
                    continue  # Skip temporary backup files
                file_path = os.path.join(root, filename)
                # Handle text files
                if filename.lower().endswith('.txt'):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            summaries.append(f"{filename}: {content}")
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
                # Handle Word documents
                elif filename.lower().endswith('.docx'):
                    try:
                        doc = Document(file_path)
                        full_text = "\n".join([para.text for para in doc.paragraphs])
                        summaries.append(f"{filename} (Word): {full_text}")
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
                # Handle PDFs
                elif filename.lower().endswith('.pdf'):
                    try:
                        with pdfplumber.open(file_path) as pdf:
                            #page = pdf.pages[0]
                            #text = page.extract_text()
                            text = read_pdf_with_pypdf2(file_path)
                            summaries.append(f"{filename} (PDF): {text}")
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
        return "\n\n".join(summaries)

    def handle_chatgpt_mode(self, folder, query):
        # Prepare content from documents
        content_summary = self.prepare_content_summary(folder)

        # Create prompt
        #prompt = f"Based on the following content:\n{content_summary}\nQuestion: {query}"
        prompt = f"כתוב את התשובה בשפה העברית על בסיס הטקסט הבא ואל תשכח לציין את מקור המידע: שם הקובץ, ומספר העמוד:\n{content_summary}\nשאלה: {query}"

        # Call GPT API
        answer = self.ask_chatgpt(prompt)
        if "error" in answer.lower() or "אין מספיק מידע" in answer.lower() or "אני מצטער" in answer.lower()  or "בטקסט שסופק" in answer.lower()   :
            answer = ""
        return answer




    def update_search_button_text(self):
        layout = self.both_groups_layout  # Use the class attribute reference
        if self.gemini_radio.isChecked():
            self.search_btn.setText(ui_setup.gemini_radio_str)
            self.label.setText(ui_setup.label_gpt_str)
            #self.g1_container.setVisible(False)
            #self.setPlaceholderText(ui_setup.search_input_question_str)
            self.g_group_widget.setVisible(False)
            #layout.removeWidget(self.g1_container)
            #layout.removeWidget(self.g_group_widget)
            #layout.insertItem(self.g1_layout_index, self.g1_placeholder)

            self.nongemini_radio.setStyleSheet("""
                QRadioButton {
                    background-color: #f0f0f0; /* Light gray background for the frame */
                    color: #333333; /* Optional: set text color */
                    padding: 5px; /* Optional: add internal padding */
                }
                QRadioButton::indicator {
                    width: 15px;
                    height: 15px;
                    border-radius: 10px;
                    border: 6px solid black;
                }
                QRadioButton::indicator:checked {
                    background-color: green;
                }
                """)
            self.gemini_radio.setStyleSheet("""
                           QRadioButton {
                               background-color: #0000ff; /* Light gray background for the frame */
                               color: #333333; /* Optional: set text color */
                               padding: 5px; /* Optional: add internal padding */
                           }
                           QRadioButton::indicator {
                               width: 15px;
                               height: 15px;
                               border-radius: 10px;
                               border: 6px solid black;
                           }
                           QRadioButton::indicator:checked {
                               background-color: green;
                           }
                           """)
        else:
            self.search_btn.setText(ui_setup.search_btn_str)
            self.label.setText(ui_setup.label_str)
            #self.setPlaceholderText(ui_setup.search_input_words_str)
            # 4. Show the widget
            self.g_group_widget.setVisible(True)

            # 1. Check if the spacer is currently in the layout at the expected index
            #item = layout.itemAt(self.g1_layout_index)
            #if item is self.g1_placeholder:
                # 2. Remove the spacer
            #    layout.removeItem(self.g1_placeholder)

            # 3. Insert the container widget back into the layout
            # The index should be safe if the spacer was removed.
            #layout.insertWidget(self.g1_layout_index, self.g1_container)
            #layout.insertWidget(self.g1_layout_index, self.g_group_widget)

            self.nongemini_radio.setStyleSheet("""
                QRadioButton {
                    background-color: #0000ff; /* Light gray background for the frame */
                    color: #333333; /* Optional: set text color */
                    padding: 5px; /* Optional: add internal padding */
                }
                QRadioButton::indicator {
                    width: 15px;
                    height: 15px;
                    border-radius: 10px;
                    border: 6px solid black;
                }
                QRadioButton::indicator:checked {
                    background-color: green;
                }
                """)
            self.gemini_radio.setStyleSheet("""
                QRadioButton {
                    background-color: #f0f0f0; /* Light gray background for the frame */
                    color: #333333; /* Optional: set text color */
                    padding: 5px; /* Optional: add internal padding */
                }
                QRadioButton::indicator {
                    width: 15px;
                    height: 15px;
                    border-radius: 10px;
                    border: 6px solid black;
                }
                QRadioButton::indicator:checked {
                    background-color: green;
                }
                """)

    # --- FINAL ATTEMPT: ShellExecuteW to bypass shell ambiguity ---
        # In SearchApp class
    def _handle_link_click(self, url: QtCore.QUrl):
        """
        Uses the Windows API function ShellExecuteW to reliably open the file,
        avoiding Explorer by forcing the native 'open' action on the file path.
        """
        # 1. Decode the local file path from the QUrl object
        # QUrl.toLocalFile() correctly handles URL-encoding and provides the clean
        # file path, including Hebrew characters.
        local_path = url.toLocalFile()
        url_str = url.toString()

        # Parse the URL to extract the path
        parsed_url = urlparse(url_str)
        # Get the path without URL encoding (e.g., spaces, non-ASCII)
        file_path = unquote(parsed_url.path)



        # Check for your custom protocol signal
        if url_str.startswith("filepage://"):
            try:
                # 2. Convert to absolute path (if needed) and use the correctly decoded path
                # os.path.abspath is usually good, but local_path from QUrl should be sufficient.
                # For Windows, on some Python versions, the path may have a leading slash
                if os.name == 'nt' and file_path.startswith('/'):
                    file_path = file_path[1:]

                # Now open the file

                content = url_str[len("filepage:///"):]  # everything after the scheme
                # Split to separate path and query
                path_part, _, query = content.partition('?')
                # Extract page number from query
                params = dict(param.split('=') for param in query.split('&'))
                page_num = int(params.get('page', 1))
                # Convert path back to OS format
                file_path = path_part.replace('/', os.path.sep)

                mime_type, _ = mimetypes.guess_type(file_path)

                if mime_type == 'application/pdf':
                    # Open PDF at specific page with SumatraPDF
                    open_pdf_page(file_path, page_num)
                else:
                    # Open other files normally
                    os.startfile(file_path)

            except Exception as e:
                print(f"Error launching file {resolved_path}: {e}")
                QtWidgets.QMessageBox.warning(
                    self, "שגיאה בפתיחת קובץ",
                    f"לא ניתן לפתוח את הקובץ: {resolved_path}\nשגיאה: {e}"
                )

    # --- END UPDATED METHOD ---

    def clear_all(self):
        """Clears the search input and, most importantly, the results display area."""
        self.search_input.clear()
        self.results_area.clear()
        self.progressBar.setValue(0)

    def save_all2file(self):
        """Clears the search input and, most importantly, the results display area."""
        doc = Document()
        path = os.path.join(self.dir_edit.text().strip(), "results.docx")
        text = self.results_area.toPlainText()
        # Add the text as a paragraph
        doc.add_paragraph(text)
        doc.save(path)




    def execute_search(self):
        folder = self.dir_edit.text().strip()
        query = self.search_input.text().strip()
        self.results_area.clear()

        if self.cloudgemini_radio.isChecked():
            normalized_path = folder.replace("\\", "/")
            prefix_to_strip = CLIENT_PREFIX_TO_STRIP.replace("\\", "/")
            # 3. Strip trailing slashes from both for consistent comparison (e.g., C:/a/מצרפי/)
            normalized_path = normalized_path.strip('/')
            prefix_to_strip = prefix_to_strip.strip('/')

            # 4. Perform the strip only if the path starts with the prefix
            if normalized_path.lower().startswith(prefix_to_strip.lower()):
                # Strip the prefix, plus the slash that separates the prefix from the folder path
                gcs_directory_path = normalized_path[len(prefix_to_strip):].strip('/')
            else:
                # If no prefix match, use the normalized path as is
                gcs_directory_path = normalized_path.strip('/')

            # ... gcs_directory_path (now 'גירושין/2024') is used for GCS listing

            folder = gcs_directory_path

            answer = on_search_button_clicked(self, query, folder)


            #perform_search(query, directory_path=folder)
            display_gemini_result(self, self.results_area, answer, folder)
            return


        if not os.path.isdir(folder):
            QtWidgets.QMessageBox.warning(self, "שגיאה", "התיקיה לא קיימת.")
            return
        if not query:
            QtWidgets.QMessageBox.warning(self, "שגיאה", "אנא הזן מילות חיפוש.")
            return

        # Parse query for AND/OR
        mode = 'any'
        # Determine search mode based on radio button selection
        if self.all_word_search_radio.isChecked():
            mode = 'all'


            # Determine mode
        if self.gemini_radio.isChecked():
            search_mode = chat_mode
        elif self.exact_search_radio.isChecked():
            search_mode = 'full'
        else:
            search_mode = 'partial'  # default


        words = [w.strip() for w in query.replace('+', ' ').replace('&', ' ').split()]

        self.results_area.clear()
        total_found = 0

        count = 0


        for root, _, files in os.walk(folder):
            total_files = sum([len(files) for r, d, files in os.walk(folder)])
            for filename in files:
                count += 1
                if filename.startswith('~$'):
                    continue  # Skip temporary backup files

                if should_skip_file(filename):
                    print(f"SKIPPING: {filename} (Temporary Lock File)")
                    continue


                self.progressBar.setValue(int(count / total_files * 100))

                QtWidgets.QApplication.processEvents()
                path = os.path.join(root, filename)

                path_str = f"{root} \t {filename}"
                filename_lower = filename.lower()
                if filename_lower.endswith('.docx'):
                    try:
                        if search_mode == 'gemini':

                            #doc_text = extract_text_from_docx(path)
                            #if doc_text:
                            #    answer = ask_gemini_with_context(doc_text, query)

                            gemini_input_parts = extract_docx_content(path, query)
                            client = genai.Client()
                            response = client.models.generate_content(
                                 model='gemini-2.5-flash',
                                 contents=gemini_input_parts
                            )
                            answer = response.text.strip()




                        # Example usage (assuming this function is part of a class):
                            display_gemini_result(self, self.results_area, answer, path)

                        else:
                            matches = docx_search(path, words, mode, search_mode)

                            for paragraph in matches:
                                self.append_result(path, paragraph, words)
                                total_found += 1
                    except:
                        continue
                elif filename_lower.endswith('.pdf'):
                    try:


                        if search_mode == 'gemini':

                            pdf_text, image_list = extract_text_and_images_from_pdf(path)
                            if image_list:
                                answer = ask_gemini_with_contextNimage(pdf_text, image_list, query)
                            elif pdf_text:
                                answer = ask_gemini_with_context(pdf_text, query)

                            display_gemini_result(self, self.results_area, answer, path)


                        else:
                            matches = pdf_search(self, path, words, mode, search_mode)

                        # matches2 = pdf_search_flags(path, words, search_mode)


                        for paragraph in matches:
                            self.append_result2(path, paragraph, words, search_mode )
                            total_found += 1
                    except:
                        continue

        if  not self.gemini_radio.isChecked():
            if total_found == 0:
                self.results_area.append("לא נמצאו תוצאות.")
            else:
                self.results_area.append(f"\nנמצאו {total_found} תוצאות.")

    def save_last_dir(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                f.write(self.dir_edit.text().strip())
        except:
            pass

    def browse_directory(self):
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "בחר תיקיה", self.dir_edit.text() or "/")
        # dir_path = RLO + dir_path
        if dir_path:
            self.dir_edit.setText(dir_path)
            self.save_last_dir()

    def load_last_dir(self):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                last_dir = f.read().strip()
                self.dir_edit.setText(last_dir)
        except:
            pass

    def append_result(self, filepath, paragraph, search_terms):
        # Highlight search terms in paragraph
        highlighted_paragraph = highlight_terms(paragraph, search_terms)
        html_text = (
            # f"<p style='font-family:Arial; font-size:14pt;'>"
            f"<div dir='rtl' style='font-family:Arial; font-size:16pt;margin-right:40px;'>"
            f"<br>*<br>"
            # f"<b>קובץ:</b> {filepath}<br>"
            f"{highlighted_paragraph}"
            f"================================================================"
            # "<hr style='height:4px; border:none; background-color:red; margin:10px 0;'>"
            "</div>"

        )
        self.results_area.append(html_text)

    def append_result2(self, filepath, paragraph, search_terms, search_mode = ""):
        # Highlight search terms in paragraph
        if search_mode == 'chatgpt':

            html_text = (
                f"<div dir='rtl' style='font-family:Arial; font-size:16pt;margin-right:40px;'>"
                f"{paragraph}"
                "</div>"
            )
        else:
            highlighted_paragraph = highlight_terms(paragraph, search_terms)
            html_text = (
                f"<div dir='rtl' style='font-family:Arial; font-size:16pt;margin-right:40px;'>"
                f"{highlighted_paragraph}"
                "</div>"
            )
        self.results_area.append(html_text)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SearchApp()
    window.show()

    # The connection remains, pointing to the new, highly native handler.
    window.results_area.anchorClicked.connect(window._handle_link_click)

    sys.exit(app.exec_())