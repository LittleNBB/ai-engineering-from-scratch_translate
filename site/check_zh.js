const fs = require('fs');
const c = fs.readFileSync('site/data.js', 'utf8');

// Find each phase and count zh entries
const phaseRegex = /"id":\s*(\d+)/g;
let match;
const phases = [];
while ((match = phaseRegex.exec(c)) !== null) {
  phases.push({ id: parseInt(match[1]), idx: match.index });
}

for (let i = 0; i < phases.length; i++) {
  const start = phases[i].idx;
  const end = i + 1 < phases.length ? phases[i + 1].idx : c.length;
  const chunk = c.substring(start, end);
  const zhCount = (chunk.match(/"zh":\s*\{/g) || []).length;
  const enCount = (chunk.match(/"en":\s*\{/g) || []).length;
  console.log(`Phase ${phases[i].id}: en=${enCount}, zh=${zhCount}`);
}