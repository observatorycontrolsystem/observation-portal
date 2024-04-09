# Development w/ Kubernetes

Activate development environment:

```sh
nix develop --impure
```

Create an ephmeral Kubernetes cluster for development:

```sh
ctlplt apply -f ./local-registry.yaml -f ./local-cluster.yaml
```

Deploy dependent services (e.g. Postgres, Redis):

```sh
skaffold -m deps run
```

Start application development loop:

```sh
skaffold -m app dev --port-forward
```

You can customize environment variables in `./k8s/envs/local/{settings,secrets}.env`.
