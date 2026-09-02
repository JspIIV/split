# Split

**A standing record of what the web serves people, and what it serves the agents
acting for them.**

Send an agent to buy something for you and it does not reach the store you see.
On a large share of the sites people actually use, the same request that opens
for a browser is refused when the client says it is an agent fetching a page for
the person who asked.

That is not an accusation, it is a measurement, and this repository is the
measurement plus every dataset it has produced.

* `measure.py` runs it. `python measure.py`
* `sites.txt` is the list, one host per line
* `results/` holds every run, dated, never edited afterwards
* `docs/` is the page that reads the newest dataset

## What it does

One homepage per site, fetched once per identity from the same machine within
seconds of itself. Exactly one thing changes between fetches: **who the client
says it is.** A browser, an agent fetching for a person who just asked
(`ChatGPT-User`, `Claude-User`, `Perplexity-User`), a crawler (`GPTBot`), and a
plain script.

Everything else is held still, because everything else is what would otherwise
explain the difference. Same machine, same seconds, same headers, same location,
same page.

It also reads `robots.txt` and records which named agent clients a site bars from
the whole site. Only a bare `Disallow: /` counts. Keeping agents out of a cart or
a search page is ordinary crawler hygiene and counting it would inflate the
number.

**Nothing is bypassed.** No login, no CAPTCHA solving, no proxy rotation, and no
pretending to be a browser we are not. When a site refuses a client, the refusal
is the finding.

## The one number, and why it is smaller than it could be

The control is not a real browser. It is a command line client sending a browser
user agent string: no JavaScript, no browser TLS fingerprint. Roughly half the
sites we test refuse it too, and refusing every non browser client is a different
thing from refusing agents.

So those sites are marked `not_comparable` and **dropped from the denominator**
rather than counted as discrimination. The headline share is out of the sites
that served the control, which is the smaller, defensible number. Anyone wanting
a bigger one can compute it from the same dataset; we would rather publish the
one we can defend.

## What it does not show

**This measures the front door, not the price.** Whether an agent is let in and
whether it is handed the same page. It says nothing about what an agent is
charged, and no number here should be read that way. Measuring price needs a
different design, with currency, geography, session and A/B testing controlled
for, and until that exists the claim will not be made.

One location, one moment, homepages only.

## Why keep the record somewhere neutral

Two parties can see this today and neither has a reason to write it down. The
sites are the ones doing it. The agent vendors sell a product that looks worse
for it. A measurement that only exists on the blog of one of them is a
measurement nobody has to accept.

So the runs are dated, never edited, and the method ships with them. The
intended end state is that each run's summary is anchored where neither side
can revise it, and the raw dataset stays here for anyone who wants to
recompute the number themselves and get a different one honestly.

## Reproducing

```
python measure.py            # every site
python measure.py --limit 10 # a quick pass
```

Results land in `results/<date>.json` with the full per identity detail, the
method text, and the identities used. To point the page at the newest run, copy
it to `docs/data.json`.

Numbers move. A site that refuses an agent today may serve it next month, and
that change is the interesting part, which is why old runs are kept rather than
overwritten.

## Taking us out of the middle

The measurement above has one weakness that measuring more carefully cannot fix:
**you have to take our word for it.** We say nike.com refuses an agent. Nike can
answer that we made it up, or ran it wrong, and nothing in the dataset settles
that.

`contracts/attest.py` removes us. `check(host)` opens a GenLayer consensus round
in which every validator fetches the site itself, from its own machine, twice
and seconds apart: once saying nothing about itself, once declaring an agent
identity. The round completes only if the validators agree on both legs.

Live on GenLayer Studionet at `0x23F124bda497e32AcB84Be5F3a309A8943501F1d`.

| host | silent | declared |
|---|---|---|
| nike.com | SERVED | **REFUSED** |
| airbnb.com | SERVED | **REFUSED** |
| walmart.com | SERVED | SERVED |

Walmart is the control, measured the same way in the same round. The tool is not
an accusation machine; where there is no difference it records none.

**The finding this produced.** The blocking is not aimed at machines. It is aimed
at machines that say what they are. Of the 16 sites that refuse a named agent
identity, 5 served an unnamed script client in the same second, and the
validators, whose HTTP client declares nothing, were served by nike.com and
airbnb.com until the moment they declared.

That is worth stating plainly, because the whole industry is currently building
standards for agents to identify themselves honestly: **right now, honesty is
the thing being punished.**

**Two rules the round obeys.** Nothing inside the nondeterministic block reads
storage, which ends the transaction on this network, and nothing inside it
raises, which reverts it. A site that hangs up comes back as data. And a round
the validators cannot agree on records nothing at all: the host stays unchecked
rather than being written down as a disagreement.

