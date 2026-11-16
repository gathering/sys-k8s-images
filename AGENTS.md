# AGENTS.md

For coding agents and other tools that change this repo.

- Read `README.md` first. It says how an image is added, how its version is set, and that a push to `main` publishes.
- Every page, comment and check message follows `docs/conventions.md` in [sys-k8s-apps](https://github.com/gathering/sys-k8s-apps/blob/main/docs/conventions.md).
- Do not edit `images/*/version` unless asked to set a version by hand. Run `make bump`.
- A pushed tag is never overwritten. A change to an image needs a new version.
- Run `make check` and `make lint` before you finish, and `make test IMAGE=<name>` for each image you changed. All must pass.
- Do not commit or push unless asked.
