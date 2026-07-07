# デプロイ

`main` の CI が成功すると、GitHub Actions の `CD` workflow が Cloud Run に backend/frontend をデプロイします。手動実行も `workflow_dispatch` から可能です。

## 前提

Terraform で次のリソースが作成済みであることを前提にします。

- Artifact Registry repository
- Cloud Run backend service
- Cloud Run frontend service
- GitHub Actions から利用する deploy 用 service account
- GitHub Actions OIDC 用の Workload Identity Federation

長期 service account key は使いません。GitHub Actions の OIDC と Workload Identity Federation で Google Cloud に認証します。

## Repository Variables

GitHub repository の `Settings` -> `Secrets and variables` -> `Actions` -> `Variables` に次を設定します。

| Name | 内容 |
| --- | --- |
| `GCP_PROJECT_ID` | デプロイ先 Google Cloud project ID |
| `GCP_REGION` | Cloud Run / Artifact Registry の region |
| `ARTIFACT_REGISTRY_REPOSITORY` | Docker image を push する Artifact Registry repository ID |
| `CLOUD_RUN_BACKEND_SERVICE` | backend の Cloud Run service 名 |
| `CLOUD_RUN_FRONTEND_SERVICE` | frontend の Cloud Run service 名 |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity Provider の full resource name |
| `GCP_SERVICE_ACCOUNT` | GitHub Actions が impersonate する service account email |
| `KNOWLEDGE_DRILLS_ENVIRONMENT` | backend に渡す環境名。未設定の場合は `prd` |

## deploy 用 service account の権限

deploy 用 service account には少なくとも次が必要です。

- `roles/run.admin`
- `roles/artifactregistry.writer`
- Cloud Run runtime service account への `roles/iam.serviceAccountUser`

Workload Identity Federation 側では、GitHub Actions の principal に deploy 用 service account の `roles/iam.workloadIdentityUser` を付与します。

## コンテナ

- backend image は `backend/Dockerfile` で build します。
- frontend image は `frontend/Dockerfile` で build します。
- frontend の `VITE_API_BASE_URL` は、CD 中に backend Cloud Run URL を取得して build arg として渡します。

Cloud Run は Terraform 側で `min_instance_count = 0` にしているため、アイドル時は scale to zero します。
