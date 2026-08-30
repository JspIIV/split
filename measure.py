"""What does the web serve a person, and what does it serve that person's agent?

One page per site, fetched several times from the same machine within seconds of
each other, with exactly one thing changed: who the client says it is. Everything
else is held still, because everything else is what would otherwise explain the
difference.

Nothing is bypassed. No login, no CAPTCHA, no proxy rotation, no pretending to be
a browser we are not. When a site refuses a client, the refusal is the finding.

    python measure.py                 # every site in sites.txt
    python measure.py --limit 10      # a quick pass while working on it

Writes results/<date>.json and prints a summary.
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITES = os.path.join(HERE, "sites.txt")
RESULTS = os.path.join(HERE, "results")

# The identities. The first is the control: what a person's browser sends.
#
# The rest are what agents actually send. They are split deliberately: a crawler
# collecting training data and an agent fetching one page because a person just
# asked for it are different things, and a site may reasonably treat them
# differently. ChatGPT-User is the one that matters most for this measurement,
# because there is a person waiting on the other end of it.
IDENTITIES = {
    "browser": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"),
    "chatgpt_user": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                     "ChatGPT-User/1.0; +https://openai.com/bot"),
    "claude_user": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                    "Claude-User/1.0; +https://anthropic.com/claude-user"),
    "perplexity_user": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                        "Perplexity-User/1.0; +https://perplexity.ai/perplexity-user"),
    "gptbot": "Mozilla/5.0 AppleWebKit/537.36 (compatible; GPTBot/1.1; +https://openai.com/gptbot)",
    "script": "python-requests/2.32.3",
}

CONTROL = "browser"

# robots.txt names worth reporting. A site barring these is not hiding it, which
# makes it the honest end of the same behaviour and worth recording as such.
ROBOT_NAMES = ["GPTBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "anthropic-ai",
               "PerplexityBot", "Perplexity-User", "CCBot", "Google-Extended",
               "Applebot-Extended", "Bytespider", "meta-externalagent"]

TIMEOUT = 25


def fetch(url, agent):
    """status, bytes, final url. A transport failure is status 0, not an
    exception: a site that hangs up on one identity and not another is exactly
    what we are here to record."""
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", os.devnull, "-L", "--max-time", str(TIMEOUT),
             "-w", "%{http_code} %{size_download} %{url_effective}",
             "-A", agent,
             "-H", "Accept: text/html,application/xhtml+xml",
             "-H", "Accept-Language: en-US,en;q=0.9",
             url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT + 10)
        parts = out.stdout.strip().split(" ", 2)
        return {"status": int(parts[0]), "bytes": int(parts[1]),
                "final": parts[2] if len(parts) > 2 else url}
    except Exception:
        return {"status": 0, "bytes": 0, "final": url}


def robots(host):
    """Which named agent clients the site bars from everything.

    Only a bare `Disallow: /` counts. A site that merely keeps agents out of its
    cart or its search pages is doing ordinary crawler hygiene, and counting that
    as exclusion would inflate the number.
    """
    try:
        out = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "20", "-A", IDENTITIES[CONTROL],
             "https://www.%s/robots.txt" % host],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        text = out.stdout
    except Exception:
        return {"error": "unreachable", "blocked": []}

    if not text or len(text) > 400_000:
        return {"error": "empty" if not text else "oversized", "blocked": []}

    blocked, current = [], []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            current = []
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            current.append(value.lower())
        elif key == "disallow" and value == "/":
            for name in ROBOT_NAMES:
                if name.lower() in current and name not in blocked:
                    blocked.append(name)
    return {"error": None, "blocked": blocked}


DIFFERENCE = 0.15  # a page has to differ by this much before it is worth a second look


def confirm(url, record, candidates):
    """Measure the size differences a second time and keep only what repeats.

    Page sizes move on their own: A/B tests, rotating banners, a carousel with a
    different number of items. The first pass over 72 sites flagged nine
    differences and three of them vanished on a re-measure, so a single
    observation is not evidence. This runs the same comparison again and drops
    anything that does not hold, which is why the published count is lower than
    the raw one.
    """
    if not candidates:
        return [], {}
    control = fetch(url, IDENTITIES[CONTROL])
    if not (200 <= control["status"] < 400) or not control["bytes"]:
        return [], {}

    held, second = [], {CONTROL: control["bytes"]}
    for name in candidates:
        again = fetch(url, IDENTITIES[name])
        second[name] = again["bytes"]
        if not (200 <= again["status"] < 400):
            continue
        if abs(again["bytes"] - control["bytes"]) / control["bytes"] > DIFFERENCE:
            held.append(name)
    return held, second


def measure(entry):
    host, category = entry
    url = "https://www.%s/" % host
    record = {"host": host, "category": category, "url": url, "identities": {}}
    for name, agent in IDENTITIES.items():
        record["identities"][name] = fetch(url, agent)
    record["robots"] = robots(host)
    record.update(verdict(record))

    # Refusals are a status code and repeat by their nature. Size differences do
    # not, so they have to survive a second measurement before they are reported.
    if record.get("differs"):
        proposed = record["differs"]
        held, second = confirm(url, record, proposed)
        record["differs"] = held
        record["difference_recheck"] = {"proposed": proposed, "held": held, "bytes": second}
        if not held and record["verdict"] == "serves_agents_differently":
            record["verdict"] = "same_for_both"
    print("  %-22s %s" % (host, " ".join(
        "%s=%s" % (n, record["identities"][n]["status"]) for n in IDENTITIES)))
    return record


def verdict(record):
    """What this site did, in one word, derived rather than asserted.

    `not_comparable` is the important one and it is why the headline number is
    smaller than it could be. Our control is curl wearing a browser user agent,
    not a browser: it runs no JavaScript and presents no browser TLS
    fingerprint. A site that refuses it is refusing non browser clients
    generally, which is a different claim from refusing agents. Those sites are
    dropped from the denominator instead of being counted as discrimination.
    """
    control = record["identities"][CONTROL]
    served = 200 <= control["status"] < 400
    if not served:
        return {"verdict": "not_comparable", "control_status": control["status"]}

    refused, differs = [], []
    for name, result in record["identities"].items():
        if name == CONTROL or name == "script":
            continue
        if not (200 <= result["status"] < 400):
            refused.append(name)
        elif control["bytes"] and abs(result["bytes"] - control["bytes"]) / control["bytes"] > DIFFERENCE:
            differs.append(name)

    if refused:
        outcome = "refuses_agents"
    elif differs:
        outcome = "serves_agents_differently"
    else:
        outcome = "same_for_both"
    return {"verdict": outcome, "control_status": control["status"],
            "refused": refused, "differs": differs}


def load(limit=None):
    entries = []
    for line in open(SITES, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        host, _, category = line.partition(",")
        entries.append((host.strip(), (category or "other").strip()))
    return entries[:limit] if limit else entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    entries = load(args.limit)
    started = datetime.datetime.now(datetime.timezone.utc)
    print("measuring %d sites, %d identities each\n" % (len(entries), len(IDENTITIES)))

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(measure, entries))
    records.sort(key=lambda r: r["host"])

    comparable = [r for r in records if r["verdict"] != "not_comparable"]
    refusing = [r for r in comparable if r["verdict"] == "refuses_agents"]
    differing = [r for r in comparable if r["verdict"] == "serves_agents_differently"]
    barring = [r for r in records if r["robots"]["blocked"]]

    payload = {
        "measured_at": started.isoformat(),
        "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "method": ("One homepage per site, fetched once per identity from the same machine "
                   "within seconds, changing only the client identity. Nothing bypassed, "
                   "nothing logged in. Sites that refuse the browser control are marked "
                   "not_comparable and left out of the denominator, because refusing every "
                   "non browser client is a different thing from refusing agents."),
        "identities": IDENTITIES,
        "totals": {
            "sites": len(records),
            "comparable": len(comparable),
            "refuses_agents": len(refusing),
            "serves_agents_differently": len(differing),
            "robots_bars_named_agents": len(barring),
        },
        "sites": records,
    }

    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, started.strftime("%Y-%m-%d") + ".json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print("\n%d sites, %d comparable" % (len(records), len(comparable)))
    if comparable:
        share = 100.0 * len(refusing) / len(comparable)
        print("%d of them refuse at least one agent identity (%.0f%%)" % (len(refusing), share))
    print("%d serve agents a materially different page" % len(differing))
    print("%d bar named agent clients in robots.txt" % len(barring))
    print("\nwrote %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
