// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

it('beautifies synthetic glob matches using EditorConfig with the patched dependencies', () => {
  const directory = mkdtempSync(join(tmpdir(), 'fastdeploy-toolchain-'));
  try {
    writeFileSync(join(directory, '.editorconfig'), 'root = true\n\n[*.js]\nindent_style = space\nindent_size = 3\n');
    writeFileSync(join(directory, 'sample.js'), 'if(true){hello();}');
    const cli = resolve('node_modules/js-beautify/js/bin/js-beautify.js');
    execFileSync(process.execPath, [cli, '--editorconfig', '--replace', '*.js'], { cwd: directory });
    expect(readFileSync(join(directory, 'sample.js'), 'utf8')).toContain('\n   hello();');
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
