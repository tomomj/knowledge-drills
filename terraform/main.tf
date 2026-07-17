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

resource "google_service_account" "agent_eval" {
  project      = local.project_id
  account_id   = local.agent_eval_service_account_id
  display_name = "Knowledge Drills GitHub Actions agent eval ${local.environment}"

  depends_on = [
    google_project_service.required["iam.googleapis.com"],
  ]
}

resource "google_firestore_database" "app" {
  project                     = local.project_id
  name                        = local.firestore_database_id
  location_id                 = local.firestore_location
  type                        = "FIRESTORE_NATIVE"
  concurrency_mode            = "OPTIMISTIC"
  app_engine_integration_mode = "DISABLED"
  delete_protection_state     = "DELETE_PROTECTION_ENABLED"
  deletion_policy             = "ABANDON"

  depends_on = [
    google_project_service.required["firestore.googleapis.com"],
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

resource "google_iam_workload_identity_pool_provider" "github_actions_agent_eval" {
  project                            = local.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = local.github_eval_wif_provider_id
  display_name                       = "GitHub Actions Agent Eval"
  description                        = "Trust GitHub Actions OIDC tokens for Agent Eval on pull requests, main pushes, and manual runs."
  disabled                           = false
  attribute_condition = join(" && ", [
    "assertion.repository == \"${local.github_repository}\"",
    "assertion.workflow == \"Agent Eval\"",
    "((assertion.event_name == \"pull_request\" && assertion.actor == \"tomomj\") || assertion.event_name == \"workflow_dispatch\" || (assertion.event_name == \"push\" && assertion.ref == \"refs/heads/main\"))",
  ])

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.event_name" = "assertion.event_name"
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
        name  = "KNOWLEDGE_DRILLS_STORAGE_MODE"
        value = local.backend_storage_mode
      }

      env {
        name  = "KNOWLEDGE_DRILLS_AUTH_MODE"
        value = local.backend_auth_mode
      }

      env {
        name  = "KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID"
        value = local.backend_firebase_project_id
      }

      env {
        name  = "KNOWLEDGE_DRILLS_FIRESTORE_DATABASE"
        value = local.firestore_database_id
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
        name  = "KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER"
        value = local.backend_agent_trace_exporter
      }

      env {
        name  = "KNOWLEDGE_DRILLS_AGENT_TRACE_SERVICE_NAME"
        value = local.backend_agent_trace_service_name
      }

      env {
        name  = "KNOWLEDGE_DRILLS_AGENT_TRACE_RESOURCE_ATTRIBUTES"
        value = local.backend_agent_trace_resource_attributes
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
        cpu_idle          = false
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

resource "google_project_iam_member" "backend_cloud_trace_agent" {
  project = local.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.backend.email}"

  depends_on = [
    google_project_service.required["cloudtrace.googleapis.com"],
  ]
}

resource "google_project_iam_member" "agent_eval_vertex_ai_user" {
  project = local.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_eval.email}"

  depends_on = [
    google_project_service.required["aiplatform.googleapis.com"],
  ]
}

resource "google_project_iam_member" "backend_firestore_user" {
  project = local.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.backend.email}"

  depends_on = [
    google_firestore_database.app,
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

resource "google_service_account_iam_member" "agent_eval_workload_identity_user" {
  service_account_id = google_service_account.agent_eval.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.github_repository}"
}

resource "google_monitoring_notification_channel" "email_alerts" {
  project      = local.project_id
  display_name = "Knowledge Drills ${local.environment} alerts email"
  type         = "email"

  labels = {
    email_address = local.alert_email
  }

  depends_on = [
    google_project_service.required["monitoring.googleapis.com"],
  ]
}

resource "google_monitoring_uptime_check_config" "frontend" {
  project      = local.project_id
  display_name = "${local.frontend_service_name}-uptime"
  timeout      = local.uptime_check_timeout
  period       = local.uptime_check_period

  selected_regions = local.uptime_check_regions

  http_check {
    path         = "/"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"

    labels = {
      project_id = local.project_id
      host       = trimprefix(google_cloud_run_v2_service.frontend.uri, "https://")
    }
  }

  depends_on = [
    google_project_service.required["monitoring.googleapis.com"],
  ]
}

resource "google_monitoring_alert_policy" "frontend_uptime" {
  project      = local.project_id
  display_name = "${local.frontend_service_name} uptime failure"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check failed for ${local.frontend_service_name}"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"uptime_url\"",
        "metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\"",
        "metric.labels.check_id = \"${google_monitoring_uptime_check_config.frontend.uptime_check_id}\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "60s"

      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields = [
          "resource.label.project_id",
          "resource.label.host",
        ]
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email_alerts.id,
  ]

  documentation {
    content   = "Frontend Cloud Run (${local.frontend_service_name}) の uptime check が複数リージョンで失敗しています。Cloud Run のステータスと直近のデプロイを確認してください。"
    mime_type = "text/markdown"
  }
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

output "github_actions_agent_eval_service_account" {
  value = google_service_account.agent_eval.email
}

output "github_actions_agent_eval_workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github_actions_agent_eval.name
}
