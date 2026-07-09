# Terraform

`terraform/` は Knowledge Drills の GCP production インフラを管理する小さな root module です。
Cloud Run、Artifact Registry、Firestore、GitHub Actions Workload Identity Federation、
service account、IAM をこのディレクトリで扱います。

## 構成

| ファイル | 内容 |
|---|---|
| `backend.tf` | GCS remote state。bucket は事前作成が必要 |
| `provider.tf` | Terraform version、Google provider、project/region |
| `locals.tf` | project、region、service 名、Cloud Run env、API、labels |
| `main.tf` | GCP resources、IAM、outputs |

環境差分は `locals.tf` に置きます。現行は `environment = "prd"` の単一環境です。

## 管理対象

- 有効化する Google APIs
- Artifact Registry Docker repository
- Cloud Run v2 services: frontend / backend
- Service accounts: frontend / backend / deploy / agent eval
- Firestore Native database
- GitHub Actions Workload Identity Pool / Provider
- Cloud Run public invoker IAM
- deploy service account の Artifact Registry / Cloud Run / service account 権限
- backend service account の Vertex AI、Firestore、Cloud Trace 権限
- agent eval service account の Vertex AI 権限

Cloud Run の初回 image は bootstrap 用の
`us-docker.pkg.dev/cloudrun/container/hello` です。実アプリ image は GitHub Actions CD が
deploy するため、Terraform は Cloud Run image の `ignore_changes` を維持します。

## 有効化する API

`locals.tf` の `required_services` で次を有効化します。

- `aiplatform.googleapis.com`
- `artifactregistry.googleapis.com`
- `cloudtrace.googleapis.com`
- `firestore.googleapis.com`
- `iam.googleapis.com`
- `iamcredentials.googleapis.com`
- `run.googleapis.com`
- `serviceusage.googleapis.com`
- `sts.googleapis.com`
- `telemetry.googleapis.com`

API を追加した場合は、該当 resource の `depends_on` も確認します。

## Cloud Run 設定

frontend / backend はどちらも `min_instance_count = 0` で scale to zero します。

| Service | 主な設定 |
|---|---|
| frontend | concurrency 80、timeout 60s、max instances 2、memory 512Mi |
| backend | concurrency 20、timeout 300s、max instances 3、memory 1Gi |

backend には主に次の環境変数を設定します。

- `KNOWLEDGE_DRILLS_ENVIRONMENT`
- `KNOWLEDGE_DRILLS_STORAGE_MODE=firestore`
- `KNOWLEDGE_DRILLS_AUTH_MODE=firebase`
- `KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID`
- `KNOWLEDGE_DRILLS_FIRESTORE_DATABASE`
- `KNOWLEDGE_DRILLS_AGENT_MODE=adk`
- `KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS`
- `KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER=gcp`
- `KNOWLEDGE_DRILLS_CORS_ALLOWED_ORIGINS`
- `GOOGLE_GENAI_USE_VERTEXAI=TRUE`
- `GOOGLE_CLOUD_LOCATION`
- `KNOWLEDGE_DRILL_AGENT_MODEL`

## GitHub Actions WIF

deploy 用 provider は `tomomj/knowledge-drills` の `main` branch を信頼します。agent eval 用
provider は `Agent Eval` workflow の `pull_request` と `workflow_dispatch` を信頼します。

Terraform apply 後、GitHub repository variables には outputs の値を設定します。

| Output | 用途 |
|---|---|
| `github_actions_workload_identity_provider` | deploy workflow の WIF provider |
| `github_actions_service_account` | deploy workflow の service account |
| `github_actions_agent_eval_workload_identity_provider` | agent eval workflow の WIF provider |
| `github_actions_agent_eval_service_account` | agent eval workflow の service account |

## 実行手順

```sh
cd terraform
terraform init
terraform fmt
terraform validate
terraform plan
```

backend 設定や state bucket を変更した場合は次を使います。

```sh
terraform init -reconfigure
```

`terraform apply` は実インフラを変更するため、plan の内容を確認してから明示的に実行します。
secret や credentials は Terraform に書かず、WIF と service account 権限で扱います。

## 実行権限

Terraform 実行アカウントには、少なくとも次の操作権限が必要です。

- GCS state bucket への object 管理
- API 有効化
- Artifact Registry 管理
- Cloud Run 管理
- Firestore database 管理
- service account と IAM policy 管理
- Workload Identity Pool / Provider 管理

運用時は最小権限を優先し、`roles/owner` のような広すぎる project 権限を常用しません。

## 注意点

- `*.tfvars` は使わず、環境差分は `locals.tf` に集約します。
- Firestore は deletion protection と `deletion_policy = "ABANDON"` を使っています。
- backend の Vertex AI location は Cloud Run region と一致するとは限らないため、
  `backend_vertex_location` を使います。
- resource 分割は `main.tf` がレビュー困難になった場合だけ行います。
