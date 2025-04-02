# Development w/ Kubernetes

## Shell

Always enter the development shell before doing anything else. This will make
sure everyone is using the same version of tools, to avoid any system discrepancies.

Install [Nix](https://github.com/LCOGT/public-wiki/wiki/Install-Nix) if you have
not already.

If you have [direnv](https://github.com/LCOGT/public-wiki/wiki/Install-direnv)
installed, the shell will automatically activate and deactive anytime you change
directories. You may have to grant permissions initially with:

```sh
direnv allow
```

Otherwise, you can manually enter the shell with:

```sh
./develop.sh
```

## Development Cluster

Spin up the development cluster with:

```sh
devenv-k8s-cluster-up
```

## Skaffold

Deploy dependent services (e.g. Postgres, Redis):

```sh
skaffold -m obs-portal-deps run
```

Start application development loop:

```sh
skaffold -m obs-portal dev
```

This will build & deploy all components, wait for them to ready and then tail their logs.

It will also watch all source-code files and automatically re-deploy/restart all necessary components when they change.

The API server should be running at https://api-obs-portal.local.lco.earth

You can access the Django Admin interface (https://api-obs-portal.local.lco.earth/admin) with the default superuser `admin:admin`.

Customize environment variables further in `./k8s/envs/local/{settings,secrets}.env`.

When you exit the development loop using `CTRL-C`, it will also cleanup all deployed resources. If you'd like to keep things
running in the background use `skaffold -m obs-portal run`.


## Teardown

To compleltely clean-up everything:

```sh
skaffold -m obs-portal,obs-portal-deps delete
```
