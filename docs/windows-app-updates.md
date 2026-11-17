# BARQ ONE desktop updates

The Windows installer bundles the update origin and the public Ed25519 key. BARQ checks the feed on startup and on demand. It downloads and checks the installer after the user selects **Update now**. The install runs in the existing per-user directory, skips optional setup tasks and starts BARQ again after success.

## Configure the stable channel

Use a dedicated Cloudflare R2 bucket with an HTTPS public custom domain for the installer files. Restrict its publishing credentials to that bucket. Use the domain root as the update origin, with no path or query. Allow the domain to serve `latest.json` without CDN caching.

Set the following **Actions variables** in the private BARQ repository.

- `BARQ_UPDATE_ORIGIN` holds the public HTTPS origin.
- `BARQ_UPDATE_PUBLIC_KEY` holds the base64-encoded raw 32-byte Ed25519 public key.
- `BARQ_R2_ACCOUNT_ID` and `BARQ_R2_BUCKET` select the storage account and bucket.
- `BARQ_UPDATE_NOTES` is optional release text shown in the app.

Set the following **Actions secrets**.

- `BARQ_UPDATE_PRIVATE_KEY` holds the base64-encoded raw 32-byte Ed25519 private key. Store its backup privately. Installed copies pin the matching public key.
- `BARQ_R2_ACCESS_KEY_ID` and `BARQ_R2_SECRET_ACCESS_KEY` are the bucket's R2 S3 API credentials.

Build and manually install one baseline copy with the variables set. A matching release tag such as `v2.41.2` publishes only after the Windows build and installer checks pass. The workflow uploads the versioned installer before pointing `latest.json` at it. The release signing key and R2 credentials are scoped to the publishing job.
