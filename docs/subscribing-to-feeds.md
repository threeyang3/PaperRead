# Subscribing to Feeds

Add, inspect, trust, and sync a source with `paperflow source`. Trust modes are
`metadata-only`, `metadata-and-ai`, and `disabled`. Sync validates Feed/read
versions, checksums, paths, immutable records, and provenance before copying
data.

PaperFlow Automation can synchronize all explicitly enabled sources on an
Obsidian-native interval. The Control Center exposes trust, disable, removal,
one-source sync, and all-enabled-source sync controls. Subscription caches are
local-only and are excluded from later public Feed builds.

Missing PDFs can be downloaded only from the original source URL and are
validated for PDF header, expected hash, and size. Compatible analyses may be
reused. Local User Data is never overwritten, and all publisher analyses are
retained.