## Where you measure from changes the answer

The same 72 sites, the same method, the same day, run once from a home
connection and once from a datacentre: **18 of them disagreed.** Amazon served
an agent from one vantage and refused it from the other. Several sites that
refuse a home connection outright are comparable from a datacentre, and several
that are comparable from home refuse the datacentre before the question of
identity ever arises.

This is why runs carry a `vantage` and are never averaged together. A single
number covering both would be true of neither, and the difference is not noise
to be smoothed away: it is a second axis of the same behaviour, address
reputation stacked on top of declared identity.

It is also the strongest argument for `contracts/attest.py`. A validator set is
many independent vantages at once, on machines nobody here controls. When they
agree, the finding no longer depends on where we happened to be sitting.

## The notice nobody gives

robots.txt is the channel a site already has for telling machines no. Public,
machine readable, free to read before knocking, and the thing the entire agent
ecosystem is built on obeying.

On the 230 site run of 2026-08-30, of the **32 sites that refused an agent, 32
announced nothing there.** No exception. In the other direction, four sites
(amazon.com, instacart.com, linkedin.com, ziprecruiter.com) bar agents in
robots.txt and serve them anyway, so a careful client that reads the notice and
obeys it keeps itself out of a site that would have let it in.

Exactly one site in 230 was consistent: tripadvisor.com bars GPTBot and refuses
GPTBot. For the identities that carry a waiting person, not one site did both.

So the two channels are not merely unaligned, they point opposite ways, and the
well behaved agent loses at both ends: turned away where no notice was given,
and staying out where the door was open. Any standard built on agents declaring
themselves and respecting published policy has to reckon with that, because
right now neither half of the bargain is being kept on the other side.

## What the network confirmed, and what it did not

All 32 hosts the 2026-08-30 run found refusing an agent were put to the
validators, one round each, no failures. What came back:

| | |
|---|---|
| **14** | served the silent validator and refused it once it declared. Our finding, reproduced by machines we do not control |
| **11** | refused the validators before identity ever came up |
| **4** | served the validators both ways, so from that vantage there was nothing to see |
| 3 | other combinations, in `results/attestations.json` |

The last two rows stay in the record rather than being trimmed out. A site that
refuses a home connection and serves a datacentre is not contradicting us, it is
filtering on something other than identity, and the same day's two vantage runs
disagreed on 18 of 72 sites for the same reason.

So the honest reading is narrower than the headline and stronger than an
assertion: **on 14 named sites, an independent validator set was let in while
silent and turned away the moment it said what it was.** That is on chain, with
the transaction for each, and nobody has to take our word for it.

## Pledge: the same promise, with money behind it

Measuring the gap is one thing. `contracts/pledge.py` closes it.

A site publishes what it promises about agent access and leaves collateral
behind it. Anyone turned away calls `claim`. Neither side supplies evidence,
because evidence from either side would be worthless: the validators go and
knock themselves, twice and seconds apart, silent and then declaring an agent
identity. If the door opened for the silent knock and shut for the declared one,
the promise was not kept and the collateral pays the person who was refused.

Live on GenLayer Studionet at `0x9fC4B5d6cb9E1260c8dA495B03F8b5638339cD7F`
(`demo_pledge.log` is the transcript):

| domain | silent | declared | claim | paid |
|---|---|---|---|---|
| nike.com | SERVED | REFUSED | **upheld** | 0.002 GEN to the claimant |
| walmart.com | SERVED | SERVED | rejected | nothing |

Walmart is the control. The same promise, the same claim, the same round, and
the contract refuses to pay because nothing was broken.

**What counts as broken is narrow on purpose.** A site that is down, or that
refuses everybody, refuses both knocks and owes nothing. Only opening for a
silent client and shutting for one that says what it is breaks this particular
promise, which is the only thing the site promised.

**Four rules money forces**, each from something that has gone wrong before. A
payable method never raises, because raising reverts the record and keeps the
value: every refused deposit here is paid straight back. A failed round pays
nobody, in either direction. Nothing inside the block reads storage or raises.
And one address is paid once per domain, or a single refusal would drain the
collateral by being reported in a loop.

`python contracts/tests/pledge_rules.py` puts 22 checks through `pledge`,
`claim` and `close` on a real instance, including every way of not paying:
promise kept, site down, site shut to everyone, site unreachable, a second claim
from a paid address, the owner claiming against itself, an early withdrawal, and
a payout larger than the collateral.

One of those tests exists because of a bug this repository shipped for an hour:
`gl.evm.contract_interface` is a decorator, not a call. Written the wrong way,
the contract deployed cleanly, accepted collateral, and answered every claim
correctly except the one path that pays somebody, which came back empty. The
stub in the test now models the decorator, so that shape cannot pass again.

