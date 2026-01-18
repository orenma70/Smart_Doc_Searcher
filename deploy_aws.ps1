# aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 038715112888.dkr.ecr.ap-southeast-2.amazonaws.com
# passwors lost rerun this


Write-Host "--- 0. login+Checking Docker Status  ---" -ForegroundColor Cyan
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 038715112888.dkr.ecr.ap-southeast-2.amazonaws.com



# Check if the docker command exists and if the engine is responding
docker info >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "X - ERROR: Docker Desktop is not running!" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and wait for the green light, then run this script again." -ForegroundColor Yellow
    exit
} else {
    Write-Host "V - Docker Desktop is running!" -ForegroundColor Green
}


# Variables
$ver_name = "v27.2.0"
$ECR_URL = "038715112888.dkr.ecr.ap-southeast-2.amazonaws.com/smart-doc-api:$ver_name"
$SERVICE_ARN = "arn:aws:apprunner:ap-southeast-2:038715112888:service/smart-doc-searcher-api-final/5abc7f51e3a04885bf68e15c4980927f"
$s3_name = "oren-smart-search-docs-amazon2"
Write-Host "--- 1. Preparing Dockerfile and Building Image ---" -ForegroundColor Cyan


docker build -f Dockerfile_amazon -t smart-doc-api:$ver_name .

Write-Host "--- 2. Tagging and Pushing to ECR ---" -ForegroundColor Cyan
docker tag smart-doc-api:$ver_name $ECR_URL
docker push $ECR_URL

Write-Host "--- 3. Triggering AWS Deployment (Ensuring Port 8080) ---" -ForegroundColor Cyan

# המבנה הנכון עבור App Runner: מילון פשוט של מפתח וערך
$configObject = @{
    ImageRepository = @{
        ImageIdentifier = $ECR_URL
        ImageRepositoryType = "ECR"
        ImageConfiguration = @{
            Port = "8080"
            RuntimeEnvironmentVariables = @{
                "APP_VERSION" = $ver_name
                "BUCKET_NAME" = $s3_name
                "AWS_REGION"  = "ap-southeast-2"             # AND THIS
            }
        }
    }
}
# הפיכה ל-JSON דחוס והוספת הלוכסנים (Escaping) עבור Windows
$sourceConfig = $configObject | ConvertTo-Json -Depth 10 -Compress
$sourceConfigEscaped = $sourceConfig.Replace('"', '\"')

# שליחה לאמזון
aws apprunner update-service --service-arn $SERVICE_ARN --source-configuration "$sourceConfigEscaped"

Write-Host "--- 4. Monitoring Deployment ---" -ForegroundColor Cyan
$total_sec = 0
$sec_int = 15

while ($true) {
    $status = aws apprunner describe-service --service-arn $SERVICE_ARN --query "Service.Status" --output text
    
    # הדפסת סטטוס עם זמן מצטבר
    Write-Host "Current Status: $status (Elapsed: ${total_sec}s)" 
    
    if ($status -eq "RUNNING") {
        Write-Host "--- Deployment Successful! ---" -ForegroundColor Green
        Write-Host "Total Time: ${total_sec} seconds"
        
        Write-Host "Waiting 10s for traffic routing..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
        
        $url = aws apprunner describe-service --service-arn $SERVICE_ARN --query "Service.ServiceUrl" --output text
        $fullUrl = "https://$url/version"
        
        Write-Host "Opening: $fullUrl" -ForegroundColor Green
        Start-Process $fullUrl
        break
    } elseif ($status -match "FAILED" -or $status -match "ROLLBACK") {
        Write-Host "Deployment Failed after ${total_sec}s. Check AWS Console Logs." -ForegroundColor Red
        break
    }

    Start-Sleep -Seconds $sec_int
    $total_sec += $sec_int
}

Write-Host "--- 5. Cleaning up old images ---" -ForegroundColor Cyan
docker image prune -f

Write-Host "Done! Wait a few minutes for the status to become RUNNING." -ForegroundColor Green