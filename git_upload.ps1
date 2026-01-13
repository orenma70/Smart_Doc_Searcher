#Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# PS C:\Users\orenm\Dropbox\my_doc\Python\Smart_Doc_Searcher> .\git_upload.ps1

$ver = "v23.1.2	"
$description = "Arch: improve Implement Path-Based Caching"

# 2. בניית מחרוזות ה-Commit וה-Tag
$commit_msg = "$ver $description"

Write-Host "--- Preparing to Push Version: $ver ---" -ForegroundColor Cyan

# 3. ביצוע הפעולות ב-Git
git add .

# ביצוע Commit (רק אם יש שינויים)
git commit -m $commit_msg

if ($LASTEXITCODE -eq 0) {
    Write-Host "--- Creating Tag: $ver ---" -ForegroundColor Yellow
    
    # יצירת תגית (דורס תגית קיימת באותו שם אם צריך בעזרת -f)
    git tag -a $ver -m $description -f
    
    Write-Host "--- Pushing to Origin (Main + Tags) ---" -ForegroundColor Green
    git push origin main --tags --force
} else {
    Write-Host "No changes to commit or Git error occurred." -ForegroundColor Red
}