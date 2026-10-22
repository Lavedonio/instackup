# Releasing

Releases are published to PyPI automatically when a GitHub release is published. The package version comes from the release's git tag, so nothing needs to be bumped by hand.

# Index
- [One-time setup](#one-time-setup)
- [Publishing a release](#publishing-a-release)
- [Dry run on TestPyPI](#dry-run-on-testpypi)
- [Building locally](#building-locally)

# One-time setup

The workflow uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/): PyPI trusts this repository's GitHub Actions workflow through OpenID Connect, so no API token is stored anywhere.

1. **PyPI publisher.** Sign in to https://pypi.org, open *Your projects → instackup → Manage → Publishing* and add a GitHub publisher:
   - Owner: `Lavedonio`
   - Repository: `instackup`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
2. **GitHub environment.** In the repository, open *Settings → Environments*, create an environment named `pypi` and, optionally, add yourself as a required reviewer so every upload waits for your approval. Restricting it to tags matching `v*` is also a good idea.
3. **TestPyPI (optional).** Repeat both steps on https://test.pypi.org with the environment name `testpypi`.
4. **Remove old tokens.** If a PyPI API token for this project was created before, revoke it.

# Publishing a release

1. Make sure `main` is green and the version log in `version_logs/` is up to date.
2. Create a release on GitHub (*Releases → Draft a new release*) with a **new tag named `v<version>`**, e.g. `v0.4.0` (pre-releases like `v0.4.0rc1` work too), targeting `main`.
3. Publish it. The *Release* workflow then:
   1. runs the full CI suite;
   2. builds the sdist and wheel, and fails if the tag doesn't match the built version;
   3. uploads them to PyPI (waiting for approval if the `pypi` environment requires it), with digital attestations;
   4. attaches them to the GitHub release.

If the workflow fails before uploading, fix the problem, delete the release and its tag, and publish again. PyPI never accepts the same version twice, so if the upload already happened, release a new patch version instead.

# Dry run on TestPyPI

Run the *Release* workflow manually (*Actions → Release → Run workflow*). It runs CI, builds a development version (e.g. `0.4.1.dev3`) and uploads it to TestPyPI. Install it with:

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --pre instackup
```

# Building locally

```bash
uv build
```

The version is computed from the latest git tag and the number of commits since then. Distributions land in `dist/`.
