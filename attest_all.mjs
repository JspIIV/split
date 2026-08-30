// Put the refusals to the network, one host at a time.
//
// Everything in results/ is our measurement. This asks the validators to go and
// look for themselves, and writes down only what they agreed on. Where the two
// disagree, both stay in the record: a validator set measuring from its own
// machines is a different vantage, and the whole method here is to label
// vantages rather than average them.
//
//   node attest_all.mjs <contract> <results file> [--all]
//
// Without --all it attests the hosts the run found refusing an agent, which is
// the claim that needs somebody other than us behind it.
import { Wallet } from 'file:///C:/Users/ysfym/AppData/Roaming/npm/node_modules/genlayer/node_modules/ethers/lib.esm/index.js';
import { createClient, createAccount } from '../placard-app/node_modules/genlayer-js/dist/index.js';
import { studionet } from '../placard-app/node_modules/genlayer-js/dist/chains/index.js';
import fs from 'fs';
import path from 'path';

const [ADDR, RESULTS] = process.argv.slice(2);
const ALL = process.argv.includes('--all');
const OUT = path.join('results', 'attestations.json');
const KS = String.raw`C:\Users\ysfym\.genlayer\keystores`;

const run = JSON.parse(fs.readFileSync(RESULTS, 'utf8'));
const hosts = run.sites
  .filter(s => ALL ? s.verdict !== 'not_comparable' : s.verdict === 'refuses_agents')
  .map(s => s.host);

const w = await Wallet.fromEncryptedJson(fs.readFileSync(`${KS}/padv.json`, 'utf8'), 'placard-test-adv-2026');
const client = createClient({ chain: studionet, account: createAccount(w.privateKey) });

// The node refuses submissions with -32005 when it is at capacity, and that is
// node wide rather than about us. Swallowing it looks exactly like a round that
// never landed, which cost a full day once, so it is retried and reported.
function busy(e) {
  return /-32005|rate limit|at capacity|-32006|-32029|fetch failed|ECONNRESET|socket|502|503|429/i
    .test(String(e && (e.details || e.message) || e));
}

async function attest(host) {
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      const hash = await client.writeContract({
        address: ADDR, functionName: 'check', args: [host], value: 0n,
      });
      const receipt = await client.waitForTransactionReceipt({
        hash, status: 'FINALIZED', retries: 200, interval: 10000,
      });
      const leader = receipt?.consensus_data?.leader_receipt?.[0];
      const readable = leader?.result?.payload?.readable ?? '';
      const parsed = JSON.parse(JSON.parse(readable || '"{}"'));
      return {
        host, tx: hash,
        votes: receipt?.consensus_data?.validators?.map(v => v?.vote ?? '?') ?? [],
        execution: leader?.execution_result ?? null,
        ...parsed,
      };
    } catch (e) {
      if (!busy(e) || attempt === 5) {
        return { host, ok: false, error: String(e && (e.details || e.message) || e).slice(0, 200) };
      }
      console.log(`   .. ${host}: node busy, retry ${attempt}/5`);
      await new Promise(r => setTimeout(r, 15000 * attempt));
    }
  }
}

const done = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, 'utf8')) : { contract: ADDR, network: 'GenLayer Studionet', attestations: [] };
const already = new Set(done.attestations.filter(a => a.ok).map(a => a.host));

console.log(`${hosts.length} hosts, ${already.size} already attested\n`);
for (const host of hosts) {
  if (already.has(host)) { console.log(`  ${host.padEnd(24)} already on chain`); continue; }
  const result = await attest(host);
  done.attestations = done.attestations.filter(a => a.host !== host).concat([result]);
  done.attested_at = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(done, null, 2));
  console.log(`  ${host.padEnd(24)} ${result.ok
    ? `${result.quiet} -> ${result.declared}${result.punishes_disclosure ? '  PUNISHES DISCLOSURE' : ''}`
    : `FAILED ${result.error ?? ''}`}`);
}

const ok = done.attestations.filter(a => a.ok);
const punishing = ok.filter(a => a.punishes_disclosure);
console.log(`\n${ok.length} attested, ${punishing.length} served the silent client and refused the declared one`);
