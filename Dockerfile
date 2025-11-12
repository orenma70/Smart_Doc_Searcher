# 1. בסיס: תמונת Python רשמית
FROM python:3.11-slim

# 2. התקנת תלויות מערכת (לינוקס) עבור PyMuPDF וכלים אחרים
# חבילות כמו libopenjp2-7 ו-libjpeg-dev עוזרות לרינדור אמין של תמונות/PDFs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libopenjp2-7 \
        libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. הגדרת משתנים וסביבת עבודה
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME

# 4. התקנת חבילות Python
COPY requirements.txt .
# התקנת requirements.txt (יטפל בהתקנת PyMuPDF)
RUN pip install --no-cache-dir -r requirements.txt [cite: 2]

# 5. העתקת הקוד
COPY . .

# 6. הגדרת הפורט
EXPOSE 8080 [cite: 3]

# 7. פקודת ההרצה
# **CORRECTION: Pointing to api_server.py instead of main.py**
CMD ["gunicorn", "-b", "0.0.0.0:8080", "api_server:app"]