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
| `VITE_FIREBASE_API_KEY` | Firebase Web app の API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase Authentication の auth domain |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID。通常は `GCP_PROJECT_ID` と同じ |
| `VITE_FIREBASE_APP_ID` | Firebase Web app の app ID |

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

## Firebase Authentication

Firebase Console で対象 Google Cloud project の Firebase project を開き、Authentication の Sign-in method で Google provider を有効にします。
Authorized domains には frontend Cloud Run の既定 domain と、利用する custom domain を追加します。既定 domain は Terraform の
frontend service 名と project number から `knowledge-drills-prd-frontend-96923902284.asia-northeast1.run.app`
になります。local 動作確認では `localhost` も有効 domain に含めます。

Firebase Web app の設定から API key、auth domain、project ID、app ID を取得し、GitHub repository variables の
`VITE_FIREBASE_API_KEY`、`VITE_FIREBASE_AUTH_DOMAIN`、`VITE_FIREBASE_PROJECT_ID`、`VITE_FIREBASE_APP_ID`
に設定します。CD workflow はこれらが未設定の場合、frontend image build より前に失敗します。

## Backend 認証 env

local backend の既定は `KNOWLEDGE_DRILLS_AUTH_MODE=none` で、外部 Firebase project に依存せず開発できます。
production Cloud Run では Terraform が backend service に `KNOWLEDGE_DRILLS_AUTH_MODE=firebase` と
`KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID=<GCP project id>` を設定します。deploy 前に `terraform plan` の
`google_cloud_run_v2_service.backend` でこの 2 つの env が追加または維持されることを確認します。

## 既存データの owner 移行

この仕様以降、owner 画面の Course / Drill / Patch は `Course.ownerUserId` を起点に認可されます。
既存の ownerless Course は、認証済み owner からは 404 として扱われ、一覧にも表示されません。

demo Course を残す場合は、最初に Google ログインした owner の Firebase UID を確認し、Firestore の対象
`courses/{courseId}` document に `ownerUserId` を設定します。子リソースの Drill / Patch は Course を辿って
owner 判定されるため、まず Course の owner を移行します。demo データを維持しない場合は、ログイン後に UI から
Course を作り直し、Drill と share URL を再生成します。

## ADK trace

backend Cloud Run は `KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER=gcp` で ADK trace を Cloud Trace に送ります。
確認先は Google Cloud Console の Trace Explorer です。`service.name` は
`knowledge-drills-prd-backend`、resource attribute には `deployment.environment=prd` と
`service.namespace=knowledge-drills` が入ります。

OTLP collector に送る場合は `KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER=otlp` に変更し、
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` または `OTEL_EXPORTER_OTLP_ENDPOINT` を Cloud Run env に追加します。
