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

Published Feed repositories include a generated `.gitattributes` and normalize
all checksummed text to LF. This is part of the checksum contract: a Feed must
still validate after a Windows clone with `core.autocrlf=true`.

The official application and data source use separate repositories:

- `PaperRead` contains MIT-licensed application code and releases.
- `ArXiv-data` contains the CC BY 4.0 public Feed only.

Subscribe with:

```powershell
paperflow source add https://github.com/threeyang3/ArXiv-data.git --name arxiv-data
paperflow source inspect arxiv-data
paperflow source sync arxiv-data --dry-run
paperflow source sync arxiv-data
```

The `ArXiv-data` round-trip acceptance test published 29 Raw records and 29 AI
records, cloned the public GitHub repository with `core.autocrlf=true`, and
validated every checksum. The first remote sync created 58 subscription-cache
records, downloaded only the three newly missing PDFs, and rendered 29 notes.
A repeated sync created no records and reused all 58. Both runs reported zero
conflicts, zero User-data writes, and zero remote-code execution.
