// Two promises, two claims, real sites, real money.
//
// One domain that our measurement and the validators both found opening for a
// silent client and shutting for a declared one, and one that treats both the
// same. The same claim is made against each, and the contract should pay on the
// first and refuse on the second.
import { Wallet } from 'file:///C:/Users/ysfym/AppData/Roaming/npm/node_modules/genlayer/node_modules/ethers/lib.esm/index.js';
import { createClient, createAccount } from '../placard-app/node_modules/genlayer-js/dist/index.js';
import { studionet } from '../placard-app/node_modules/genlayer-js/dist/chains/index.js';
import fs from 'fs';

const KS = String.raw`C:\Users\ysfym\.genlayer\keystores`;
const load = async (name, password) => {
  const w = await Wallet.fromEncryptedJson(fs.readFileSync(`${KS}/${name}.json`, 'utf8'), password);
  return createClient({ chain: studionet, account: createAccount(w.privateKey) });
};

const site = await load('padv', 'placard-test-adv-2026');   // publishes the promises
const agent = await load('ppub', 'placard-test-pub-2026');  // gets turned away

let ADDR = process.argv[2];
if (!ADDR) {
  const hash = await site.deployContract({
    code: fs.readFileSync('contracts/pledge.py'), args: [], leaderOnly: false,
  });
  const r = await site.waitForTransactionReceipt({ hash, status: 'FINALIZED', retries: 120, interval: 10000 });
  ADDR = r?.data?.contract_address;
  console.log('deployed', ADDR, '\n');
}

const read = out => {
  try { return JSON.parse(JSON.parse(out?.consensus_data?.leader_receipt?.[0]?.result?.payload?.readable ?? '"{}"')); }
  catch { return { raw: JSON.stringify(out?.consensus_data?.leader_receipt?.[0]?.result ?? '').slice(0, 200) }; }
};

async function send(client, fn, args, value = 0n) {
  const hash = await client.writeContract({ address: ADDR, functionName: fn, args, value });
  return read(await client.waitForTransactionReceipt({ hash, status: 'FINALIZED', retries: 200, interval: 10000 }));
}

const PROMISE = 'Agents fetching a page for a person are served exactly what a browser is served.';
const COLLATERAL = 10n ** 16n;   // 0.01 GEN behind each promise
const BOUNTY = '2000000000000000'; // 0.002 GEN to anyone turned away

for (const domain of ['nike.com', 'walmart.com']) {
  console.log(domain);
  console.log('  pledge', JSON.stringify(await send(site, 'pledge', [domain, PROMISE, '3600'], COLLATERAL)));
  console.log('  claim ', JSON.stringify(await send(agent, 'claim', [domain, BOUNTY])));
  console.log();
}
console.log('board', JSON.stringify(await site.readContract({ address: ADDR, functionName: 'size', args: [] })));
