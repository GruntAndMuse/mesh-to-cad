# Sigstore Release Signing — Reusable Pattern

Pioneered on `mesh-to-cad` v1.0.2 (2026-10-04). Copy this pattern to
`med-tracker`, `document-ocr`, and every future GruntAndMuse release.

## What it does

Every tagged release gets a `.sigstore` bundle per asset, signed at build
time by CI via [Sigstore](https://www.sigstore.dev/) using GitHub OIDC.
No long-lived keys, no secrets to manage, nothing to rotate. The signature
attests: *these exact bytes were built by this repo's workflow on this tag.*

Checksums (SHA-256) prove the file wasn't corrupted. Signatures prove **who
built it**. Ship both; verify signature first, checksum second.

## Workflow snippet

In the release job (the one that only runs on version tags):

```yaml
    permissions:
      contents: write
      id-token: write  # REQUIRED — Sigstore needs the OIDC token

    steps:
      # ... build artifacts, generate checksums.txt ...

      - name: Sign release assets with Sigstore
        uses: sigstore/gh-action-sigstore-python@v3.4.0
        with:
          inputs: >-
            ./artifacts/checksums.txt
            ./artifacts/<asset-1>
            ./artifacts/<asset-2>

      - name: Stage signature bundles
        # The action emits <asset>.sigstore.json next to each input; we
        # publish them as <asset>.sigstore. Fail loudly if any is missing.
        shell: bash
        run: |
          for f in ./artifacts/checksums.txt \
                   ./artifacts/<asset-1> \
                   ./artifacts/<asset-2>; do
            if [ -f "$f.sigstore.json" ]; then
              mv "$f.sigstore.json" "$f.sigstore"
              echo "staged: $f.sigstore"
            else
              echo "MISSING signature bundle for $f" && exit 1
            fi
          done

      # ... create release with files: ./artifacts/**/* ...
```

The action writes `<file>.sigstore` next to each input. The release upload
glob picks them up automatically.

## OIDC identity format

```
https://github.com/<OWNER>/<REPO>/.github/workflows/<WORKFLOW_FILE>@<REF>
```

Concrete example (mesh-to-cad v1.0.2):

```
https://github.com/GruntAndMuse/mesh-to-cad/.github/workflows/build.yml@refs/tags/v1.0.2
```

Components:
- `OWNER/REPO` — the GitHub org and repo
- `.github/workflows/<file>` — the workflow that ran the signing step
- `@refs/tags/vX.Y.Z` — the tag ref the release job ran on. **Always the
  full tag ref**, because the release job's `if:` gates on tags.

Issuer (always): `https://token.actions.githubusercontent.com`

## Verify commands

```bash
pip install sigstore   # once

sigstore verify identity \
  --bundle <asset>.sigstore \
  --cert-identity "https://github.com/<OWNER>/<REPO>/.github/workflows/<WORKFLOW_FILE>@refs/tags/vX.Y.Z" \
  --cert-oidc-issuer "https://token.actions.githubusercontent.com" \
  <asset>
```

`OK` = genuine. Anything else = do not trust the file.

## What to change per project

| Item | Change to |
|---|---|
| `OWNER/REPO` | The project's GitHub org/repo |
| Workflow filename | Whatever the release workflow is called |
| `inputs:` list | The project's actual asset paths |
| Confirm-bundles `ls` | Same asset paths + `.sigstore` |
| `--cert-identity` | The project's identity string (tag substituted per release) |
| SECURITY.md | Copy the "Release signatures" section, swap identity |
| This doc | Not needed per project — it lives here as the reference |

## Gotchas (earned 2026-10-04)

- The release job **must** have `id-token: write` — without it the signing
  action can't get the OIDC token and fails.
- Sign **after** all assets exist (including `checksums.txt`) and **before**
  the release is created, so bundles upload as release assets.
- Sign `checksums.txt` too — it authenticates the integrity list itself.
- The confirm-bundles step is load-bearing: it turns "signing silently did
  nothing" from a silent doc lie into a loud CI failure.
- The action emits `<asset>.sigstore.json` next to each input (v3.4.0
  behavior — verify, don't assume, if you upgrade). We rename to
  `<asset>.sigstore` for the published extension.
- Pin the action version (`@v3.4.0`, not `@v3`) for reproducible builds.