## Three holes a steward found

**Anybody could pledge anybody's domain.** Our own first demo pledged nike.com,
which we do not own. A board of promises where the promise may not be the site's
own is a board of rumours.

A pledge now needs proof of control. The owner publishes its address at
`https://<domain>/.well-known/split-pledge.txt`, calls `verify`, and every
validator fetches that file itself under `strict_eq`. The comparison is against
the whole trimmed body, not a substring, because a file that merely mentions an
address in a sentence is not a domain vouching for it. Proof expires after
thirty days, since domains change hands.

**The claimant chose the payout.** A claim named its own bounty, so one refusal
could ask for the whole collateral. The payout per upheld claim is fixed by the
pledge, by the party putting up the money, and `claim` now takes nothing but a
domain.

**Rotating addresses.** One address could be paid once per domain, so a single
refusal reported from twenty addresses emptied the collateral twenty times.
Payouts are capped inside an observation window, by count and by value. Past the
cap a claim is still recorded as upheld and pays nothing, because the finding is
true whether or not there is budget left for it.

Shown on chain at the address above:

```
pledge nike.com     {"ok":false,"error":"prove control of that domain first ..."}
verify              {"ok":true,"controller":"0x8051...6258","good_for_seconds":2592000}
pledge              {"ok":true,"payout_each":"2000000000000000","window_seconds":3600,
                     "max_claims_per_window":3}
claim, by another   {"ok":true,"quiet":"SERVED","declared":"SERVED","upheld":false,"paid":"0"}
```

**A fourth thing, found while fixing those.** The contract knocked at
`https://www.<domain>/`, so the first run of this demo came back
`UNREACHABLE` on both legs: `www.jspiiv.github.io` does not exist. It now knocks
at the domain as pledged, which is the host the promise was actually made about.

`python contracts/tests/pledge_rules.py` is now 35 checks through `verify`,
`pledge`, `claim` and `close`, including a pledge without proof, a proof file
naming somebody else, an address merely mentioned in a sentence, a stale proof,
six rotating addresses against a window that allows three, and a capped claim
that is recorded and pays nothing.

## The promise now decides what is measured

The first correction bound a pledge to a proved controller and capped the
payouts. It missed the third thing asked for, and the miss was the important
one: **the promise text was prose nobody read.** A site could publish any
sentence it liked while every claim settled the same fixed condition
underneath, so the published promise and the thing being enforced had nothing to
do with each other. A steward rejected it for exactly that, and was right.

A pledge now carries terms the round can act on:

* **which identities it covers**, from a vocabulary the contract can knock as:
  `chatgpt_user`, `claude_user`, `perplexity_user`, `gptbot`. A claim under an
  identity the promise does not name is refused before any round opens.
* **what is promised**, one of two:
  * `SAME_DOOR` the declared client is let in wherever the silent one is
  * `SAME_PAGE` the same, and handed a page of comparable size

The prose stays, for a person to read. It is no longer the thing being enforced,
and the contract says so.

**Why two conditions rather than one.** A site that answers an agent with a stub
is keeping `SAME_DOOR` and breaking `SAME_PAGE`. Skyscanner does exactly that in
our own measurement: 200 KB to a browser, 708 bytes to an agent. Which of those a
site is willing to promise should be the site's to say, not ours to assume.

The size comparison never leaves the round. Validators fetch from different
places, so an exact byte count would split the jury over a rotating banner; what
crosses to consensus is the coarse verdict each validator reached under the same
rule, with a 40 percent tolerance.

Live on GenLayer Studionet at `0x3FFeC768c08e6E149339413CDc188F71e6c8De39`,
run end to end in `demo_pledge.log`:

```
pledge nike.com     refused, no proof of control
no identities       refused, name one from chatgpt_user, claude_user, gptbot, perplexity_user
unknown condition   refused, either SAME_DOOR or SAME_PAGE
verify              controller 0x8051...6258, good for 30 days
pledge              covers [chatgpt_user, claude_user], condition SAME_PAGE
claim as gptbot     refused, that promise does not cover gptbot
claim as chatgpt_user  SERVED then SERVED, not upheld, nothing paid
```

`python contracts/tests/pledge_rules.py` is now 47 checks. Twelve are new: a
pledge naming no identity, an identity the contract cannot knock as, a missing
condition, an unknown condition, a claim under an uncovered identity, and the
pair that matters most, where the same site behaviour is judged against two
different published promises. A page cut to a fifth breaks `SAME_PAGE` and pays,
does not break `SAME_DOOR` and pays nothing, and a page a tenth smaller breaks
neither.
