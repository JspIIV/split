# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Attest: let the network find out for itself whether a site serves an agent.

The measurement in this repository has one weakness, and it is the kind that
cannot be fixed by measuring more carefully: **you have to take our word for
it.** We say nike.com refuses an agent. A site could answer that we made it up,
or that we did it wrong, and nothing in the dataset settles that argument.

This contract removes us from the middle. `check(host)` opens a consensus round
in which every validator fetches the site itself, from its own machine, and the
round completes only if their results agree. What lands on chain is not our
claim about the site. It is what the site did to a set of independent clients
that have no stake in the answer.

Why the validators are the right clients
----------------------------------------

A GenLayer validator fetching a page is exactly the thing being measured: a
machine acting on behalf of somebody else. It is not pretending to be a browser
and not pretending to be anything at all. So the question this contract asks is
the honest form of the question the whole project asks: **when a machine asks
for your public homepage, do you answer it?**

What goes to consensus
----------------------

One value, and a coarse one: SERVED, REFUSED, SERVER_ERROR or UNREACHABLE.

Not the body, not the byte count, not the headers. Validators run in different
places on different networks, so anything finer than this would disagree for
reasons that have nothing to do with the site's policy, and a round that cannot
agree records nothing at all. The coarse value is the part that is about the
site rather than about the weather.

`strict_eq` rather than a prompt rule: there is no judgement here, no model, and
nothing to word differently. Every validator either got the same answer from the
site or did not, and if they did not, that disagreement is the finding and the
round should fail rather than paper over it.

Three rules this contract obeys, each learned the hard way
----------------------------------------------------------

**Nothing inside the block reads storage.** On chain id 4221 a round that
touches `self.<field>` from inside the nondeterministic block ends
FINISHED_WITH_ERROR every time, while Studio allows it happily. The host is
copied into a local before the block opens.

**Nothing inside the block raises.** A throw there cannot be caught outside it:
it reverts the whole transaction, so a site that hangs up would become a site
that can never be checked. An unreachable site comes back as data.

