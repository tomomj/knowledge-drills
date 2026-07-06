# Terraform

Knowledge Drills の GCP インフラを作成する Terraform 定義です。

## デプロイ先

デプロイ先の project、region、environment、state backend は次のファイルで管理します。

- `locals.tf`
- `backend.tf`

## 作成するリソース

- Artifact Registry Docker repository
- Cloud Run service:
  - frontend
  - backend
- Service account:
  - frontend
  - backend
- Cloud Run invoker IAM:
  - frontend/backend を `allUsers` に公開

初回作成時の Cloud Run image は bootstrap 用の `us-docker.pkg.dev/cloudrun/container/hello` です。実アプリの image は Artifact Registry に push した後、別途 Cloud Run にデプロイします。

## 有効化する API

Terraform は次の API を有効化します。

- `artifactregistry.googleapis.com`
- `iam.googleapis.com`
- `run.googleapis.com`
- `serviceusage.googleapis.com`

手動で API を有効化する場合も、同じ API を有効にしてください。

## 実行手順

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

backend 設定を変更した場合は次を使います。

```bash
terraform init -reconfigure
```

## 実行権限

Terraform を実行するアカウントには少なくとも次が必要です。

- state bucket への `roles/storage.objectAdmin`
- Cloud Run 管理用の `roles/run.admin`
- Artifact Registry 管理用の `roles/artifactregistry.admin`
- service account 作成用の `roles/iam.serviceAccountAdmin`
- API 有効化用の `roles/serviceusage.serviceUsageAdmin`

初期構築を急ぐ場合は project-level の広い権限で作成し、運用時に Terraform 実行用 service account へ絞り込む方針にします。

## コスト設定

Cloud Run は frontend/backend ともに `min_instance_count = 0` です。アイドル時は scale to zero します。

同時に、上限は次の値に抑えています。

- frontend: `frontend_max_instances = 2`
- backend: `backend_max_instances = 3`

さらに費用を抑える場合は、これらを `1` に下げます。
