# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Pledge: a promise about agent access, with money behind it.

Today a site can say it welcomes agents and the sentence costs nothing. We
measured 230 of them: of the 32 that refuse an agent outright, not one says so
in robots.txt, and four bar agents there and serve them anyway. The published
position and the behaviour at the door are not connected, because nothing
connects them.

This connects them. A site publishes its promise here and leaves collateral
behind it. Anyone turned away calls `claim`, the validators go and knock
themselves, and if the promise is not being kept the collateral pays the person
who was refused. The site can withdraw its collateral once the term is over,
which is what makes leaving it there a real statement rather than a slogan.

Why the validators are the right witnesses
------------------------------------------

Neither side can be trusted with the evidence here. The site would report itself
served; the claimant would report itself refused. So neither reports anything.
Every validator fetches the site itself, twice and seconds apart: once saying
nothing, once declaring an agent identity. Both legs must match across
validators or the round records nothing.

That pair is the whole test, and it is fair to the site in a way a single fetch
would not be. A site that is simply down, or that refuses everyone, refuses both
legs and breaks no promise. Only the site that opens for a silent client and
shuts for a declared one has done the specific thing it promised not to do.

The four rules money forces
---------------------------

**A payable method never raises.** Raising out of one reverts the state and
keeps the value: measured elsewhere, a refused deposit left the caller poorer
and the contract heavier. Every guard here refuses by paying the value back.

**A failed round pays nobody.** No default, no benefit of the doubt in either
direction. The claim can be made again.

**Nothing inside the block reads storage or raises.** On chain id 4221 a round
touching `self.<field>` from inside ends FINISHED_WITH_ERROR, and a throw there
reverts the whole transaction rather than the round.

**One claim, one payout, one claimant per address.** An address that has already
been paid for a domain cannot be paid again for it, or a single refusal would
drain the collateral by being reported in a loop.
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

OPEN = "OPEN"
CLOSED = "CLOSED"

MAX_DOMAIN = 100
MAX_PROMISE = 1000

MIN_TERM = 60
MAX_TERM = 365 * 24 * 60 * 60
DEFAULT_TERM = 30 * 24 * 60 * 60

# What the second fetch declares itself to be: an agent fetching one page because
# a person just asked. The promise is about this client, so this is the client
# the network knocks with.
DECLARED_AGENT = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                  "ChatGPT-User/1.0; +https://openai.com/bot")


@gl.evm.contract_interface
class _Recipient:
    """A plain address to pay. Value moves on Studionet; on testnet-asimov the
    message is formed correctly and the chain never runs it, which is why a
    contract whose point is that money moves lives where it actually does."""

    class View:
        pass

    class Write:
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_epoch() -> int:
    """Deterministic here: every validator sees the same transaction timestamp,
    so a deadline costs no agreement."""
    return int(datetime.now(timezone.utc).timestamp())


def _addr(address) -> str:
    return str(address).lower()


def _domain(value: str) -> str:
    """A bare hostname, or the empty string.

    Strict on purpose. If a full URL were accepted, a site could pledge for one
    path and be judged on another, and two people could pledge what they think
    is the same domain and get two records.
    """
    text = str(value).strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.split("/")[0].split("?")[0].strip()
    if not text or len(text) > MAX_DOMAIN or "." not in text or " " in text:
        return ""
    for character in text:
        if not (character.isalnum() or character in ".-"):
            return ""
    return text


def _term(value, fallback: int) -> int:
    """Clamped, never raising: this is reached from a payable method."""
    try:
        seconds = int(str(value).strip())
    except Exception:
        return fallback
    return max(MIN_TERM, min(MAX_TERM, seconds))


def _outcome(status: int) -> str:
    if 200 <= status < 400:
        return SERVED
    if 400 <= status < 500:
        return REFUSED
    return SERVER_ERROR


