# ☁️ Cloud Run & GCS Configuration - smart-doc-searcher-api

This file documents the critical configuration settings that are applied directly in the Google Cloud Console for the stable RAG API service. These settings correspond to the Cloud Run revision tagged as **stable-v1-0-rag-fix**.

## 1. Cloud Run Service Details

| Setting | Value | Rationale |
| :--- | :--- | :--- |
| **Service Name** | `smart-doc-searcher-api` | Name used in the deployment command. |
| **Region** | `us-central1` | Region where the service is deployed. |
| **Minimum Instances** | **[PLACEHOLDER - MIN INSTANCES]** | **CRITICAL for cost/performance.** `0` saves money but causes cold starts. `1` or higher is better for low latency. |
| **Maximum Instances** | **[PLACEHOLDER - MAX INSTANCES]** | Limits scaling and max spend (e.g., `10`). |
| **Revision Tag** | `stable-v1-0-rag-fix` | The manual tag applied to the working configuration. |
| **Timeout** | 300 seconds (Default) | Verified as sufficient for the RAG pipeline. |
| **CPU Allocation** | CPU is only allocated during request processing | Recommended setting for cost-efficiency. |

## 2. Environment Variables & Secrets

The application relies on environment variables for secure access.

| Variable Name | Value Type / Source | Location in Console |
| :--- | :--- | :--- |
| **`GEMINI_API_KEY`** | AIzaSyDjIgFhkq8HVzeEK6yErg03BKLNRwWdwMk | **This must be set in the Cloud Run Environment Variables or Secret Manager.** |
| **`BUCKET_NAME`** | `oren-smart-search-docs-1205` | The GCS bucket containing the source PDF documents. |

## 3. Identity and Access Management (IAM)

The Service Account must have the necessary permissions to read GCS files. ## serviceAccountName - 359127107055-compute@developer.gserviceaccount.com

| Setting | Value | Permissions Rationale |
| :--- | :--- | :--- |
| **Service Account ID** | 359127107055-compute@developer.gserviceaccount.com |
| **Required GCS Role** | `Storage Object Viewer` | The minimum required role to read files from the bucket. |

---
## 4. Deployment Command

This is the verified, working command used to deploy this exact version of the code:

```bash
gcloud run deploy smart-doc-searcher-api --source . --region us-central1 --allow-unauthenticated