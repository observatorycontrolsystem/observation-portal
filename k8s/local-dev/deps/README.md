# Local Development Dependencies

This Kustomization should define any dependencies needed by your application.

For example, things like the Namespace, databases, etc. should go in here.

## Rationale

Main reason for seperating this out into its own Kustomization is that `skaffold dev` deletes any resources it deploys when the development loop is killed.
This is fine (and good) for the application itself, but things which carry state or are slow to clean-up/deploy (i.e. Namespaces) should keep running so that
the next time `skaffold dev` is run we're not stuck waiting for things to stablize.
