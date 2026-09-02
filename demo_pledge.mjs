// A promise about agent access, made only by the party that can prove the
// domain is its own, and settled against the terms that promise actually
// published.
//
// Four things are shown, and the last one is the correction a steward asked for:
// a domain nobody has proved cannot be pledged, a proved domain can, a claim
// under an identity the promise does not cover is refused, and the claim that is
// covered settles under the condition the pledge named rather than a fixed one.
import { Wallet } from '../courtscan/node_modules/ethers/lib.esm/index.js';
import { createClient, createAccount } from '../placard-app/node_modules/genlayer-js/dist/index.js';
import { studionet } from '../placard-app/node_modules/genlayer-js/dist/chains/index.js';
import fs from 'fs';

const ADDR = process.argv[2];
const KS = String.raw`C:\Users\ysfym\.genlayer\keystores`;
const load = async (n, p) => {
  const w = await Wallet.fromEncryptedJson(fs.readFileSync(`${KS}/${n}.json`, 'utf8'), p);
  return createClient({ chain: studionet, account: createAccount(w.privateKey) });
};

const site = await load('padv', 'placard-test-adv-2026');   // controls jspiiv.github.io
const agent = await load('ppub', 'placard-test-pub-2026');  // the one who might be turned away

const read = r => {
  try { return JSON.parse(JSON.parse(r?.consensus_data?.leader_receipt?.[0]?.result?.payload?.readable ?? '"{}"')); }
  catch { return { raw: JSON.stringify(r?.consensus_data?.leader_receipt?.[0]?.result ?? '').slice(0, 200) }; }
};
async function send(client, fn, args, value = 0n) {
  const hash = await client.writeContract({ address: ADDR, functionName: fn, args, value });
  return read(await client.waitForTransactionReceipt({ hash, status: 'FINALIZED', retries: 200, interval: 10000 }));
}

const PROMISE = 'Agents fetching a page for a person are served exactly what a browser is served.';
const COVERS = 'chatgpt_user,claude_user';
const CONDITION = 'SAME_PAGE';
const COLLATERAL = 10n ** 16n;      // 0.01 GEN behind the promise
const PAYOUT = '2000000000000000';  // 0.002 GEN per upheld claim, fixed here
const WINDOW = '3600';
const TERM = '86400';

console.log('a domain nobody has proved control of');
console.log('  pledge nike.com   ', JSON.stringify(await send(site, 'pledge',
  ['nike.com', PROMISE, COVERS, CONDITION, PAYOUT, WINDOW, TERM], COLLATERAL)));

console.log('\na promise that does not say what it promises');
console.log('  no identities     ', JSON.stringify(await send(site, 'pledge',
  ['jspiiv.github.io', PROMISE, '', CONDITION, PAYOUT, WINDOW, TERM], COLLATERAL)));
console.log('  unknown condition ', JSON.stringify(await send(site, 'pledge',
  ['jspiiv.github.io', PROMISE, COVERS, 'BE_NICE', PAYOUT, WINDOW, TERM], COLLATERAL)));

console.log('\nthe domain this account can actually prove');
console.log('  verify            ', JSON.stringify(await send(site, 'verify', ['jspiiv.github.io'])));
console.log('  pledge            ', JSON.stringify(await send(site, 'pledge',
  ['jspiiv.github.io', PROMISE, COVERS, CONDITION, PAYOUT, WINDOW, TERM], COLLATERAL)));

console.log('\nclaims are settled against the published terms');
console.log('  under gptbot, not covered',
  JSON.stringify(await send(agent, 'claim', ['jspiiv.github.io', 'gptbot'])));
console.log('  under chatgpt_user, covered',
  JSON.stringify(await send(agent, 'claim', ['jspiiv.github.io', 'chatgpt_user'])));

console.log('\nsize', JSON.stringify(await site.readContract({ address: ADDR, functionName: 'size', args: [] })));
