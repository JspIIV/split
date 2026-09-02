# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Pledge: a promise about agent access, with money behind it.

A site can say it welcomes agents and the sentence costs nothing. We measured
230 of them for a sibling project: of the 32 that refuse an agent outright, not
one says so in robots.txt, and four bar agents there and serve them anyway. What
a site publishes and what it does at the door are not connected, because nothing
connects them.

Here the site publishes its promise, proves the domain is its own, and leaves
collateral behind it. Anyone turned away claims, the validators go and knock
themselves, and if the promise is not kept the collateral pays the person who
was refused.

Three things a steward found, and what they cost
------------------------------------------------

The first version of this contract let **anybody pledge anybody's domain.** Our
own demo pledged nike.com, which we do not own. That is not a small hole: a
board of promises where the promise may not be the site's own is a board of
rumours, and the collateral would have been ours to lose on somebody else's
behalf.

So a pledge now requires proof of control. The owner publishes its address at
`https://<domain>/.well-known/split-pledge.txt` and calls `verify`, where every
validator fetches that file itself and they must agree on the text. Only the
address the domain vouches for can pledge it. Proof expires, because domains
change hands.

The second: **the claimant chose the payout.** A claim named its own bounty, so
one refusal could ask for the whole collateral. The payout is now fixed by the
pledge when it is opened, and a claim cannot ask for anything.

The third, and the one that made the first two worse: **rotating addresses.**
One address could be paid once per domain, so a single refusal reported from
twenty addresses emptied the collateral twenty times over. Payouts are now
capped inside an observation window, by count and by value. Past the cap the
claim is recorded as upheld and pays nothing, because the finding is still true
even when the budget for it is spent.

Why the validators are the right witnesses
------------------------------------------

Neither side can be trusted with the evidence. The site would report itself
serving; the claimant would report being refused. So neither reports anything.
Every validator fetches the site itself, twice and seconds apart, once saying
nothing and once declaring an agent identity. Both legs must agree across
validators or the round records nothing.

That pair is fair to the site in a way a single fetch would not be. A site that
is down, or that refuses everyone, refuses both legs and breaks no promise. Only
opening for a silent client and shutting for a declared one is the thing it
promised not to do.

The rules money forces
----------------------

**A payable method never raises.** Raising reverts the state and keeps the
value. Every guard here refuses by paying the value back.

**A failed round pays nobody**, in either direction.

**Nothing inside the block reads storage or raises.** On chain id 4221 a round
touching `self.<field>` from inside ends FINISHED_WITH_ERROR, and a throw there
reverts the whole transaction rather than the round.
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
MAX_TERM = 90 * 24 * 60 * 60
DEFAULT_TERM = 30 * 24 * 60 * 60

# How long a proof of control stands before it has to be shown again. Domains
# change hands, and a permanent proof would let yesterday's owner keep speaking
# for a site it no longer runs.
PROOF_TTL = 30 * 24 * 60 * 60

# The observation window, and what a domain can lose inside one. Both caps
# exist because addresses are free: without them one refusal reported from
# twenty addresses drains the collateral twenty times over.
DEFAULT_WINDOW = 24 * 60 * 60
MIN_WINDOW = 60
MAX_WINDOW = 30 * 24 * 60 * 60
MAX_CLAIMS_PER_WINDOW = 3

# Where the domain vouches for an address.
PROOF_PATH = "/.well-known/split-pledge.txt"

# The identities a promise can be made about. A pledge names which of these it
# covers, and a claim has to be made under one of the named ones. Free prose was
# not enough: the first version let a site publish any sentence it liked while
# every claim settled the same fixed condition underneath, so the published
# promise and the thing being enforced had nothing to do with each other.
IDENTITIES = {
    "chatgpt_user": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                     "ChatGPT-User/1.0; +https://openai.com/bot"),
    "claude_user": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                    "Claude-User/1.0; +https://anthropic.com/claude-user"),
    "perplexity_user": ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; "
                        "Perplexity-User/1.0; +https://perplexity.ai/perplexity-user"),
    "gptbot": ("Mozilla/5.0 AppleWebKit/537.36 (compatible; GPTBot/1.1; "
               "+https://openai.com/gptbot)"),
}

