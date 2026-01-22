#Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# PS C:\Users\orenm\Dropbox\my_doc\Python\Smart_Doc_Searcher> .\git_upload.ps1

# 1. הצגת סטטוס נוכחי
git status


$ver = "v27.8.2"
$comment = "aws - Azure supports AI search"

# 2. בקשת אישור מהמשתמש
Write-Host "-------- $ver - $comment --------" -ForegroundColor Cyan
$confirmation = Read-Host "Keep on commit and push to +++ $ver +++  ? (y/n)"
if ($confirmation -ne 'y') {
    Write-Host "Operation cancelled by user." -ForegroundColor Yellow
    exit
}


# 3. הגדרות גרסה
$description = $comment
$commit_msg = "$ver $description"

Write-Host "--- Preparing to Push Version: $ver ---" -ForegroundColor Cyan

# 4. ביצוע הפעולות ב-Git
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