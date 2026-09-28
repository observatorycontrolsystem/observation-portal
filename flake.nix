{
  description = "Astronomical observing management backend";

  inputs = {
    devenv-k8s.url = "github:LCOGT/devenv-k8s/v1";

    nixpkgs.follows = "devenv-k8s/nixpkgs";
    flake-parts.follows = "devenv-k8s/flake-parts";

    devenv-root = {
      url = "file+file:///dev/null";
      flake = false;
    };

  };

  nixConfig = {
    extra-substituters = [
      "https://devenv.cachix.org"
      "https://lco-public.cachix.org"
    ];

    extra-trusted-public-keys = [
      "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw="
      "lco-public.cachix.org-1:zSmLK7CkAehZ7QzTLZKt+5Y26Lr0w885GUB4GlT1SCg="
    ];
  };

  outputs = inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.devenv-k8s.flakeModules.default
      ];

      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];

      perSystem = { config, self', inputs', pkgs, system, ... }: {
        # Per-system attributes can be defined here. The self' and inputs'
        # module parameters provide easy access to attributes of the same
        # system.

        config.packages = {

          # This provides a wrapped skaffold w/ any additional scripts
          skaffold = pkgs.writeShellApplication {
            name = "skaffold";

            runtimeInputs = [
              inputs'.devenv-k8s.packages.skaffold
              config.packages.skaffold-builder-buildx
            ];

            text = ''
             ${inputs'.devenv-k8s.packages.skaffold}/bin/skaffold "$@"
            '';
          };
          skaffold-builder-buildx = pkgs.writeShellApplication {
            name = "skaffold-builder-buildx";
            text = ''
              args=()

              if [[ -n "''${SKAFFOLD_BUILDX_ARGS-}" ]]; then
                IFS=" " read -r -a args <<< "$SKAFFOLD_BUILDX_ARGS"
              fi

              if test "$PUSH_IMAGE" = true; then
                args+=("--push")
              else
                args+=("--load")
              fi

              if test -n "$PLATFORMS"; then
                args+=("--platform $PLATFORMS")
              fi

              if docker buildx > /dev/null 2>&1; then
                buildx_cmd="docker buildx"
              elif buildx > /dev/null 2>&1; then
                buildx_cmd="buildx"
              else
                echo "buildx not found"
                exit 1
              fi

              set -ex
              $buildx_cmd build "$BUILD_CONTEXT" --tag "$IMAGE" "''${args[@]}" "$@"
            '';
          };
        };

        # https://devenv.sh/basics/
        # Enter using `nix develop --impure`
        config.devenv.shells.default = {

          # use direnv without --impure
          devenv.root = let
            devenvRootFileContent = builtins.readFile inputs.devenv-root.outPath;
          in pkgs.lib.mkIf (devenvRootFileContent != "") devenvRootFileContent;

          # setup local development cluster
          devenv-k8s.local-cluster.enable = true;

          # offload caching to docker/buildx
          env.SKAFFOLD_CACHE_ARTIFACTS = "false";

          languages.python = {
            enable = true;
            package = pkgs.python310;

            poetry = {
              enable = true;
              activate.enable = false;
              install.enable = false;
            };
          };

          # https://devenv.sh/packages/
          packages = [
            pkgs.gfortran.cc.lib

          ];

          # https://devenv.sh/reference/options/#entershell
          enterShell = ''
            touch "$DEVENV_ROOT/k8s/local-dev/secrets.env"
          '';

        };
      };

      flake = {
        # The usual flake attributes can be defined here, including system-
        # agnostic ones like nixosModule and system-enumerating ones, although
        # those are more easily expressed in perSystem.

      };
    };
}

