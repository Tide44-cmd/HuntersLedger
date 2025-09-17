from io import BytesIO
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Europe/London"
DEFAULT_DURATION_HOURS = 2

TZ_ABBREV_MAP = {
    "GMT": "Europe/London",
    "BST": "Europe/London",
    "UTC": "UTC",
    "CET": "Europe/Berlin",
    "CEST": "Europe/Berlin",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
}

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"]

# --- Utility functions ---

def _parse_date(date_str: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

def _parse_time(time_str: str) -> tuple[int, int] | None:
    ts = time_str.strip().lower().replace(".", "")
    m = re.fullmatch(r"^([0-2]?\d)([0-5]\d)$", ts)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"^([0-2]?\d):([0-5]?\d)$", ts)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"^([0-1]?\d)(?::([0-5]?\d))?\s*(am|pm)$", ts)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        if hh == 12: hh = 0
        if m.group(3) == "pm": hh += 12
        return hh, mm
    return None

def _resolve_tz(tz_input: str | None) -> ZoneInfo:
    if tz_input:
        tz_input = tz_input.strip()
        tz_name = TZ_ABBREV_MAP.get(tz_input.upper(), tz_input)
    else:
        tz_name = DEFAULT_TZ
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)

def _build_ics(title: str, start: datetime, end: datetime, location: str, description: str) -> bytes:
    uid = f"{uuid4()}@havenshelper"
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dtstart = start.strftime("%Y%m%dT%H%M%SZ")
    dtend = end.strftime("%Y%m%dT%H%M%SZ")
    description = description.replace("\n", "\\n")
    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Hunter's Ledger//Hunt Session//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{title}
LOCATION:{location}
DESCRIPTION:{description}
BEGIN:VALARM
TRIGGER:-PT15M
ACTION:DISPLAY
DESCRIPTION:Game session starts in 15 minutes
END:VALARM
END:VEVENT
END:VCALENDAR""".encode("utf-8")

def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]+", "", name).strip().replace(" ", "_")[:60] or "session"

# --- Slash command ---

@bot.tree.command(name="huntingsession", description="Create a calendar invite for a game session.")
@app_commands.describe(
    game="Name of the game (will be the calendar title)",
    date="Date of the session (e.g. 2025-09-17 or 17/09/2025)",
    time="Time (e.g. 1700, 17:00, 5pm)",
    timezone="Optional: timezone like Europe/London, GMT, PST etc.",
    notes="Optional notes to include in the calendar"
)
async def huntingsession(
    interaction: discord.Interaction,
    game: str,
    date: str,
    time: str,
    timezone: str | None = None,
    notes: str | None = None
):
    await interaction.response.defer(ephemeral=True)

    d = _parse_date(date)
    if not d:
        return await interaction.followup.send("❌ Invalid date format. Try `2025-09-17`, `17/09/2025`, or `17 Sep 2025`.", ephemeral=True)

    t = _parse_time(time)
    if not t:
        return await interaction.followup.send("❌ Invalid time format. Try `1700`, `17:00`, or `5pm`.", ephemeral=True)

    hour, minute = t
    tzinfo = _resolve_tz(timezone)
    tz_label = tzinfo.key
    local_start = datetime(d.year, d.month, d.day, hour, minute, tzinfo)
    local_end = local_start + timedelta(hours=DEFAULT_DURATION_HOURS)

    start_utc = local_start.astimezone(timezone.utc)
    end_utc = local_end.astimezone(timezone.utc)

    description = notes.strip() if notes else "This calendar invite was created by Hunter's Ledger for your upcoming hunt."
    location = "Discord - Hunter's Haven"

    ics_data = _build_ics(game, start_utc, end_utc, location, description)
    filename = f"{_safe_filename(game)}_{local_start.strftime('%Y-%m-%d_%H%M')}_{tz_label.replace('/', '-')}.ics"

    await interaction.followup.send(
        content=(
            f"✅ **{game}** session created for **{local_start.strftime('%a %d %b %Y • %H:%M')}** ({tz_label})\n"
            f"• Duration: {DEFAULT_DURATION_HOURS}h\n• Reminder: 15 mins before\n"
            f"📅 Add it to your calendar below:"
        ),
        file=discord.File(fp=BytesIO(ics_data), filename=filename),
        ephemeral=True
    )
