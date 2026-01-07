# Variables
$ECR_URL = "038715112888.dkr.ecr.ap-southeast-2.amazonaws.com/smart-doc-api:latest"
$SERVICE_ARN = "arn:aws:apprunner:ap-southeast-2:038715112888:service/smart-doc-searcher-api-final/5abc7f51e3a04885bf68e15c4980927f"

Write-Host "--- 1. Building Image ---" -ForegroundColor Cyan
docker build -t smart-doc-api .

Write-Host "--- 2. Tagging and Pushing to ECR ---" -ForegroundColor Cyan
docker tag smart-doc-api:latest $ECR_URL
docker push $ECR_URL

Write-Host "--- 3. Triggering AWS Deployment (Ensuring Port 8080) ---" -ForegroundColor Cyan

# שימוש ב-Here-String שומר על ה-JSON נקי לגמרי
$sourceConfig = @"
{
    "ImageRepository": {
        "ImageIdentifier": "$ECR_URL",
        "ImageRepositoryType": "ECR",	
        "ImageConfiguration": { "Port": "8080" }
    }
}
"@

# שליחת הפקודה
aws apprunner update-service --service-arn $SERVICE_ARN --source-configuration $sourceConfig

Write-Host "--- 4. Monitoring Deployment ---" -ForegroundColor Cyan
while ($true) {
    $status = aws apprunner describe-service --service-arn $SERVICE_ARN --query "Service.Status" --output text
    Write-Host "Current Status: $status"
    
    if ($status -eq "RUNNING") {
        Write-Host "AWS reports RUNNING. Waiting 30s for traffic routing..." -ForegroundColor Yellow
        Start-Sleep -Seconds 30
        
        $url = aws apprunner describe-service --service-arn $SERVICE_ARN --query "Service.ServiceUrl" --output text
        $fullUrl = "https://$url"
        
        Write-Host "Opening: $fullUrl" -ForegroundColor Green
        Start-Process $fullUrl
        break
    } elseif ($status -contains "ROLLBACK") {
        Write-Host "Deployment Failed. Check AWS Logs." -ForegroundColor Red
        break
    }
    Start-Sleep -Seconds 15
}

Write-Host "Done! Wait a few minutes for the status to become RUNNING." -ForegroundColor Green