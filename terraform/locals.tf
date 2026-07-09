locals {
  project_id     = "onyx-harmony-457309-p9"
  project_number = "96923902284"
  region         = "asia-northeast1"
  environment    = "prd"

  project_name = "knowledge-drills"

  frontend_service_name         = "${local.project_name}-${local.environment}-frontend"
  backend_service_name          = "${local.project_name}-${local.environment}-backend"
  frontend_service_account_id   = "${local.project_name}-${local.environment}-frontend"
  backend_service_account_id    = "${local.project_name}-${local.environment}-backend"
  deploy_service_account_id     = "${local.project_name}-${local.environment}-deploy"
  agent_eval_service_account_id = "${local.project_name}-${local.environment}-eval"
  artifact_repository_id        = "${local.project_name}-${local.environment}"
  github_repository             = "tomomj/knowledge-drills"
  github_wif_pool_id            = "${local.project_name}-${local.environment}-github"
  github_wif_provider_id        = "github-actions"
  github_eval_wif_provider_id   = "github-actions-agent-eval"

  # Terraform bootstraps Cloud Run with a known public image. CI/CD should deploy
  # the real frontend/backend images after the services and Artifact Registry exist.
  bootstrap_container_image = "us-docker.pkg.dev/cloudrun/container/hello"

  backend_max_instances  = 3
  frontend_max_instances = 2

  # Local backend default stays auth_mode=none; production Cloud Run uses Firebase auth.
  backend_auth_mode                = "firebase"
  backend_firebase_project_id      = local.project_id
  backend_storage_mode             = "firestore"
  backend_agent_mode               = "adk"
  backend_agent_model              = "gemini-3.1-flash-lite"
  backend_agent_timeout_seconds    = "120"
  backend_agent_trace_exporter     = "gcp"
  backend_agent_trace_service_name = "${local.project_name}-${local.environment}-backend"
  backend_agent_trace_resource_attributes = join(",", [
    "deployment.environment=${local.environment}",
    "gcp.project_id=${local.project_id}",
    "service.namespace=${local.project_name}",
  ])
  backend_vertex_location = "global"
  firestore_database_id   = "${local.project_name}-${local.environment}"
  firestore_location      = local.region

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
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudtrace.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "serviceusage.googleapis.com",
    "sts.googleapis.com",
    "telemetry.googleapis.com",
  ])
}
