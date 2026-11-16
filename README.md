# sys-k8s-images

Upstream images with a small change of ours, for apps in [sys-k8s-workloads](https://github.com/gathering/sys-k8s-workloads) and [sys-k8s-apps](https://github.com/gathering/sys-k8s-apps). For developers who add or change an image.

## How it fits together

```
images/<name>/ ──push to main──▶ ghcr.io/gathering/sys-k8s-images/<name>:<version> ──▶ Kargo
      ▲
   Renovate
```

- **A push to `main` publishes.** CI builds, tests and pushes every image whose version is not in the registry yet. Kargo then promotes the new tag.
- **Renovate keeps base images up to date.** A new digest goes to `main` by itself once the build passes. A new upstream version gets a pull request, because our change may no longer apply.

Each image is a directory in `images/`:

| File | What it is |
| --- | --- |
| `Dockerfile` | Upstream's image, pinned as `<tag>@sha256:<digest>`, with our change. |
| `version` | The tag to push. CI sets it ([Versions](#versions)). |
| `test.sh` | Run as `test.sh <image>` on every build. Fails when our change is missing. |
| `image.yaml` | Optional. `version_scheme: free` when the version does not come from the `FROM` tag. |

## 1. Add an image

1. Write `images/<name>/Dockerfile`. Get the digest with `docker buildx imagetools inspect <image>:<tag>`. Make the build fail when the change no longer applies, as `images/shlink-web-client` does.
2. Write `images/<name>/test.sh` and make it executable. Test what the change is for.
3. Build and check:

   ```bash
   make bump                  # writes images/<name>/version
   make test IMAGE=<name>     # builds and runs test.sh
   make check lint            # versions and linters
   ```

4. Push. The run on `main` shows the pushed tag in its summary.
5. Make the new package public in GitHub, once, so the clusters can pull it.

## 2. Use the image in an app

Add the repository to the app's `Pipeline` in the workloads repo ([promote-images.md](https://github.com/gathering/sys-k8s-workloads/blob/main/docs/promote-images.md)):

```yaml
spec:
  images:
    - repo: ghcr.io/gathering/sys-k8s-images/shlink-web-client
```

No `strategy` is needed. The new tag shows in the app's Kargo project, `<team>-<app>-kargo`.

## Versions

A version is `<upstream>-gathering.<n>`, such as `4.9.0-gathering.1`. `<upstream>` is the `FROM` tag. Kargo reads it as SemVer: `4.9.0-gathering.10` is newer than `4.9.0-gathering.9`, and `4.9.1-gathering.1` is newer than both.

**A pushed tag is never overwritten.**

When an image's directory changes after its `version` was last set, CI sets a new one and commits it:

- A new `FROM` tag gives `<upstream>-gathering.1`.
- Any other change raises `<n>` by one.

`make bump` does the same locally.

To set a version by hand, edit `version` in the same commit as the change, or after it. CI keeps it. `make check` fails unless it matches the `FROM` tag and is the highest the file has had. CI also fails when the tag is already pushed from other content.

With `version_scheme: free`, the version is always set by hand. It must still be SemVer and the highest so far.

To run an older version, promote its tag in the Kargo UI. A lower version or an older `FROM` tag here fails `make check`.

The tags are SemVer pre-releases. Kargo picks them because the `Pipeline` sets no version constraint. A constraint such as `^4` would hide them.

## Setup

Once per repository:

- **Renovate** must be enabled for the repository.
- **`main`** must take direct pushes from GitHub Actions, for version bumps, and from Renovate, for new digests. Do not add a ruleset that requires a PR or checks.

## When something goes wrong

| What you see | Fix |
| --- | --- |
| `the image changed after ... was set` | Run `make bump`. With `version_scheme: free`, raise the version. |
| `... is not <upstream>-gathering.<n>, from the last FROM` | The version does not match the `FROM` tag. Fix it. |
| `... is lower than ..., the highest so far` | Raise the version. |
| `FROM tag ... is older than ...` | Keep the newer `FROM`. To run an older version, promote its tag in the Kargo UI. |
| `... is already in the registry` | `main` published that tag after the branch left it. Merge `main` into the branch and run `make bump`. |
| `the tag is pushed from other content` | On `main`, a version that was already pushed for other content. Raise the version. |
| `cannot tell whether ... exists` | The registry did not answer clearly. Nothing was pushed. Re-run the job. |
| The build fails on a new upstream version | Our change no longer applies. Fix it in the Renovate PR. |
| Kargo does not see a new tag | Make the package public. |