**A failed round records nothing.** There is no default outcome and no
half-result. If the validators cannot agree, the host stays unchecked and can be
checked again, because a disagreement written down as a fact would be worse than
no record.
"""

from genlayer import *
from datetime import datetime, timezone
import json
import typing


SERVED = "SERVED"
REFUSED = "REFUSED"
SERVER_ERROR = "SERVER_ERROR"
UNREACHABLE = "UNREACHABLE"

OUTCOMES = [SERVED, REFUSED, SERVER_ERROR, UNREACHABLE]

MAX_HOST = 100

# What the second fetch says it is. A real agent identity, sent honestly: this
# is the string an agent uses when it is fetching one page because a person just
# asked for it, and the point of the measurement is what happens to a client
# that declares that rather than hiding it.
DECLARED_AGENT = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                  "ChatGPT-User/1.0; +https://openai.com/bot")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _addr(address) -> str:
    return str(address).lower()


def _clean_host(host: str) -> str:
    """A bare hostname, or the empty string.

    Deliberately strict. Accepting a full URL would let two callers check what
    they think is the same site and get two different records, and accepting a
    path would turn this into a page checker, which is a different measurement
    with a different meaning.
    """
    text = str(host).strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.split("/")[0].split("?")[0].strip()
    if not text or len(text) > MAX_HOST or "." not in text or " " in text:
        return ""
    for character in text:
        if not (character.isalnum() or character in ".-"):
            return ""
    return text


def _outcome(status: int) -> str:
    if 200 <= status < 400:
        return SERVED
    if 400 <= status < 500:
        return REFUSED
    return SERVER_ERROR


class Attest(gl.Contract):
    # Every attestation ever made, in order. Append only: an attestation is a
    # statement about a moment, and a site changing its mind next week is the
    # interesting part rather than a correction to be applied backwards.
    #
    # No per host index. A TreeMap raises KeyError on a key that does not exist
    # yet, and in a sibling contract that single line discarded a round the
    # validators had already agreed on. Scanning is slower and cannot fail that
    # way.
    attestations: DynArray[str]

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------ write

    @gl.public.write
    def check(self, host: str) -> str:
        """Ask the network what a site does when a machine knocks.

        One round, one value. The caller does not supply the answer and cannot
        influence it: the only thing that crosses into the block is the hostname.
        """
        name = _clean_host(host)
        if not name:
            return json.dumps({"ok": False, "error": "give a bare hostname, like nike.com"})

        url = "https://www." + name + "/"

        def look() -> str:
            # Locals only. Nothing here may touch self, and nothing here may
            # raise: both end the transaction rather than the round.
            #
            # Two fetches, seconds apart, from the same validator. The first
            # says nothing about itself. The second says what it is. That pair
            # is the whole measurement: the difference between them cannot be
            # explained by location, timing or luck, because both legs share all
            # of it.
            try:
                quiet = _outcome(int(gl.nondet.web.get(url).status))
            except Exception:
                quiet = UNREACHABLE
            try:
                declared = _outcome(int(gl.nondet.web.get(url, headers={
                    "User-Agent": DECLARED_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                }).status))
            except Exception:
                declared = UNREACHABLE
            return quiet + "|" + declared

        agreed = str(gl.eq_principle.strict_eq(look)).strip().upper()
        quiet, _, declared = agreed.partition("|")
        if quiet not in OUTCOMES or declared not in OUTCOMES:
            # Nothing is written. The round produced something this contract
            # does not understand, and inventing a reading of it would put a
            # number on chain that no validator actually asserted.
            return json.dumps({
                "ok": False,
                "host": name,
                "error": "the round produced no outcome this contract recognises",
                "returned": agreed[:120],
            })

        index = len(self.attestations)
        record = {
            "index": index,
            "host": name,
            "url": url,
            "quiet": quiet,
            "declared": declared,
            # The finding, derived rather than asserted: the same validator, the
            # same site, seconds apart, let in while silent and turned away once
            # it said what it was.
            "punishes_disclosure": quiet == SERVED and declared == REFUSED,
            "attested_at": _now_iso(),
            "asked_by": _addr(gl.message.sender_address.as_hex),
            "note": ("every validator fetched this twice itself, once silent and once "
                     "declaring an agent identity, and they agreed on both; this is what the "
                     "site did, not what anybody reported"),
        }
        self.attestations.append(json.dumps(record))
        return json.dumps({"ok": True, "index": index, "host": name,
                           "quiet": quiet, "declared": declared,
                           "punishes_disclosure": record["punishes_disclosure"]})

    # ------------------------------------------------------------------ reads

    @gl.public.view
    def attestation(self, index: str) -> str:
        position = self._as_index(index)
        if position is None:
            return json.dumps({"ok": False, "error": "no such attestation"})
        return self.attestations[position]

    @gl.public.view
    def history(self, host: str) -> str:
        """Everything the network has ever said about one site, oldest first.

        This is the read that matters over time. One attestation says what a
        site did once. A run of them says whether it changed its mind, and when.
        """
        name = _clean_host(host)
        found = []
        for raw in self.attestations:
            record = json.loads(raw)
            if record["host"] == name:
                found.append(record)
        return json.dumps({"ok": True, "host": name, "count": len(found), "attestations": found})

    @gl.public.view
    def page(self, start: str, count: str) -> str:
        try:
            first = max(0, int(str(start).strip()))
        except Exception:
            first = 0
        try:
            size = max(1, min(50, int(str(count).strip())))
        except Exception:
            size = 20
        out = []
        for position in range(first, min(first + size, len(self.attestations))):
            out.append(json.loads(self.attestations[position]))
        return json.dumps({"ok": True, "total": len(self.attestations),
                           "start": first, "attestations": out})

    @gl.public.view
    def size(self) -> str:
        counts = {outcome: 0 for outcome in OUTCOMES}
        hosts = []
        punishing = 0
        for raw in self.attestations:
            record = json.loads(raw)
            counts[record["declared"]] = counts.get(record["declared"], 0) + 1
            if record.get("punishes_disclosure"):
                punishing += 1
            if record["host"] not in hosts:
                hosts.append(record["host"])
        return json.dumps({
            "attestations": len(self.attestations),
            "hosts": len(hosts),
            "outcomes_when_declaring": counts,
            "served_until_it_said_what_it_was": punishing,
            "note": ("each of these was fetched by every validator independently and required "
                     "their agreement, so none of them is anybody's report"),
        })

    # ----------------------------------------------------------------- helper

    def _as_index(self, value: str) -> typing.Optional[int]:
        try:
            index = int(str(value).strip().strip('"').strip("'").strip())
        except Exception:
            return None
        if index < 0 or index >= len(self.attestations):
            return None
        return index
