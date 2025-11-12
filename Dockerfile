# 1. בסיס: תמונת Python רשמית
FROM python:3.11-slim

# 2. התקנת תלויות מערכת (לינוקס) עבור PyMuPDF וכלים אחרים
# חבילות כמו libopenjp2-7, libjpeg-dev ו-build-essential עוזרות לרינדור אמין של תמונות/PDFs
# build-essential נחוץ להידור חבילות פייתון מורכבות כמו PyMuPDF
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libopenjp2-7 \
        libjpeg-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. הגדרת משתנים וסביבת עבודה
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME

# 4. התקנת חבילות Python
COPY requirements.txt .
# התקנת requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 5. העתקת הקוד
COPY . .

# 6. הגדרת הפורט
EXPOSE 8080

# 7. פקודת ההרצה
# CORRECTION: הפניה נכונה למודול 'api_server' ולאפליקציה 'app'
CMD ["gunicorn", "-b", "0.0.0.0:8080", "api_server:app"]