import io
import traceback
from docx import Document
from pypdf import PdfReader


MAX_CHARS_PER_DOC = 100000


def extract_pdf_local(blob_bytes: bytes) -> str:
    """
    Extracts text from a PDF blob using pypdf.
    Returns an empty string on extraction failure.
    """
    try:
        pdf_file = io.BytesIO(blob_bytes)
        reader = PdfReader(pdf_file)

        full_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)

        return "\n\n".join(full_text).strip()
    except Exception as e:
        print(f"CRASH WARNING: Failed to extract text from PDF using pypdf. Error: {e}")
        traceback.print_exc()
        return ""


def extract_docx_with_lines2(blob_bytes: bytes) -> str:
    """
    Extracts text from a DOCX blob using python-docx (local, fast).
    """
    try:
        doc_file = io.BytesIO(blob_bytes)
        document = Document(doc_file)
        full_text = [paragraph.text for paragraph in document.paragraphs]
        return '\n'.join(full_text).strip()
    except Exception as e:
        print(f"ERROR: Failed to extract text from DOCX locally: {e}")
        traceback.print_exc()
        return ""


def extract_content3(blob_bytes: bytes, full_gcs_path: str) -> str:
    """
    Primary document extraction function. Uses the appropriate parser based on file extension.
    """
    path_lower = full_gcs_path.lower()
    extracted_text = ""

    if path_lower.endswith('.pdf'):
        extracted_text = extract_pdf_local(blob_bytes)
    elif path_lower.endswith('.docx'):
        extracted_text = extract_docx_with_lines2(blob_bytes)
    elif path_lower.endswith('.txt'):
        try:
            extracted_text = blob_bytes.decode('utf-8', errors='ignore').strip()
        except Exception as e:
            print(f"ERROR: Could not decode TXT: {e}")
            extracted_text = ""
    else:
        extracted_text = ""

    if not extracted_text:
        return ""

    if len(extracted_text) > MAX_CHARS_PER_DOC:
        return extracted_text[:MAX_CHARS_PER_DOC]

    return extracted_text