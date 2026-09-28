# Base Kustomization

This Kustomization should define the bare minimum K8s resources (`Deployments`, `StatefulSets`, `CronJobs`, `Services`, etc) needed to
run this application.

It should be as generic and simple as possible. Any environment specific resources can be added as needed by overlays for those environments.
