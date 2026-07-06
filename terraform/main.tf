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
        name  = "KNOWLEDGE_DRILLS_CORS_ALLOWED_ORIGINS"
        value = google_cloud_run_v2_service.frontend.uri
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

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "artifact_registry_repository" {
  value = "${local.region}-docker.pkg.dev/${local.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
