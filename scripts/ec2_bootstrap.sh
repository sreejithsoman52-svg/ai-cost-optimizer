#!/usr/bin/env bash
# Run this once on a fresh EC2 instance (Amazon Linux 2023) after cloning
# the repo, to install everything needed to build and deploy.
set -euo pipefail

echo "== Installing Python 3.12, pip, zip, unzip =="
sudo dnf install -y python3.12 python3.12-pip zip unzip

echo "== Installing Terraform =="
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://rpm.releases.hashicorp.com/AmazonLinux/hashicorp.repo
sudo dnf install -y terraform

echo "== Installing boto3 (for the seed script) =="
pip3.12 install --user boto3

echo ""
echo "Done. Next steps:"
echo "  1. cp terraform/terraform.tfvars.example terraform/terraform.tfvars"
echo "     and fill in your real values (bucket name, emails, API key)"
echo "  2. bash scripts/build_all.sh"
echo "  3. cd terraform && terraform init && terraform apply"
echo "  4. python3.12 scripts/seed_demo_data.py     # populate demo data"
