# Publishing a Feed

Set a stable feed ID, name, publisher attribution, separate data repository,
branch, and data licence. Then run:

```text
paperflow publish plan
paperflow publish build
paperflow publish validate
paperflow publish scan
paperflow publish diff <candidate>
```

After a successful manual publication, a data-source host may opt into
unattended publication from the Control Center. Automatic publication keeps the
same validation and privacy gates, requires the configured origin to match
exactly, suppresses no-change commits, and never republishes subscription
caches. The authorization can be revoked by turning off the automation track.

Build is local. Review the separate data repository before any explicit Git
commit or push. PaperFlow does not store PATs in Workspace configuration.
