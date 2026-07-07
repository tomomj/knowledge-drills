locals {
  project_id     = "onyx-harmony-457309-p9"
  project_number = "96923902284"
  region         = "asia-northeast1"
  environment    = "prd"

  project_name = "knowledge-drills"

  frontend_service_name       = "${local.project_name}-${local.environment}-frontend"
  backend_service_name        = "${local.project_name}-${local.environment}-backend"
  frontend_service_account_id = "${local.project_name}-${local.environment}-frontend"
  backend_service_account_id  = "${local.project_name}-${local.environment}-backend"
  deploy_service_account_id   = "${local.project_name}-${local.environment}-deploy"
  artifact_repository_id      = "${local.project_name}-${local.environment}"
  github_repository           = "tomomj/knowledge-drills"
  github_wif_pool_id          = "${local.project_name}-${local.environment}-github"
  github_wif_provider_id      = "github-actions"

  # Terraform bootstraps Cloud Run with a known public image. CI/CD should deploy
  # the real frontend/backend images after the services and Artifact Registry exist.
  bootstrap_container_image = "us-docker.pkg.dev/cloudrun/container/hello"

  backend_max_instances  = 3
  frontend_max_instances = 2

  frontend_cloud_run_origins = [
    google_cloud_run_v2_service.frontend.uri,
    "https://${local.frontend_service_name}-${local.project_number}.${local.region}.run.app",
  ]

  labels = {
    app         = local.project_name
    environment = local.environment
    managed_by  = "terraform"
  }

  required_services = toset([
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "serviceusage.googleapis.com",
    "sts.googleapis.com",
  ])
}
