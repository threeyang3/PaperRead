# PaperFlow Control Center

PaperFlow Automation 1.5.1 adds an Obsidian-native Control Center. It opens
automatically after the Obsidian workspace is ready; this behavior can be
disabled in the plugin settings. You can also open it from the left ribbon,
the command palette, or the plugin settings page. It wraps common PaperFlow
commands so routine use does not require a terminal.

The first screen is an extensible task workspace, not a fixed three-step
workflow or a required sequence:

- add or collect a paper from an arXiv ID, DOI, PDF, or paper page;
- discover candidates from saved topics;
- browse the paper library and daily intake;
- continue the reading and reproduction queues;
- analyze an already imported paper by Paper UID;
- configure an execution Agent profile, provider, model, reasoning effort,
  timeout, fallback, and reuse policy;
- process Inbox requests or generate the daily brief.

None is presented as the required successor of another, and the shelf can grow
as PaperFlow adds user-facing capabilities. Feed subscriptions, publishing,
migration, and maintenance are collapsed under **Advanced tools**.

Five additional parallel entrances cover Reading, Annotations, Reviews,
Community, and Publish Contributions. The reading workspace arranges the PDF,
private Annotation index, private Review, and read-only Community Note. These
entrances do not imply that Agent settings follow collection or analysis.

Above the task shelf, the automation orchestrator presents three independent
tracks: enabled-source synchronization, confirmation-authorized source-host
publishing, and release discovery/verified staging. Each track shows its
interval and most recent run. Applying a staged update still requires a
dedicated confirmation.

## Available operations

- **Research task shelf:** collect or discover papers, browse the library,
  continue reading or reproduction, and inspect daily intake.
- **Quick run:** process Inbox, run the daily workflow, extract caption-backed
  figures for existing papers, inspect import requests, and check runtime
  status.
- **Collect a paper:** add an arXiv ID, DOI, PDF URL, or web URL with priority
  and optional immediate AI analysis.
- **Analyze a paper:** reanalyze an imported Paper UID using the saved Agent
  configuration or an explicitly selected provider.
- **Agent settings:** choose the profile, Codex/Claude/ChatGPT Web/Mock provider, model,
  Codex reasoning effort, timeout, fallback, Feed-analysis reuse, and
  reanalysis policy. Saving is one atomic backend operation and never reads or
  stores AI credentials.
- **Data health:** inspect mojibake, missing visual embeds, broken assets,
  pending reanalysis, sync conflicts, and relationship rebuild needs without
  automatically overwriting user content.
- **GitHub Feed subscriptions:** add a GitHub HTTPS repository, inspect its
  checksummed structure, set trust, enable/disable/remove sources, and
  synchronize one or all enabled sources.
- **Publish and Git:** plan/build/validate/privacy-scan a local Feed,
  initialize its independent Git repository, inspect status, commit, and push
  after a dedicated confirmation dialog.
- **Maintenance:** create a Workspace backup, inspect and verify migrations,
  validate paths, preview render-all, rebuild the relationship graph, and
  display resolved configuration.
- **Updates:** configure one fixed GitHub Releases repository, check or
  SHA256-stage a release, and confirmation-apply the program, Workspace, and
  versioned plugin update transaction.

## Command safety

The plugin has no terminal input and cannot run an arbitrary command. Every
button maps to a fixed `paperflow` argument list and starts Python with
`shell: false`. Dynamic values are bounded and validated:

- AI provider/profile/policy values use allowlists;
- GitHub repositories must use
  `https://github.com/<owner>/<repository>[.git]`;
- source names contain only letters, numbers, dots, underscores, and hyphens;
- commit messages and model names reject control characters and length abuse;
- only one PaperFlow operation runs at a time.

Subscription clones disable Git hooks and never execute remote code. Local
Feed repositories also disable hooks. `.git` is excluded from Feed checksums,
privacy scans, diffs, and snapshots.

Agent tool access is deliberately not arbitrary. Codex always runs in a
read-only sandbox against staged metadata and selected paper text. Claude is
started with an empty tool set. Neither Agent can write to the Vault or execute
scripts from papers, LaTeX sources, repositories, or installers.

`push` is the only remote write in the Control Center. It requires a separate
confirmation, then repeats Feed schema validation and privacy scanning before
calling Git. PaperFlow does not create a GitHub repository. Scheduled Feed
publication runs only after the user explicitly enables that automation track
and still repeats the same safety gates.

## Publishing prerequisites

The public Feed remains a repository separate from the PaperFlow program and
from the Vault. Before `Build Feed` succeeds, configure:

- `publishing.feed_id`;
- `publishing.name`;
- publisher attribution;
- an independently chosen data licence.

The current `ArXiv-data` Feed uses `CC-BY-4.0`; the separate PaperRead
application source uses the MIT software licence.

PDFs remain link-only. User sidecars, notes, paths, logs, SQLite, credentials,
and local Git metadata are never part of the Feed.

The Control Center runs only while Obsidian Desktop is open. Daily work missed
while closed catches up after the next launch.
