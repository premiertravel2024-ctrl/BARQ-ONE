# BARQ ONE desktop updates

The Windows installer bundles the update origin and the public Ed25519 key. BARQ checks the feed on startup and on demand. It downloads and checks the installer after the user selects **Update now**. The install runs in the existing per-user directory, skips optional setup tasks and starts BARQ again after success.

## Configure the stable channel

Create a separate public GitHub repository with an initial README commit. GitHub creates release source archives from the public repository, so keep only distribution material there. Set `BARQ_UPDATE_ORIGIN` to `https://github.com/OWNER/BARQ-ONE-Updates` and `BARQ_UPDATE_GITHUB_TOKEN` as an Actions secret in the private source repository. Use a fine-grained token with Contents read/write for only the public distribution repository. The workflow publishes the installer and signed manifest in the same, initially draft release.

A dedicated Cloudflare R2 bucket with a public HTTPS custom domain also works. Use its domain root as the update origin, with no path or query. Restrict publishing credentials to that bucket and serve `latest.json` without CDN caching.

Set the following **Actions variables** in the private BARQ repository.

- `BARQ_UPDATE_ORIGIN` holds the public GitHub repository URL or R2 HTTPS origin.
- `BARQ_UPDATE_PUBLIC_KEY` holds the base64-encoded raw 32-byte Ed25519 public key.
- `BARQ_R2_ACCOUNT_ID` and `BARQ_R2_BUCKET` select the storage account and bucket for R2 only.
- `BARQ_UPDATE_NOTES` is optional release text shown in the app.

Set the following **Actions secrets**.

- `BARQ_UPDATE_PRIVATE_KEY` holds the base64-encoded raw 32-byte Ed25519 private key. Store its backup privately. Installed copies pin the matching public key.
- `BARQ_R2_ACCESS_KEY_ID` and `BARQ_R2_SECRET_ACCESS_KEY` are the bucket's S3 API credentials for R2 only.

Build and manually install one baseline copy with the variables set. A matching release tag such as `v2.41.2` publishes only after the Windows build and installer checks pass. The workflow uploads the versioned installer before pointing `latest.json` at it. The release signing key and R2 credentials are scoped to the publishing job.
