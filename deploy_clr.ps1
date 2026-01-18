# 1. Configuration (Fixed the name typo)
$ver_name = "smart-doc-searcher-v27-api"

# 2. Safety Check: Pull Gemini Key from YOUR local session
$gemini_key = $env:GEMINI_API_KEY

if (-not $gemini_key) {
    Write-Host "Error: GEMINI_API_KEY is not set in your session." -ForegroundColor Red
    Write-Host "Please run: `$env:GEMINI_API_KEY = 'YOUR_KEY_HERE'"
    exit
}

# 3. Deploy with Security, Resource settings, and Instant Logging
gcloud run deploy $ver_name `
  --source . `
  --region us-central1 `
  --allow-unauthenticated `
  --memory 1Gi `
  --timeout 300 `
  --set-env-vars "GEMINI_API_KEY=$gemini_key,PYTHONUNBUFFERED=1"


# 4. Success: Get the URL and Open Browser
if ($LASTEXITCODE -eq 0) {
    # Get the official URL from Google
    $actual_url = gcloud run services describe $ver_name --region us-central1 --format='value(status.url)'
    $version_url = "$actual_url/version"
    
    Write-Host "`n🚀 Deployment Successful!" -ForegroundColor Green
    Write-Host "Opening: $version_url" -ForegroundColor Cyan
    
    # Open the default browser to the /version endpoint
    Start-Process $version_url
}