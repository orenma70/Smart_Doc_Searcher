# ==========================================
# Azure Deployment Script - Smart Doc Searcher
# ==========================================


# 1. הגדרות משתנים
$ver_name = "v26.1.0"
$rg_name = "SmartSearch-RG"
$acr_name = "smartsearchregoren"
$app_name = "smart-doc-searcher-api"
$image_full_name = "${acr_name}.azurecr.io/smart-doc-api:${ver_name}"

Write-Host "--- Starting Deploy for Version: $ver_name ---" -ForegroundColor Cyan

# 2. בניית ה-Image בתוך ה-ACR
Write-Host "--- Step 1: Building Docker Image in Azure ---" -ForegroundColor Yellow
az acr build --registry $acr_name --image "smart-doc-api:${ver_name}" --file Dockerfile_azure .

if ($LASTEXITCODE -ne 0) { 
    Write-Host "Build Failed! Exiting..." -ForegroundColor Red
    exit 
}

# 3. עדכון ה-Container App - שים לב לתוספת ה-set-env-vars
Write-Host "--- Step 2: Updating Container App to $ver_name ---" -ForegroundColor Yellow

$envVars = @(
    "APP_VERSION=$ver_name",
    "AZURE_SEARCH_INDEX=azureblob-index2",                # השם הנכון שמצאת!
        "azure-key-search=secretref:azure-key-search",       # שימוש ב-Secret הקיים
    "azuresmartsearch3key1conn=secretref:azuresmartsearch3key1conn" # תיקון השם ל-A גדולה
)

az containerapp revision set-mode `
    --name $app_name `
    --resource-group $rg_name `
    --mode single

az containerapp update `
    --name $app_name `
    --resource-group $rg_name `
    --image $image_full_name `
    --set-env-vars $envVars


if ($LASTEXITCODE -ne 0) { 
    Write-Host "Update Failed!" -ForegroundColor Red
} else {
    Write-Host "--- Successfully Deployed $ver_name! ---" -ForegroundColor Green
}

# 4. הצגת הכתובת הסופית לבדיקה
$fqdn = az containerapp show --name $app_name --resource-group $rg_name --query properties.configuration.ingress.fqdn -o tsv
Write-Host "Live URL: https://$fqdn/version" -ForegroundColor White