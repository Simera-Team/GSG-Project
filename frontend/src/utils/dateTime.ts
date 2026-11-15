const UNAVAILABLE = "Not available";
const TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:?\d{2})?$/i;

export function hasTimezone(value: string): boolean {
  return /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
}

function readable(date: Date, preserveClock: boolean): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true,
    ...(preserveClock ? { timeZone: "UTC" } : {}),
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(item => item.type === type)?.value;
  return `${part("month")} ${part("day")}, ${part("year")} at ${part("hour")}:${part("minute")} ${part("dayPeriod")}`;
}

export function formatTimestamp(value?: string | null): string {
  if (typeof value !== "string") return UNAVAILABLE;
  const match = TIMESTAMP.exec(value.trim());
  if (!match) return UNAVAILABLE;
  const [, year, month, day, hour, minute, second = "00", fraction = "", zone] = match;
  const [y, m, d, h, min, sec] = [year, month, day, hour, minute, second].map(Number);
  if (y < 1 || m < 1 || m > 12 || d < 1 || d > 31 || h > 23 || min > 59 || sec > 59) return UNAVAILABLE;

  // This is a calendar container, not a claim that a naive timestamp is UTC.
  // UTC setters/formatting preserve its original wall-clock components without
  // involving the browser's timezone or daylight-saving normalization.
  const calendar = new Date(0);
  calendar.setUTCFullYear(y, m - 1, d);
  calendar.setUTCHours(h, min, sec, 0);
  if (calendar.getUTCFullYear() !== y || calendar.getUTCMonth() !== m - 1 || calendar.getUTCDate() !== d) return UNAVAILABLE;
  if (!zone) return readable(calendar, true);

  let offset = zone.toUpperCase();
  if (offset !== "Z") {
    const digits = offset.slice(1).replace(":", "");
    if (Number(digits.slice(0, 2)) > 23 || Number(digits.slice(2)) > 59) return UNAVAILABLE;
    offset = `${offset[0]}${digits.slice(0, 2)}:${digits.slice(2)}`;
  }
  // Normalize subsecond precision for browser parsing; it is never displayed.
  const milliseconds = fraction.padEnd(3, "0").slice(0, 3);
  const instant = new Date(`${year}-${month}-${day}T${hour}:${minute}:${second}.${milliseconds}${offset}`);
  return Number.isNaN(instant.getTime()) ? UNAVAILABLE : readable(instant, false);
}