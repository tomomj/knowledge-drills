---
name: terraform
description: AWS 向け Terraform Infrastructure as Code のコーディング規約。Codex が Terraform ファイルを作成、リファクタリング、レビュー、説明するときに使う。特に terraform/environment/dev、terraform/environment/prd、環境別 locals.tf、root module の main.tf 集約、provider.tf、backend.tf、versions.tf、variables.tf、outputs.tf、tfenv 非生成、タグ、リモートステート、セキュリティ、検証手順を判断するときに使う。
---

# Terraform コーディング規約

Terraform の作成、編集、レビューではこの規約を適用する。対象は AWS 向け Terraform とする。過剰な汎用化よりも、実用性、レビュー容易性、環境差分の明示を優先する。

## 標準構成

新規作成では、原則として次の構成を使う。

```text
terraform/
├── main.tf
├── variables.tf
├── outputs.tf
├── versions.tf
└── environment/
    ├── dev/
    │   ├── backend.tf
    │   ├── locals.tf
    │   ├── main.tf
    │   └── provider.tf
    └── prd/
        ├── backend.tf
        ├── locals.tf
        ├── main.tf
        └── provider.tf
```

- `environment` は単数形を使う。`environments` にはしない。
- 標準環境は `dev` と `prd` にする。`stg` などは明示要求がある場合だけ追加する。
- 環境差分は各環境の `locals.tf` に置く。
- 環境別の `variables.tf` と `terraform.tfvars` は作らない。
- root module のリソース定義は基本的に `terraform/main.tf` に集約する。
- root module には `provider.tf` を置かない。provider は環境ディレクトリ側で設定する。

## 作成しないもの

次のファイルや手順は標準では作成しない。

- `.terraform-version`
- `.tfenv`
- tfenv の導入手順
- tfenv 前提の実行コマンド
- `terraform/environment/dev/variables.tf`
- `terraform/environment/prd/variables.tf`
- `terraform/environment/dev/terraform.tfvars`
- `terraform/environment/prd/terraform.tfvars`
- リソース種別ごとの `iam.tf`、`s3.tf`、`lambda.tf` などの初期分割ファイル

Terraform version は `terraform/versions.tf` の `required_version` で管理する。

## root module

root module は環境に依存しないリソース定義と module interface を持つ。

```text
terraform/
├── main.tf       # AWS リソース定義を集約
├── variables.tf  # 必要な入力だけ
├── outputs.tf    # 必要な出力だけ
└── versions.tf   # Terraform と provider の制約
```

### main.tf

- インフラリソース定義は `main.tf` に集約する。
- リソースタイプごとのファイル分割は、明示要求または大規模化するまで避ける。
- 常に作成するリソースに `count = var.create_x ? 1 : 0` のような feature flag を付けない。
- versioning、lifecycle policy、条件付き作成は実際に必要な場合だけ追加する。

### variables.tf

実際に使う入力だけを定義する。変数名は snake_case にする。

```hcl
variable "environment" {
  description = "Deployment environment."
  type        = string

  validation {
    condition     = contains(["dev", "prd"], var.environment)
    error_message = "Environment must be one of: dev, prd."
  }
}

variable "region" {
  description = "AWS region."
  type        = string
}

variable "project_name" {
  description = "Project name used for resource naming."
  type        = string
}
```

`default_tags` を再現するためだけの `tags` 変数は作らない。

### outputs.tf

他の作業や運用で実際に参照する値だけを出力する。将来使うかもしれない値は出力しない。

### versions.tf

Terraform と provider の制約を明示する。

```hcl
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

## 環境ディレクトリ

各環境ディレクトリは、backend、locals、module 呼び出し、provider だけを持つ。

### locals.tf

環境固有値は `locals.tf` に集約する。

```hcl
locals {
  environment  = "dev"
  region       = "ap-northeast-1"
  project_name = "your-project"

  # environment-specific settings only
}
```

- `environment`、`region`、`project_name` は必須にする。
- dev/prd の local key は可能な限り揃え、値だけを変える。
- secret は locals に置かない。

### main.tf

環境側 `main.tf` は root module 呼び出しに集中する。

```hcl
module "main" {
  source = "../.."

  environment  = local.environment
  region       = local.region
  project_name = local.project_name
}
```

### provider.tf

AWS provider は環境側で設定し、`default_tags` を使う。

```hcl
provider "aws" {
  region = local.region

  default_tags {
    tags = {
      Environment = local.environment
      Project     = local.project_name
      ManagedBy   = "terraform"
    }
  }
}
```

- 全リソースで `tags = local.common_tags` を繰り返すパターンは避ける。
- リソース固有 tag は必要な場合だけ対象リソースに追加する。

### backend.tf

S3 remote state を標準にし、環境別 key、暗号化、lockfile を設定する。

```hcl
terraform {
  backend "s3" {
    bucket       = "your-terraform-state"
    key          = "dev/terraform.tfstate"
    region       = "ap-northeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

- `prd` は `prd/terraform.tfstate` のように環境別 key を使う。
- backend bucket の作成は別途 bootstrap として扱う。
- DynamoDB locking は既存 Terraform version や platform 制約で必要な場合だけ使う。

## 命名

プロバイダー側の制約が許す場合、リソース名は project、environment、service、resource type、detail をもとに決める。

```hcl
resource "aws_s3_bucket" "main" {
  bucket = "${var.project_name}-${var.environment}-input"
}

resource "aws_lambda_function" "main" {
  function_name = "${var.project_name}-${var.environment}-worker"
}
```

Terraform local name は過剰に長くしない。単一用途の主要リソースは `main` を許容する。

## セキュリティ

- secret をハードコードしない。
- 機密値は環境変数、AWS Secrets Manager、または SSM Parameter Store を優先する。
- IAM policy は最小権限にする。
- IAM の wildcard `*` は最小限にし、必要性を説明できる場合だけ使う。
- secret を含む `terraform.tfvars` は作らない。

## 大規模化した場合

この skill の標準は小規模から中規模の Terraform を対象にする。次の条件に当てはまる場合は、root module `main.tf` 集約を見直し、module 分割を提案する。

- リソース数が概ね 100 個を超える。
- 複数サービスが独立して変更される。
- network、compute、storage、security などで明確に ownership が分かれる。
- 同じ構成を複数プロジェクトで再利用する。

module 分割する場合でも、環境差分は `environment/<env>/locals.tf` に置く方針を維持する。

## 既存リポジトリでの扱い

既存 Terraform 構成がある場合は、いきなり rename や再配置をしない。

1. 現在の構成を確認する。
2. この skill の標準構成との差分を説明する。
3. ユーザーが移行を求めた場合だけ、最小差分で移行する。
4. 既存の production state key や backend 設定は特に慎重に扱う。

## 検証

Terraform 作業後は、実行できる範囲で次を確認する。

```bash
terraform fmt -recursive
```

環境ごとに実行する。

```bash
cd terraform/environment/dev
terraform init
terraform validate
terraform plan
```

```bash
cd terraform/environment/prd
terraform init
terraform validate
terraform plan
```

AWS 認証、backend bucket、権限がないため実行できない場合は、実行不可理由とユーザーが確認すべき事項を明示する。`terraform apply` はユーザーが明示的に求めた場合だけ扱う。
