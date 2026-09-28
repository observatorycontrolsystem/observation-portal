# ingress

## Description

This package provides a bare-bones [`networking.k8s.io/v1.Ingress`](https://kubernetes.io/docs/concepts/services-networking/ingress/)
that you can build upon and use in other packages.

## Usage

Clone this package:

```shell
kpt pkg get https://github.com/LCOGT/kpt-pkg-catalog/ingress ing-myname
```

Customize `ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: example
...
```

And then render to update resources:

```shell
kpt fn render
```

This package is also a Kustomization, so it can also be referenced by other
Kustomizations:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ./ing-myname/
```