# What a promise can promise. Both are checked by the validators in the round,
# and which one is checked comes from the pledge rather than from the contract.
#
#   SAME_DOOR  the declared client is let in wherever the silent one is
#   SAME_PAGE  the same, and it is handed a page of comparable size
#
# SAME_PAGE is the stronger promise: a site that answers an agent with a stub is
# keeping SAME_DOOR and breaking SAME_PAGE, and that is a distinction a site
# should be able to make about itself rather than have made for it.
SAME_DOOR = "SAME_DOOR"
SAME_PAGE = "SAME_PAGE"
CONDITIONS = [SAME_DOOR, SAME_PAGE]

# How much smaller a declared client's page may be before SAME_PAGE is broken.
# Coarse on purpose: validators fetch from different places and a tight
# threshold would split the jury over a rotating banner rather than over policy.
PAGE_TOLERANCE = 40


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
    return int(datetime.now(timezone.utc).timestamp())


def _addr(address) -> str:
    return str(address).lower()


def _domain(value: str) -> str:
    """A bare hostname, or the empty string."""
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


def _clamp(value, low: int, high: int, fallback: int) -> int:
    """Never raises: reached from a payable method, where raising strands money."""
    try:
        number = int(str(value).strip())
    except Exception:
        return fallback
    return max(low, min(high, number))


def _identities(value: str):
    """The identities a pledge covers, in the contract's own vocabulary.

    Unknown names are dropped rather than stored, so a pledge cannot promise
    something about a client the contract has no way to knock as.
    """
    named = []
    for part in str(value).replace(";", ",").split(","):
        name = part.strip().lower()
        if name in IDENTITIES and name not in named:
            named.append(name)
    return named


def _condition(value: str) -> str:
    name = str(value).strip().upper()
    return name if name in CONDITIONS else ""


def _outcome(status: int) -> str:
    if 200 <= status < 400:
        return SERVED
    if 400 <= status < 500:
        return REFUSED
    return SERVER_ERROR


