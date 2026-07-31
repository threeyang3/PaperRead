"use strict";

const assert = require("node:assert/strict");
const {
  TIME_ZONE,
  beijingClock,
  workspaceClock,
  parseLocalTime,
  shouldRunDaily,
  jobArguments,
  isInboxRequestPath
} = require("../../integrations/obsidian-paperflow-automation/scheduler-core");

assert.equal(TIME_ZONE, "Asia/Shanghai");
assert.equal(parseLocalTime("08:00"), 480);
assert.throws(() => parseLocalTime("25:00"));

const now = new Date("2026-07-17T01:00:00Z");
const clock = beijingClock(now);
assert.equal(clock.date, "2026-07-17");
assert.equal(clock.time, "09:00:00");
const tokyoClock = workspaceClock(
  new Date("2026-07-17T15:30:00Z"),
  "Asia/Tokyo"
);
assert.equal(tokyoClock.date, "2026-07-18");
assert.equal(tokyoClock.time, "00:30:00");
assert.throws(
  () => workspaceClock(now, "Mars/Olympus"),
  /Invalid Workspace timezone/
);
assert.equal(
  shouldRunDaily(
    {
      catchUpDailyAfterStartup: true,
      timezone: "UTC",
      dailyLocalTime: "08:00",
      runtime: { lastDailyDate: "2026-07-16" }
    },
    now
  ).due,
  false
);
assert.equal(
  shouldRunDaily(
    {
      catchUpDailyAfterStartup: true,
      timezone: "Asia/Tokyo",
      dailyLocalTime: "10:00",
      runtime: { lastDailyDate: "2026-07-16" }
    },
    now
  ).due,
  true
);
assert.equal(
  shouldRunDaily(
    {
      catchUpDailyAfterStartup: true,
      dailyLocalTime: "10:00",
      runtime: { lastDailyDate: "2026-07-16" }
    },
    now
  ).due,
  false
);
assert.equal(
  shouldRunDaily(
    {
      catchUpDailyAfterStartup: true,
      dailyLocalTime: "08:00",
      runtime: { lastDailyDate: "2026-07-17" }
    },
    now
  ).due,
  false
);
assert.equal(
  shouldRunDaily(
    {
      catchUpDailyAfterStartup: false,
      dailyLocalTime: "08:00",
      runtime: { lastDailyDate: "2026-07-16" }
    },
    now
  ).due,
  false
);
assert.deepEqual(jobArguments("inbox"), ["-m", "paperflow.cli", "inbox"]);
assert.deepEqual(jobArguments("daily"), ["-m", "paperflow.cli", "daily"]);
assert.equal(isInboxRequestPath("50 Inbox/Paper Requests/new-paper.md"), true);
assert.equal(isInboxRequestPath("50 Inbox\\Paper Requests\\new-paper.MD"), true);
assert.equal(isInboxRequestPath("50 Inbox/Processed Requests/old.md"), false);
assert.equal(isInboxRequestPath("50 Inbox/Paper Requests/not-markdown.json"), false);

console.log("PaperFlow Automation scheduler tests passed");
