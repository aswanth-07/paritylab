import {readFileSync} from 'node:fs';
import {transform} from 'lightningcss';

const result = transform({
  filename: 'web/styles.css',
  code: readFileSync(new URL('../web/styles.css', import.meta.url)),
  errorRecovery: false
});
if (result.warnings.length) {
  throw new Error(JSON.stringify(result.warnings));
}
console.log('CSS parsed without errors or warnings.');