class Pledge(gl.Contract):
    # Who a domain has vouched for, and when it last said so.
    controllers: TreeMap[str, str]

    # One entry per domain. A second pledge for the same domain tops up the
    # collateral rather than creating a rival promise, so a claimant never has
    # to work out which of two promises applies to them.
    pledges: TreeMap[str, str]
    domains: DynArray[str]

    # Every claim ever made, upheld or not, paid or capped. Append only: a claim
    # that failed is part of the record, and so is one that was true and arrived
    # after the budget for the window was spent.
    claims: DynArray[str]

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------ proof

    @gl.public.write
    def verify(self, domain: str) -> str:
        """Prove the caller controls this domain.

        The caller publishes its own address, on its own site, at a path nobody
        else can write to, and the validators read it themselves. Nothing here
        is taken on trust: not the caller's claim, and not ours.
        """
        name = _domain(domain)
        if not name:
            return json.dumps({"ok": False, "error": "give a bare domain, like example.com"})

        claimant = _addr(gl.message.sender_address.as_hex)
        url = "https://" + name + PROOF_PATH   # into a local before the block opens

        def look() -> str:
            try:
                response = gl.nondet.web.get(url)
                if int(response.status) >= 400:
                    return "HTTP_" + str(int(response.status))
                return response.body.decode("utf-8", "replace").strip().lower()[:200]
            except Exception:
                return ""

        published = str(gl.eq_principle.strict_eq(look)).strip().lower()
        if not published:
            return json.dumps({"ok": False, "domain": name,
                               "error": "nothing the validators agreed on at " + PROOF_PATH})
        if published != claimant:
            # Exact match, not a substring: a file that merely mentions an
            # address somewhere in a paragraph is not a domain vouching for it.
            return json.dumps({"ok": False, "domain": name,
                               "error": "that file does not name the calling address",
                               "found": published[:60]})

        self.controllers[name] = json.dumps({
            "domain": name, "controller": claimant,
            "proved_at": _now_iso(), "proved_epoch": _now_epoch(),
        })
        return json.dumps({"ok": True, "domain": name, "controller": claimant,
                           "good_for_seconds": PROOF_TTL})

    def _controller(self, name: str) -> typing.Optional[str]:
        """The address this domain vouches for, if the proof is still fresh."""
        if name not in self.controllers:
            return None
        record = json.loads(self.controllers[name])
        if _now_epoch() - int(record["proved_epoch"]) > PROOF_TTL:
            return None
        return str(record["controller"])

    # ------------------------------------------------------------- the promise

    @gl.public.write.payable
    def pledge(self, domain: str, promise: str, identities: str, condition: str,
               payout: str, window_seconds: str, term_seconds: str) -> str:
        """Publish a promise about a domain you have proved you control.

        The payout per upheld claim is fixed here, by the party putting up the
        money, and a claimant can never name its own figure.
        """
        value = gl.message.value
        name = _domain(domain)
        text = str(promise).strip()[:MAX_PROMISE]
        owner = _addr(gl.message.sender_address.as_hex)

        def refuse(why: str) -> str:
            if value > 0:
                _Recipient(gl.message.sender_address).emit_transfer(value=int(value))
            return json.dumps({"ok": False, "error": why})

        covered = _identities(identities)
        rule = _condition(condition)

        if not name or len(text) < 10 or value <= 0:
            return refuse("need a bare domain, a promise, and collateral behind it")
        if not covered:
            return refuse("name at least one identity this promise covers, from: "
                          + ", ".join(sorted(IDENTITIES)))
        if not rule:
            return refuse("say what is promised, either " + " or ".join(CONDITIONS))

        controller = self._controller(name)
        if controller is None:
            return refuse("prove control of that domain first: publish your address at "
                          + PROOF_PATH + " and call verify")
        if controller != owner:
            return refuse("that domain vouches for " + controller)

        each = _clamp(payout, 1, int(value), max(1, int(value) // 10))
        window = _clamp(window_seconds, MIN_WINDOW, MAX_WINDOW, DEFAULT_WINDOW)

        if name in self.pledges:
            existing = json.loads(self.pledges[name])
            if existing["owner"] != owner:
                return refuse("that domain was pledged by " + existing["owner"])
            existing["collateral"] = int(existing["collateral"]) + int(value)
            existing["topped_up_at"] = _now_iso()
            self.pledges[name] = json.dumps(existing)
            return json.dumps({"ok": True, "domain": name, "topped_up": True,
                               "collateral": str(existing["collateral"])})

        record = {
            "domain": name,
            # The prose is for a person to read. The two fields under it are what
            # the round actually checks, and a claim is settled against them
            # rather than against a sentence nobody can enforce.
            "promise": text,
            "covers": covered,
            "condition": rule,
            "owner": owner,
            "collateral": int(value),
            # The terms, fixed and machine readable rather than left in prose.
            "payout_each": each,
            "window_seconds": window,
            "max_claims_per_window": MAX_CLAIMS_PER_WINDOW,
            "max_value_per_window": each * MAX_CLAIMS_PER_WINDOW,
            "paid_out": 0,
            "state": OPEN,
            "opened_at": _now_iso(),
            "expires_at_epoch": _now_epoch() + _clamp(term_seconds, MIN_TERM, MAX_TERM,
                                                      DEFAULT_TERM),
            "claims_upheld": 0,
            "paid_addresses": [],
        }
        self.pledges[name] = json.dumps(record)
        self.domains.append(name)
        return json.dumps({"ok": True, "domain": name, "collateral": str(value),
                           "covers": covered, "condition": rule,
                           "payout_each": str(each), "window_seconds": window,
                           "max_claims_per_window": MAX_CLAIMS_PER_WINDOW,
                           "expires_at_epoch": record["expires_at_epoch"]})

    # --------------------------------------------------------------- the claim

    def _spent_in_window(self, name: str, window: int):
        """What this domain has already paid inside the current window."""
        since = _now_epoch() - window
        count = value = 0
        for raw in self.claims:
            claim = json.loads(raw)
            if claim["domain"] != name or not claim.get("upheld"):
                continue
            if int(claim.get("at_epoch", 0)) < since:
                continue
            paid = int(claim.get("paid", 0))
            if paid > 0:
                count += 1
                value += paid
        return count, value

    @gl.public.write
    def claim(self, domain: str, identity: str) -> str:
        """Say you were turned away, and let the network go and check.

        The caller supplies no evidence and no figure. It names the domain and
        the identity it was refused under, and that identity has to be one the
        pledge actually covers.
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

        wanted = str(identity).strip().lower()
        covered = record.get("covers") or []
        if wanted not in IDENTITIES:
            return json.dumps({"ok": False, "error": "unknown identity: " + str(wanted)[:40]})
        if wanted not in covered:
            return json.dumps({"ok": False, "domain": name,
                               "error": "that promise does not cover " + wanted,
                               "covers": covered})

        # The domain as pledged, with no www bolted on. The promise is about
        # this name, and knocking somewhere else would test a host the site
        # never made a promise about: measured, jspiiv.github.io answered while
        # www.jspiiv.github.io did not exist at all.
        url = "https://" + name + "/"

        # Copied into locals before the block opens, because the terms live in
        # storage and nothing inside the block may read it.
        agent_ua = IDENTITIES[wanted]
        rule = str(record.get("condition") or SAME_DOOR)

        def knock() -> str:
            """Two knocks, and the verdict the pledged condition asks for.

            The sizes never leave this block. Validators fetch from different
            places, so an exact byte count would split the jury over a rotating
            banner. What crosses to consensus is the coarse reading each of them
            arrived at under the same rule.
            """
            try:
                first = gl.nondet.web.get(url)
                quiet = _outcome(int(first.status))
                quiet_size = len(first.body)
            except Exception:
                quiet, quiet_size = UNREACHABLE, 0
            try:
                second = gl.nondet.web.get(url, headers={
                    "User-Agent": agent_ua,
                    "Accept": "text/html,application/xhtml+xml",
                })
                declared = _outcome(int(second.status))
                declared_size = len(second.body)
            except Exception:
                declared, declared_size = UNREACHABLE, 0

            broken = "NO"
            if quiet == SERVED and declared == REFUSED:
                broken = "YES"
            elif rule == SAME_PAGE and quiet == SERVED and declared == SERVED and quiet_size:
                shrunk = (quiet_size - declared_size) * 100 // quiet_size
                if shrunk > PAGE_TOLERANCE:
                    broken = "YES"
            return quiet + "|" + declared + "|" + broken

        agreed = str(gl.eq_principle.strict_eq(knock)).strip().upper()
        parts = agreed.split("|")
        if len(parts) != 3 or parts[0] not in OUTCOMES or parts[1] not in OUTCOMES:
            return json.dumps({"ok": False, "domain": name,
                               "error": "the round produced no outcome this contract recognises"})
        if parts[2] not in ("YES", "NO"):
            return json.dumps({"ok": False, "domain": name,
                               "error": "the round produced no verdict this contract recognises"})

        quiet, declared, verdict = parts[0], parts[1], parts[2]
        broken = verdict == "YES"

        payout = 0
        capped = None
        if broken:
            window = int(record["window_seconds"])
            count, spent = self._spent_in_window(name, window)
            each = int(record["payout_each"])
            collateral = int(record["collateral"])

            if count >= int(record["max_claims_per_window"]):
                capped = "the claim cap for this window is already spent"
            elif spent + each > int(record["max_value_per_window"]):
                capped = "the value cap for this window is already spent"
            elif collateral <= 0:
                capped = "there is nothing left behind that promise"
            else:
                payout = min(each, collateral)
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
            "identity": wanted, "condition": rule,
            "quiet": quiet, "declared": declared, "upheld": broken,
            # A capped claim is still recorded as upheld. The finding is true
            # whether or not there is budget left to pay for it, and dropping it
            # would quietly shrink the record of what the site did.
            "paid": payout, "capped": capped,
            "at": _now_iso(), "at_epoch": _now_epoch(),
        }))
        return json.dumps({"ok": True, "domain": name, "identity": wanted,
                           "condition": rule, "quiet": quiet, "declared": declared,
                           "upheld": broken, "paid": str(payout), "capped": capped,
                           "claim": index})

    @gl.public.write
    def close(self, domain: str) -> str:
        """Take back what is left, once the term is over."""
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
    def controller(self, domain: str) -> str:
        name = _domain(domain)
        who = self._controller(name)
        if who is None:
            return json.dumps({"ok": False, "domain": name,
                               "error": "no fresh proof of control for that domain"})
        return json.dumps({"ok": True, "domain": name, "controller": who})

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
        upheld = paid = capped = 0
        for raw in self.claims:
            claim = json.loads(raw)
            upheld += bool(claim["upheld"])
            paid += int(claim.get("paid", 0)) > 0
            capped += bool(claim.get("capped"))
        return json.dumps({
            "pledges": len(self.domains),
            "claims": len(self.claims),
            "claims_upheld": upheld,
            "claims_paid": paid,
            "claims_capped": capped,
            "note": ("a claim is settled by the validators knocking on the door themselves, "
                     "twice, silent and then declaring; neither party supplies evidence, and "
                     "the payout is fixed by the pledge rather than chosen by the claimant"),
        })