class Pledge(gl.Contract):
    # One entry per domain, and the domain is the key because the promise is
    # about the domain. A second pledge for the same domain tops up the
    # collateral rather than creating a rival promise, so a claimant never has
    # to work out which of two promises applies to them.
    pledges: TreeMap[str, str]
    domains: DynArray[str]

    # Every claim ever made, upheld or not. Append only: a claim that failed is
    # part of the record, because a promise nobody could break is worth knowing
    # about too.
    claims: DynArray[str]

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------- the promise

    @gl.public.write.payable
    def pledge(self, domain: str, promise: str, term_seconds: str) -> str:
        """Publish a promise about this domain and leave collateral behind it.

        Payable, and it never raises. A guard that raised here would revert the
        record and keep the money, which is the worst outcome available.
        """
        value = gl.message.value
        name = _domain(domain)
        text = str(promise).strip()[:MAX_PROMISE]
        owner = _addr(gl.message.sender_address.as_hex)

        if not name or len(text) < 10 or value <= 0:
            # Refused by paying it back. A refusal here is a successful
            # transaction that created nothing.
            if value > 0:
                _Recipient(gl.message.sender_address).emit_transfer(value=int(value))
            return json.dumps({"ok": False, "error":
                               "need a bare domain, a promise, and collateral behind it"})

        now = _now_epoch()
        if name in self.pledges:
            existing = json.loads(self.pledges[name])
            if existing["owner"] != owner:
                _Recipient(gl.message.sender_address).emit_transfer(value=int(value))
                return json.dumps({"ok": False, "error":
                                   "that domain was pledged by " + existing["owner"]})
            existing["collateral"] = int(existing["collateral"]) + int(value)
            existing["topped_up_at"] = _now_iso()
            self.pledges[name] = json.dumps(existing)
            return json.dumps({"ok": True, "domain": name, "topped_up": True,
                               "collateral": str(existing["collateral"])})

        record = {
            "domain": name,
            "promise": text,
            "owner": owner,
            "collateral": int(value),
            "paid_out": 0,
            "state": OPEN,
            "opened_at": _now_iso(),
            "expires_at_epoch": now + _term(term_seconds, DEFAULT_TERM),
            "claims_upheld": 0,
            "paid_addresses": [],
        }
        self.pledges[name] = json.dumps(record)
        self.domains.append(name)
        return json.dumps({"ok": True, "domain": name, "collateral": str(value),
                           "expires_at_epoch": record["expires_at_epoch"]})

    # --------------------------------------------------------------- the claim

    @gl.public.write
    def claim(self, domain: str, bounty: str) -> str:
        """Say you were turned away, and let the network go and check.

        The caller supplies no evidence, because evidence from either side would
        be worthless. All the caller does is name the domain.
        """
        name = _domain(domain)
        if name not in self.pledges:
            return json.dumps({"ok": False, "error": "nothing is pledged for that domain"})

        record = json.loads(self.pledges[name])
        claimant = _addr(gl.message.sender_address.as_hex)

        if record["state"] != OPEN:
            return json.dumps({"ok": False, "error": "that pledge is closed"})
        if _now_epoch() > int(record["expires_at_epoch"]):
            return json.dumps({"ok": False, "error": "that pledge has expired"})
        if claimant in record["paid_addresses"]:
            return json.dumps({"ok": False, "error":
                               "this address has already been paid for that domain"})
        if claimant == record["owner"]:
            return json.dumps({"ok": False, "error": "the owner cannot claim against itself"})

        collateral = int(record["collateral"])
        if collateral <= 0:
            return json.dumps({"ok": False, "error": "there is nothing left behind that promise"})

        # Everything the round needs, in locals, before the block opens.
        url = "https://www." + name + "/"

        def knock() -> str:
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

        agreed = str(gl.eq_principle.strict_eq(knock)).strip().upper()
        quiet, _, declared = agreed.partition("|")
        if quiet not in OUTCOMES or declared not in OUTCOMES:
            return json.dumps({"ok": False, "domain": name,
                               "error": "the round produced no outcome this contract recognises"})

        # The promise is broken only by the specific thing it promised not to
        # do: open for a silent client and shut for one that says what it is. A
        # site that is down, or that refuses everybody, has not done that.
        broken = quiet == SERVED and declared == REFUSED

        payout = 0
        if broken:
            payout = min(collateral, max(1, _amount(bounty, collateral)))
            record["collateral"] = collateral - payout
            record["paid_out"] = int(record["paid_out"]) + payout
            record["claims_upheld"] = int(record["claims_upheld"]) + 1
            record["paid_addresses"] = record["paid_addresses"] + [claimant]
            if record["collateral"] <= 0:
                record["state"] = CLOSED
            self.pledges[name] = json.dumps(record)
            _Recipient(gl.message.sender_address).emit_transfer(value=int(payout))

        index = len(self.claims)
        self.claims.append(json.dumps({
            "index": index, "domain": name, "claimant": claimant,
            "quiet": quiet, "declared": declared, "upheld": broken,
            "paid": str(payout), "at": _now_iso(),
        }))
        return json.dumps({"ok": True, "domain": name, "quiet": quiet, "declared": declared,
                           "upheld": broken, "paid": str(payout), "claim": index})

    @gl.public.write
    def close(self, domain: str) -> str:
        """Take back what is left, once the term is over.

        Only after expiry, and only by the owner. Collateral that could be
        withdrawn at any moment would not be collateral.
        """
        name = _domain(domain)
        if name not in self.pledges:
            return json.dumps({"ok": False, "error": "nothing is pledged for that domain"})
        record = json.loads(self.pledges[name])
        if _addr(gl.message.sender_address.as_hex) != record["owner"]:
            return json.dumps({"ok": False, "error": "only the owner can close a pledge"})
        if _now_epoch() <= int(record["expires_at_epoch"]):
            return json.dumps({"ok": False, "error": "the term is not over yet"})

        remaining = int(record["collateral"])
        record["collateral"] = 0
        record["state"] = CLOSED
        record["closed_at"] = _now_iso()
        self.pledges[name] = json.dumps(record)
        if remaining > 0:
            _Recipient(gl.message.sender_address).emit_transfer(value=int(remaining))
        return json.dumps({"ok": True, "domain": name, "returned": str(remaining)})

    # ------------------------------------------------------------------ reads

    @gl.public.view
    def promise(self, domain: str) -> str:
        name = _domain(domain)
        if name not in self.pledges:
            return json.dumps({"ok": False, "error": "nothing is pledged for that domain"})
        return self.pledges[name]

    @gl.public.view
    def board(self) -> str:
        out = []
        for name in self.domains:
            out.append(json.loads(self.pledges[name]))
        return json.dumps({"ok": True, "count": len(out), "pledges": out})

    @gl.public.view
    def claim_at(self, index: str) -> str:
        try:
            position = int(str(index).strip())
        except Exception:
            return json.dumps({"ok": False, "error": "no such claim"})
        if position < 0 or position >= len(self.claims):
            return json.dumps({"ok": False, "error": "no such claim"})
        return self.claims[position]

    @gl.public.view
    def size(self) -> str:
        upheld = 0
        for raw in self.claims:
            if json.loads(raw)["upheld"]:
                upheld += 1
        return json.dumps({
            "pledges": len(self.domains),
            "claims": len(self.claims),
            "claims_upheld": upheld,
            "note": ("a claim is settled by the validators knocking on the door themselves, "
                     "twice, silent and then declaring; neither party supplies evidence"),
        })


def _amount(value, ceiling: int) -> int:
    """A requested payout, clamped to what is actually there. Never raises."""
    try:
        wanted = int(str(value).strip())
    except Exception:
        return ceiling
    if wanted <= 0:
        return ceiling
    return min(wanted, ceiling)
