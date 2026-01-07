# Variables
$ECR_URL = "038715112888.dkr.ecr.ap-southeast-2.amazonaws.com/smart-doc-api:latest"
$SERVICE_ARN = "arn:aws:apprunner:ap-southeast-2:038715112888:service/smart-doc-searcher-api-final/5abc7f51e3a04885bf68e15c4980927f"

Write-Host "--- 1. Building Image ---" -ForegroundColor Cyan
docker build -t smart-doc-api .

Write-Host "--- 2. Tagging and Pushing to ECR ---" -ForegroundColor Cyan
docker tag smart-doc-api:latest $ECR_URL
docker push $ECR_URL

Write-Host "--- 3. Triggering AWS Deployment ---" -ForegroundColor Cyan
aws apprunner start-deployment --service-arn $SERVICE_ARN --region ap-southeast-2

Write-Host "Done! Wait a few minutes for the status to become RUNNING." -ForegroundColor Green