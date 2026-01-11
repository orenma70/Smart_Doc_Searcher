import re


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

