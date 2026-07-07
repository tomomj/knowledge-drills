resource "google_project_service" "required" {
  for_each = local.required_services

  project = local.project_id
  service = each.value

  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "containers" {
  project       = local.project_id
  location      = local.region
  repository_id = local.artifact_repository_id
  description   = "Docker images for Knowledge Drills ${local.environment}."
  format        = "DOCKER"

  labels = local.labels

  depends_on = [
    google_project_service.required["artifactregistry.googleapis.com"],
  ]
}

resource "google_service_account" "frontend" {
  project      = local.project_id
  account_id   = local.frontend_service_account_id
  display_name = "Knowledge Drills frontend ${local.environment}"

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
  ]
}

resource "google_service_account" "backend" {
  project      = local.project_id
  account_id   = local.backend_service_account_id
  display_name = "Knowledge Drills backend ${local.environment}"

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
  ]
}

resource "google_service_account" "deploy" {
  project      = local.project_id
  account_id   = local.deploy_service_account_id
  display_name = "Knowledge Drills GitHub Actions deploy ${local.environment}"

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
  ]
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = local.project_id
  workload_identity_pool_id = local.github_wif_pool_id
  display_name              = "KD GitHub Actions ${local.environment}"
  description               = "OIDC pool for GitHub Actions deployments."
  disabled                  = false

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
    google_project_service.required["sts.googleapis.com"],
  ]
}

resource "google_iam_workload_identity_pool_provider" "github_actions" {
  project                            = local.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = local.github_wif_provider_id
  display_name                       = "GitHub Actions"
  description                        = "Trust GitHub Actions OIDC tokens from ${local.github_repository} main."
  disabled                           = false
  attribute_condition                = "assertion.repository == \"${local.github_repository}\" && assertion.ref == \"refs/heads/main\""

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.workflow"   = "assertion.workflow"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_cloud_run_v2_service" "frontend" {
  project             = local.project_id
  name                = local.frontend_service_name
  location            = local.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = local.labels

  template {
    service_account                  = google_service_account.frontend.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 80
    timeout                          = "60s"

    scaling {
      min_instance_count = 0
      max_instance_count = local.frontend_max_instances
    }

    containers {
      image = local.bootstrap_container_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }

  depends_on = [
    google_project_service.required["run.googleapis.com"],
  ]
}

resource "google_cloud_run_v2_service" "backend" {
  project             = local.project_id
  name                = local.backend_service_name
  location            = local.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = local.labels

  template {
    service_account                  = google_service_account.backend.email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    max_instance_request_concurrency = 20
    timeout                          = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = local.backend_max_instances
    }

    containers {
      image = local.bootstrap_container_image

      ports {
        container_port = 8080
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = local.project_id
      }

      env {
        name  = "KNOWLEDGE_DRILLS_ENVIRONMENT"
        value = local.environment
      }

      env {
        name  = "KNOWLEDGE_DRILLS_AGENT_MODE"
        value = local.backend_agent_mode
      }

      env {
        name  = "KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS"
        value = local.backend_agent_timeout_seconds
      }

      env {
        name  = "KNOWLEDGE_DRILLS_CORS_ALLOWED_ORIGINS"
        value = join(",", local.frontend_cloud_run_origins)
      }

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "TRUE"
      }

      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = local.backend_vertex_location
      }

      env {
        name  = "KNOWLEDGE_DRILL_AGENT_MODEL"
        value = local.backend_agent_model
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }

  depends_on = [
    google_project_service.required["run.googleapis.com"],
  ]
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public_invoker" {
  project  = local.project_id
  location = google_cloud_run_v2_service.frontend.location
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "backend_public_invoker" {
  project  = local.project_id
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_project_iam_member" "deploy_cloud_run_admin" {
  project = local.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "backend_vertex_ai_user" {
  project = local.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.backend.email}"

  depends_on = [
    google_project_service.required["aiplatform.googleapis.com"],
  ]
}

resource "google_artifact_registry_repository_iam_member" "deploy_artifact_writer" {
  project    = local.project_id
  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_act_as_frontend" {
  service_account_id = google_service_account.frontend.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_act_as_backend" {
  service_account_id = google_service_account.backend.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_workload_identity_user" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.github_repository}"
}

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "artifact_registry_repository" {
  value = "${local.region}-docker.pkg.dev/${local.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}

output "github_actions_service_account" {
  value = google_service_account.deploy.email
}

output "github_actions_workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github_actions.name
}
