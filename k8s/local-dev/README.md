# local-dev Overaly

This overlay is used for local development (i.e. on a K8s cluster running locally on your machine)


# Ingress

If you're using the cluster setup by `devenv-k8s-cluster-up`, you can expose web Services on domain names like `https://something-something.local.lco.earth`
and it will be accessible from your browser (with valid TLS certs!). `something-something` can be anything and it will still resolve locally to your machine.

This is done via a DNS wildcard record that resolves `*.local.lco.earth` to `127.0.0.1` and by periodically getting LetsEncrypt to dole out a valid TLS cert for that.
That cert is then published to https://github.com/LCOGT/local-lco-earth-cert, which the nginx-ingress controller running on the local K8s cluster picks up. This means
`*.local.lco.earth` is not be trusted and is susceptible to MIMT attacks, but that's a fair bargain to be able to test TLS specific things for development purposes.

If you're using another way of setting up a local K8s cluster, you can use the cert in https://github.com/LCOGT/local-lco-earth-cert to setup something similar.

You can use the following KPT package to fetch the boilerplate, https://github.com/LCOGT/kpt-pkg-catalog/tree/main/ingress-local-lco-earth
