// Orbit adapter: upstream providers are read-only; no Career Ops CLI or tracker.
import fs from 'node:fs';
import greenhouse from '../vendor/career-ops/providers/greenhouse.mjs';
import ashby from '../vendor/career-ops/providers/ashby.mjs';
import lever from '../vendor/career-ops/providers/lever.mjs';
import workday from '../vendor/career-ops/providers/workday.mjs';
import smartrecruiters from '../vendor/career-ops/providers/smartrecruiters.mjs';
import {makeHttpCtx} from '../vendor/career-ops/providers/_http.mjs';
const providers=[greenhouse,ashby,lever,workday,smartrecruiters];
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const results=[];
let cursor=0;
await Promise.all(Array.from({length:3},async()=>{
  while(cursor<input.entries.length){
    const entry=input.entries[cursor++];
    const provider=providers.find(p=>entry.provider===p.id||(!entry.provider&&p.detect?.(entry)));
    if(!provider){results.push({name:entry.name,error:'Unsupported public provider',jobs:[]});continue;}
    try{
      const ctx={...makeHttpCtx(),maxPages:entry.max_pages||10,locationHints:input.locationHints};
      const jobs=await provider.fetch(entry,ctx);
      results.push({name:entry.name,provider:provider.id,jobs:jobs.map(j=>({...j,provider:provider.id,dedup_key:provider.dedupKey?.(j)||null}))});
    }catch(error){results.push({name:entry.name,provider:provider.id,error:String(error.message).slice(0,250),jobs:[]});}
  }
}));
process.stdout.write(JSON.stringify(results));
