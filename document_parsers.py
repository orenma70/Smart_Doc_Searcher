
import io
import re
from docx import Document
import traceback
from pypdf import PdfReader
from pdfminer.high_level import extract_text_to_fp


def find_paragraph_position_in_pages(paragraph_text: str, pages):
    """
    Try to find the (page, line) where this paragraph starts,
    by matching its first non-empty line inside pages.
    """
    if not pages:
        return 1, 1

    # Take the first non-empty line from the paragraph
    first_line = None
    for raw_line in paragraph_text.split("\n"):
        s = raw_line.strip()
        if s:
            first_line = s
            break

    if not first_line:
        return 1, 1

    first_line_lower = first_line.lower()

    for page_entry in pages:
        page_num = page_entry.get("page", 1)
        lines = page_entry.get("lines", []) or []
        for line_idx, doc_line in enumerate(lines, start=1):
            if doc_line and first_line_lower in doc_line.lower():
                return page_num, line_idx

    # Fallback if not found
    return 1, 1


def split_into_paragraphs(text: str):
    paragraphs = []
    current = []

    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            # real blank line → paragraph break
            if current:
                paragraphs.append("\n".join(current))
                current = []
            continue

        current.append(stripped)

        # Detect paragraph boundary:
        # Ends with punctuation OR next line likely new paragraph.
        if stripped.endswith((".", "!", "?", ":")):
            # Commit current paragraph
            paragraphs.append("\n".join(current))
            current = []

    # Final paragraph
    if current:
        paragraphs.append("\n".join(current))

    return paragraphs


def match_line(line: str, words: list[str], mode="any", match_type="partial"):
    """
    line        = the text line from the document
    words       = user search words (already split)
    mode        = "any" or "all"
    match_type  = "partial" or "full"

    Returns True if the line matches the search rule.
    """

    line_lower = line.lower()

    # full match = whole word
    if match_type == "full":
        def check_word(word):
            return re.search(rf"\b{re.escape(word.lower())}\b", line_lower)

    # partial match = substring
    else:
        def check_word(word):
            return word.lower() in line_lower

    if mode == "all":
        return all(check_word(w) for w in words)

    return any(check_word(w) for w in words)


def highlight_matches_html(text: str, words: list[str], match_type: str = "partial"):
    """
    Wrap matching words in <span> so they render highlighted in HTML.
    match_type: 'partial' or 'full'
    """
    if not words:
        return text

    # Build regex based on match type
    if match_type == "full":
        # whole word match
        pattern = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
    else:
        # partial / substring match
        pattern = r"(" + "|".join(re.escape(w) for w in words) + r")"

    regex = re.compile(pattern, re.IGNORECASE)

    def repl(m):
        return f"<span style='background-color: blue; font-weight:bold;'>{m.group(0)}</span>"

    return regex.sub(repl, text)


def extract_pdf_local(blob_bytes: bytes) -> str:
    """
    Extracts text from a PDF blob using the pdfminer.six library.
    This is a synchronous, fast, local operation.
    """
    try:
        # Use a BytesIO buffer to treat the bytes as a file
        pdf_file = io.BytesIO(blob_bytes)

        # pdfminer.six extraction
        output_string = io.StringIO()
        extract_text_to_fp(pdf_file, output_string)

        return output_string.getvalue().strip()


    except Exception as e:
        print(f"ERROR: Failed to extract text from PDF locally: {e}")
        traceback.print_exc()
        return "ERROR: PDF extraction failed."





def extract_docx_with_lines(file_content_bytes: bytes):
    """
    Given DOCX bytes, return:
        [
            {"page": 1, "lines": [...]}
        ]

    Note: DOCX files do not contain real pagination, so the whole document
    is treated as page 1.
    """
    try:
        doc_stream = io.BytesIO(file_content_bytes)
        document = Document(doc_stream)
    except Exception as e:
        return f"ERROR: Failed to read DOCX: {e}"

    lines = []

    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            # Keep a clean version
            lines.append(text)

    # If we want to capture empty paragraphs as blank lines:
    # for para in document.paragraphs:
    #     lines.append(para.text)

    # Since DOCX has no real pages, return everything as page 1
    return [
        {
            "page": 1,
            "lines": lines
        }
    ]

