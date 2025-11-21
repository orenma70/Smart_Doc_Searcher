import io
import traceback
from docx import Document
from pypdf import PdfReader
from pdfminer.high_level import extract_text_to_fp

MAX_CHARS_PER_DOC = 100000

def extract_pdf_local2(blob_bytes: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob_bytes))
    # Efficiently extract text from all pages using a list comprehension
    full_text = [page.extract_text() for page in reader.pages if page.extract_text()]
    return "\n\n".join(full_text).strip()


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

