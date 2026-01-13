import re
import time
import boto3
import json


def run_textract_and_save_index(bucket_name, document_key):
    textract = boto3.client('textract', region_name='ap-southeast-2')
    s3_client = boto3.client('s3', region_name='ap-southeast-2')

    print(f"--- Starting Final Hebrew Fix for {document_key} ---")

    try:
        # 1. שימוש ב-LAYOUT בלבד (כדי למנוע את שגיאת ה-InvalidParameter)
        # הוספנו כאן את הטיפול ב-NextToken כדי לוודא שכל 37 העמודים נסרקים
        response = textract.start_document_analysis(
            DocumentLocation={'S3Object': {'Bucket': bucket_name, 'Name': document_key}},
            FeatureTypes=['LAYOUT']
        )
        job_id = response['JobId']

        # המתנה לסיום
        while True:
            status_resp = textract.get_document_analysis(JobId=job_id)
            status = status_resp['JobStatus']
            if status == 'SUCCEEDED': break
            if status == 'FAILED': raise Exception("Textract failed")
            time.sleep(5)

        # 2. איסוף כל העמודים (טיפול ב-37 עמודים)
        pages_data = []
        next_token = None
        while True:
            params = {'JobId': job_id}
            if next_token: params['NextToken'] = next_token

            result = textract.get_document_analysis(**params)

            for block in result['Blocks']:
                if block['BlockType'] == 'LINE':
                    p_num = block.get('Page', 1)
                    while len(pages_data) < p_num:
                        pages_data.append({"page": len(pages_data) + 1, "lines": []})

                    if 'Text' in block:
                        # כאן קורה הקסם: אם זה עדיין ג'יבריש, אנחנו נדע מהלוג
                        pages_data[p_num - 1]["lines"].append(block['Text'])

            next_token = result.get('NextToken')
            if not next_token: break

        # 3. השמירה הקריטית - UTF-8 ו-Charset
        index_key = f".index/{document_key.rsplit('.', 1)[0]}.json"
        json_body = json.dumps({"pages": pages_data}, ensure_ascii=False).encode('utf-8')

        s3_client.put_object(
            Bucket=bucket_name,
            Key=index_key,
            Body=json_body,
            ContentType='application/json; charset=utf-8'  # זה מה שמונע ג'יבריש בדפדפן
        )
        print(f"✅ Created index for {len(pages_data)} pages with UTF-8 encoding")
        return True

    except Exception as e:
        print(f"❌ OCR Error: {str(e)}")
        return False


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

