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

Deploy application dependencies:

```sh
skaffold -m obs-portal-deps run
```

Start application development loop:

```sh
skaffold -m obs-portal dev
```

If there are any Ingresses, they should be exposed at:
  - https://obs-portal.local.lco.earth
  - https://dependency-obs-portal.local.lco.earth

## Github Settings

Octopilot creates lots of temporary branches to create PRs. It's a good idea to delete branches on merge:

```sh
gh repo edit --delete-branch-on-merge
```

### Secrets

Workflows expect the following secrets:

  - `GH_TOKEN_OCTOPILOT`
    - Fine-grained personal access token
    - Limited to this repo
    - Contents: write
    - PR: write

Github user that's used to generate these tokens also **needs** to be added
to this repo with the `Write` role.
