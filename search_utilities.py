import re
import os
import io
import traceback
from typing import List, Dict, Any # <-- THIS LINE IS THE CRITICAL FIX
from docx import Document
from google.cloud import storage
from pypdf import PdfReader
from google.cloud import vision_v1 as vision

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

        output_lines.append(f" debug:  {results_data.get("debug")}<br>")
        #output_lines.append(f"נתיב מלא: {full_path} <br>")


        for line in lines:
            output_lines.append(f"   • {line}<br>")



    return "\n".join(output_lines)
