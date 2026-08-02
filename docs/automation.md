# Obsidian-native automation

PaperFlow Automation 1.5.1 runs three independent background tracks while
Obsidian Desktop is open. Windows Task Scheduler is not used.

## Subscription synchronization

The source-sync track runs `paperflow source sync --all` at the configured
interval. `--all` means every source whose local subscription configuration is
enabled; disabled sources are never contacted. Per-source trust can be:

- `metadata-only`;
- `metadata-and-ai`;
- `disabled`.

Every Feed, manifest path, reader/schema version, and SHA256 is validated before
immutable Raw or AI records are copied. Community revisions additionally have
their canonical `content_sha256` recomputed before cache writes. Remote code is never executed and User
Data is never modified. Subscription caches are excluded from public Feed
publishing, so a host does not silently republish another publisher's records.
Feed v2 Community capability is copied only into a read-only cache; legacy
subscriptions default to Raw/AI capabilities.

## Automatic source-host publishing

Unattended publication is off until the user authorizes it in the Control
Center. Once authorized, each scheduled run:

1. requires publishing to be enabled and the configured GitHub repository to
   exactly match the local Feed `origin`;
2. builds a deterministic Feed containing only locally produced Raw and AI
   records;
3. validates the Feed and every checksum;
4. runs the privacy scan;
5. checks the Git working tree and stops without a commit when content is
   unchanged;
6. commits and pushes only the configured branch.

Any failed gate stops the run. Git hooks stay disabled. User Data, PDFs,
rendered notes, paths, logs, databases, and subscription caches are excluded.

## Version discovery and safe upgrades

The update track reads the latest non-draft, non-prerelease GitHub Release from
the fixed repository in `updates.repository_url`. When a newer semantic version
exists, PaperFlow can automatically download:

- `paperflow-<version>-py3-none-any.whl`;
- `SHA256SUMS`.

The wheel is staged only when its SHA256 matches the published checksum. Applying
an update always requires a separate user confirmation. The apply transaction:

1. verifies the staged wheel again;
2. creates a Workspace backup;
3. extracts and imports the new runtime in isolation;
4. keeps the previous runtime as rollback material;
5. switches the managed Vault runtime;
6. finalizes formal Workspace migration and versioned Obsidian resources;
7. verifies the migration.

If runtime finalization fails, the previous runtime is restored. Resource
installers also keep their own backups. Obsidian must be restarted after a
successful apply so the newly installed plugin code is loaded.

PaperFlow never downloads an update from an arbitrary UI-provided host: the URL
must identify one normal HTTPS GitHub owner/repository. GitHub Release assets
must use GitHub HTTPS download hosts.

## Scheduling behavior

The daily workflow has first priority, followed by source synchronization,
automatic publishing, and update checks. Only one PaperFlow job runs at a time.
Missed daily work catches up after Obsidian starts; interval tracks become due
after their last recorded run. Closing Obsidian stops all three tracks.
