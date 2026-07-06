terraform {
  backend "gcs" {
    # Create this bucket before running `terraform init`.
    bucket = "knowledge-drills-terraform-state"
    prefix = "prd"
  }
}
