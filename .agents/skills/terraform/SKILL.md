---
name: terraform
description: Knowledge Drills の GCP 向け Terraform Infrastructure as Code 規約。Codex が terraform/ 配下で Google provider、Cloud Run、Artifact Registry、Firestore、IAM service account、GitHub Actions Workload Identity Federation、GCS backend、locals.tf、provider.tf、backend.tf、main.tf、terraform fmt/validate/plan を扱う実装・レビュー・説明を行うときに使う。
---

# Terraform GCP 規約

この repository の Terraform は GCP production 環境を `terraform/` 直下の小さな root module として管理する。AWS 前提や `environment/dev` / `environment/prd` 分割は使わない。

## 現行構成

```text
terraform/
├── README.md
├── backend.tf
├── locals.tf
├── main.tf
└── provider.tf
```

- `backend.tf`: GCS remote state。
- `provider.tf`: Terraform version と `hashicorp/google` provider、project/region。
- `locals.tf`: project、region、environment、service 名、Cloud Run env、required APIs、labels。
- `main.tf`: API enablement、Artifact Registry、service accounts、Firestore、GitHub WIF、Cloud Run、IAM を集約。

## 管理対象

- Artifact Registry Docker repository。
- Cloud Run v2 services: frontend / backend。
- Service accounts: frontend / backend / deploy。
- Firestore Native database。
- GitHub Actions Workload Identity Pool / Provider。
- Cloud Run public invoker IAM。
- deploy service account の Artifact Registry / Cloud Run / service account / viewer 権限。
- backend Cloud Run env: `KNOWLEDGE_DRILLS_*`, `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_LOCATION`, `KNOWLEDGE_DRILL_AGENT_MODEL`。

## 実装ルール

- 環境差分は `locals.tf` に置く。`*.tfvars` は作らない。
- secret や credentials は Terraform に書かない。GitHub WIF と service account 権限で扱う。
- Cloud Run image は Terraform では bootstrap image を使い、実アプリ image は GitHub Actions CD が deploy する。`ignore_changes` の image 設定を壊さない。
- backend の Vertex AI location は Cloud Run region と一致するとは限らない。`backend_vertex_location` を使い、現状は `us-central1`。
- `required_services` に API を追加した場合、該当 resource の `depends_on` も確認する。
- IAM は最小権限を優先する。`roles/owner` や広すぎる project 権限を追加しない。
- Firestore は deletion protection と `deletion_policy = "ABANDON"` を慎重に扱う。
- リソースを分割ファイル化するのは、`main.tf` がレビュー困難になった場合だけ。小規模な変更では既存構成を維持する。

## 変更時の確認

```bash
cd terraform
terraform fmt
terraform validate
terraform plan
```

remote state や provider 設定を変えた場合:

```bash
terraform init -reconfigure
```

認証や state bucket がない環境では `fmt` まで実行し、`validate` / `plan` が実行できない理由を明示する。
