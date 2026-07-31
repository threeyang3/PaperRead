"use strict";

const DEFAULT_TIME_ZONE = "Asia/Shanghai";

function workspaceClock(now = new Date(), timeZone = DEFAULT_TIME_ZONE) {
  let parts;
  try {
    parts = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23"
    }).formatToParts(now);
  } catch (error) {
    throw new Error(`Invalid Workspace timezone: ${timeZone}`, { cause: error });
  }
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    date: `${values.year}-${values.month}-${values.day}`,
    time: `${values.hour}:${values.minute}:${values.second}`,
    minutes: Number(values.hour) * 60 + Number(values.minute)
  };
}

function beijingClock(now = new Date()) {
  return workspaceClock(now, DEFAULT_TIME_ZONE);
}

function parseLocalTime(value) {
  const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(String(value || ""));
  if (!match) {
    throw new Error(`无效的每日时间：${value}`);
  }
  return Number(match[1]) * 60 + Number(match[2]);
}

function shouldRunDaily(settings, now = new Date()) {
  const clock = workspaceClock(now, settings.timezone || DEFAULT_TIME_ZONE);
  return {
    due:
      Boolean(settings.catchUpDailyAfterStartup) &&
      clock.minutes >= parseLocalTime(settings.dailyLocalTime) &&
      settings.runtime.lastDailyDate !== clock.date,
    clock
  };
}

function jobArguments(kind) {
  if (kind === "inbox") {
    return ["-m", "paperflow.cli", "inbox"];
  }
  if (kind === "daily") {
    return ["-m", "paperflow.cli", "daily"];
  }
  throw new Error(`未知 PaperFlow 作业：${kind}`);
}

function isInboxRequestPath(value) {
  const normalized = String(value || "").replaceAll("\\", "/");
  return (
    normalized.startsWith("50 Inbox/Paper Requests/") &&
    normalized.toLowerCase().endsWith(".md")
  );
}

module.exports = {
  DEFAULT_TIME_ZONE,
  TIME_ZONE: DEFAULT_TIME_ZONE,
  workspaceClock,
  beijingClock,
  parseLocalTime,
  shouldRunDaily,
  jobArguments,
  isInboxRequestPath
};
