# Development w/ Kubernetes

Install Nix if you haven't already using [this guide](https://github.com/LCOGT/public-wiki/wiki/Install-Nix).

Activate development environment:

```sh
nix develop --impure
```

This will install all necessary tools used below.

Create an ephmeral Kubernetes cluster for development:

```sh
ctlptl apply -f ./local-registry.yaml -f ./local-cluster.yaml
```

Deploy dependent services (e.g. Postgres, Redis):

```sh
skaffold -m deps run
```

Start application development loop:

```sh
skaffold -m app dev --port-forward
```

This will build & deploy all components, wait for them to ready and then tail their logs.

The API server should be exposed at http://localhost:8080/ (the port may be different, check the output).

It will also watch all source-code files and automatically re-deploy/restart all necessary components when they change.

You can access the Django Admin interface (http://localhost:8080/admin) with the default superuser `admin:admin`.

Customize environment variables further in `./k8s/envs/local/{settings,secrets}.env`.

When you exit the development loop using `CTRL-C`, it will also cleanup all deployed resources. If you'd like to keep things
running in the background use `skaffold -m app run` instead of `skaffold -m app dev`.

Use `skaffold -m <module> delete` to bring down artifacts of a previous `run`.

## Teardown

To compleltely clean-up everything, just delete the local cluster:

```sh
ctlptl delete -f ./local-cluster.yaml
```

You should leave the `./local-registry.yaml` running because it might be used by other projects.
It also caches container images, allowing you to skip expensive container builds next time you work on this project.
