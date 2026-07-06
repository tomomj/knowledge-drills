locals {
  project_id  = "onyx-harmony-457309-p9"
  region      = "asia-northeast1"
  environment = "prd"

  project_name = "knowledge-drills"

  frontend_service_name       = "${local.project_name}-${local.environment}-frontend"
  backend_service_name        = "${local.project_name}-${local.environment}-backend"
  frontend_service_account_id = "${local.project_name}-${local.environment}-frontend"
  backend_service_account_id  = "${local.project_name}-${local.environment}-backend"
  artifact_repository_id      = "${local.project_name}-${local.environment}"

  # Terraform bootstraps Cloud Run with a known public image. CI/CD should deploy
  # the real frontend/backend images after the services and Artifact Registry exist.
  bootstrap_container_image = "us-docker.pkg.dev/cloudrun/container/hello"

  backend_max_instances  = 3
  frontend_max_instances = 2

  labels = {
    app         = local.project_name
    environment = local.environment
    managed_by  = "terraform"
  }

  required_services = toset([
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "serviceusage.googleapis.com",
  ])
}