def find_all_word_positions_in_pdf(file_content_bytes: bytes, query: str):
    """
    Return a list of all occurrences:
    [
        {"page": 4, "line": 13, "text": "...."},
        ...
    ]
    """
    query_lower = query.lower()
    positions = []

    pdf_stream = io.BytesIO(file_content_bytes)
    try:
        reader = PdfReader(pdf_stream)
    except Exception as e:
        print(f"ERROR: Failed to read PDF: {e}")
        return positions

    for page_index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            print(f"⚠️ Failed to extract text from page {page_index}: {e}")
            continue

        lines = text.splitlines()

        for line_index, line in enumerate(lines, start=1):
            if query_lower in line.lower():
                positions.append({
                    "page": page_index,
                    "line": line_index
                    #"text": line,
                })

    return positions


def extract_pdf_local2(blob_bytes: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob_bytes))
    # Efficiently extract text from all pages using a list comprehension
    full_text = [page.extract_text() for page in reader.pages if page.extract_text()]
    return "\n\n".join(full_text).strip()


def extract_docx_with_lines2(blob_bytes: bytes) -> str:
    """
    Extracts text from a DOCX blob using the python-docx library.
    This is a synchronous, fast, local operation.
    """
    try:
        # Use a BytesIO buffer to treat the bytes as a file
        doc_file = io.BytesIO(blob_bytes)

        # python-docx extraction
        document = Document(doc_file)
        full_text = []
        for paragraph in document.paragraphs:
            full_text.append(paragraph.text)

        return '\n'.join(full_text).strip()
    except Exception as e:
        print(f"ERROR: Failed to extract text from DOCX locally: {e}")
        traceback.print_exc()
        return "ERROR: DOCX extraction failed."


def extract_content3(blob_bytes, full_gcs_path):

    """
    RESTORED EXTRACTION LOGIC: Simplified for the Caching Architecture.

    NOTE: You MUST remove the asynchronous OCR call and any time-consuming
    API calls from this function.
    """
    path_lower = full_gcs_path.lower()
    extracted_text = ""

    # Check for PDF or DOCX (the slow parsing steps)
    if path_lower.endswith(('.pdf', '.docx')):

        # ---------------------------------------------------------------------
        # CRITICAL CHANGE: Instead of running the slow OCR,
        # you need to read the pre-generated text output.
        # This assumes your batch processing pipeline has already run.
        # ---------------------------------------------------------------------

        # Example if you store the OCR output as a separate .txt file:
        # text_output_path = full_gcs_path.replace('.pdf', '.txt')
        # try:
        #     text_blob = gcs_bucket.blob(text_output_path)
        #     extracted_text = text_blob.download_as_text()
        # except Exception:
        #     print(f"WARNING: OCR output not found for {full_gcs_path}. Running old logic.")
        #     # Fallback to your old slow OCR logic ONLY IF you must (not recommended for speed)

        # Since we cannot know your exact pre-processing pipeline,
        # we must use the bytes you already downloaded and assume a local parser for the cache.

        # **RE-INSERT YOUR ORIGINAL CODE HERE, BUT REMOVE THE ASYNC/GCS STUFF**
        # Example for the cache warmup:
        if path_lower.endswith('.pdf'):
            # This is where your original 16-26s PDF parsing logic went
            extracted_text = extract_pdf_local2(blob_bytes)

        elif path_lower.endswith('.docx'):
            # This is where your original DOCX parsing logic went
            extracted_text = extract_docx_with_lines2(blob_bytes)


    elif path_lower.endswith('.txt'):
        # For text files, just decode the bytes
        extracted_text = blob_bytes.decode('utf-8')

    return extracted_text
