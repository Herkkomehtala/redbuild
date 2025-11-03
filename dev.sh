#!/bin/bash
#
# dev.sh - A script to automate the setup and launch of the development environment.

# Exit immediately if any command exits with a non-zero status.
set -e

echo "INFO: Checking Minikube status..."

if ! minikube status > /dev/null 2>&1; then
  echo "INFO: Minikube is not running. Starting cluster with the Docker driver..."
  minikube start --driver=docker --memory=8g --cpus=4
else
  echo "INFO: Minikube is already running."
fi

echo "INFO: Ensuring Minikube addons are enabled (ingress, metrics-server)..."
minikube addons enable ingress
minikube addons enable metrics-server

echo "INFO: Waiting for Ingress controller to be ready..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=60s
echo "INFO: Ingress controller is ready."

echo "INFO: Pointing Docker client to Minikube's Docker daemon..."

# The 'eval' command executes the output of 'minikube docker-env', which sets
# environment variables (like DOCKER_HOST) for this script's shell session.
# This is crucial for Skaffold to build images directly into the cluster.
eval $(minikube -p minikube docker-env)
echo "INFO: Docker environment set for this session."

echo "INFO: Starting Skaffold development workflow..."

skaffold dev
