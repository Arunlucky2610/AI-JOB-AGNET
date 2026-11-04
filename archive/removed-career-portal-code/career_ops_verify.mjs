import fs from 'node:fs';
import {classifyLiveness} from '../vendor/career-ops/liveness-core.mjs';
import {checkLivenessViaApi} from '../vendor/career-ops/liveness-api.mjs';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const result=input.apiOnly?await checkLivenessViaApi(input.url):classifyLiveness(input.snapshot);
process.stdout.write(JSON.stringify(result));
