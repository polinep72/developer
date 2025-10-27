/*
 Minimal MCP stdio client to test @modelcontextprotocol/server-sequential-thinking
 Usage (PowerShell):
   node C:\\Soft_IPK\\sequential_thinking_test.js
 Requirements: Node.js, internet for npx to resolve the package on first run
*/

const { spawn } = require('child_process');

// Simple logger: only errors per user preference; minimal success output
function logInfo(message) {
  // Intentionally keep quiet to avoid noisy logs
}
function logError(message, err) {
  const details = err ? `\n${(err && err.stack) || err}` : '';
  console.error(`[sequential-thinking-test][ERROR] ${message}${details}`);
}

// LSP/MCP-style message framing over stdio
class StdioJsonRpc {
  constructor(child) {
    this.child = child;
    this.buffer = Buffer.alloc(0);
    this.contentLength = null;
    this.pending = new Map();
    this.nextId = 1;

    child.stdout.on('data', (chunk) => this._onData(chunk));
    child.stderr.on('data', (chunk) => {
      // Forward server stderr as error-level
      logError(`server stderr: ${chunk.toString().trim()}`);
    });
    child.stdin.on('error', (e) => {
      logError('stdin error', e);
    });
    child.on('exit', (code) => {
      if (code !== 0) logError(`server exited with code ${code}`);
    });
  }

  _onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      if (this.contentLength == null) {
        const headerEndCrLf = this.buffer.indexOf('\r\n\r\n');
        const headerEndLf = this.buffer.indexOf('\n\n');
        const headerEnd = headerEndCrLf !== -1 ? headerEndCrLf : headerEndLf;
        if (headerEnd === -1) return; // need more data
        const header = this.buffer.slice(0, headerEnd).toString('utf8');
        const match = /Content-Length:\s*(\d+)/i.exec(header);
        if (!match) {
          logError(`Missing Content-Length in header: ${header}`);
          this.buffer = this.buffer.slice(headerEnd + (headerEndCrLf !== -1 ? 4 : 2));
          continue;
        }
        this.contentLength = parseInt(match[1], 10);
        this.buffer = this.buffer.slice(headerEnd + (headerEndCrLf !== -1 ? 4 : 2));
      }
      if (this.buffer.length < this.contentLength) return; // wait full body
      const body = this.buffer.slice(0, this.contentLength).toString('utf8');
      this.buffer = this.buffer.slice(this.contentLength);
      this.contentLength = null;

      try {
        const msg = JSON.parse(body);
        if (msg.id != null && (msg.result != null || msg.error != null)) {
          const pending = this.pending.get(msg.id);
          if (pending) {
            this.pending.delete(msg.id);
            if (msg.error) pending.reject(msg.error);
            else pending.resolve(msg.result);
          }
        } else {
          // notifications or server requests are ignored for this test
        }
      } catch (e) {
        logError('Failed to parse server message', e);
      }
    }
  }

  send(method, params, timeoutMs = 10000) {
    const id = this.nextId++;
    const payload = { jsonrpc: '2.0', id, method, params };
    const json = JSON.stringify(payload);
    const header = `Content-Length: ${Buffer.byteLength(json, 'utf8')}\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8`;
    const frame = `${header}\r\n\r\n${json}`;
    const ok = this.child.stdin.write(frame, 'utf8');
    if (!ok) {
      // backpressure: wait for drain to avoid chunking issues
      this.child.stdin.once('drain', () => {});
    }
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Timeout waiting response for method ${method}`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (v) => { clearTimeout(t); resolve(v); },
        reject: (e) => { clearTimeout(t); reject(e); }
      });
    });
  }
}

const fs = require('fs');
const path = require('path');

function findOnPath(names) {
  const pathVar = process.env.PATH || process.env.Path || '';
  const dirs = pathVar.split(';').filter(Boolean);
  for (const dir of dirs) {
    for (const name of names) {
      const candidate = path.join(dir, name);
      try {
        if (fs.existsSync(candidate)) return candidate;
      } catch (_) { /* ignore */ }
    }
  }
  return null;
}

function hasDocker() {
  // naive PATH check for docker(.exe)
  return !!findOnPath(['docker.exe', 'docker']);
}

function resolveNpxCommand() {
  if (process.platform !== 'win32') return 'npx';
  // Prefer absolute path to avoid quoting issues with spaces; include PowerShell shim first
  const abs = findOnPath(['npx.ps1', 'npx.cmd', 'npx.exe']);
  if (abs) return abs;
  // Fallback common installation dirs
  const candidates = [
    'C:\\Program Files\\nodejs\\npx.ps1',
    'C:\\Program Files\\nodejs\\npx.cmd',
    'C:\\Program Files (x86)\\nodejs\\npx.cmd'
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return 'npx';
}

async function main() {
  // Start server via available runtime
  const npxCmd = resolveNpxCommand();
  let child;
  if (hasDocker()) {
    // Prefer Docker since it cleanly supports stdio -i
    child = spawn('docker', ['run', '--rm', '-i', 'mcp/sequentialthinking'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env }
    });
  } else if (process.platform === 'win32') {
    if (npxCmd.toLowerCase().endsWith('.ps1')) {
      const pwsh = process.env.SystemRoot
        ? path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
        : 'powershell.exe';
      child = spawn(pwsh, [
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', npxCmd,
        '-y', '@modelcontextprotocol/server-sequential-thinking'
      ], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, DISABLE_THOUGHT_LOGGING: 'true' }
      });
    } else {
      const cmdExe = process.env.COMSPEC || 'C\\\\Windows\\\\System32\\\\cmd.exe';
      const fullCmd = `"${npxCmd}" -y @modelcontextprotocol/server-sequential-thinking`;
      child = spawn(cmdExe, ['/d', '/s', '/c', fullCmd], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, DISABLE_THOUGHT_LOGGING: 'true' }
      });
    }
  } else {
    child = spawn(npxCmd, ['-y', '@modelcontextprotocol/server-sequential-thinking'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, DISABLE_THOUGHT_LOGGING: 'true' }
    });
  }
  child.on('error', (e) => {
    logError(`Failed to spawn server`, e);
    try { child.kill(); } catch (_) {}
    process.exitCode = 1;
  });

  const rpc = new StdioJsonRpc(child);

  try {
    // Small delay to let server start listening on stdio
    await new Promise(r => setTimeout(r, 800));

    // 1) initialize
    const initRes = await rpc.send('initialize', {
      version: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'sequential-thinking-test', version: '1.0.0' }
    }, 60000);
    logInfo(`initialized: ${JSON.stringify(initRes)}`);

    // notify initialized (some servers expect this)
    try { await rpc.send('initialized', {}, 5000); } catch (_) {}

    // 2) list tools
    const tools = await rpc.send('tools/list', {}, 30000);
    const names = (tools && tools.tools ? tools.tools.map(t => t.name) : []) || [];
    if (!names.includes('sequential_thinking')) {
      throw new Error('Tool sequential_thinking not found in tools/list');
    }

    // 3) call sequential_thinking (first thought)
    const call1 = await rpc.send('tools/call', {
      name: 'sequential_thinking',
      arguments: {
        thought: 'Шаг 1: сформулировать цель таска',
        nextThoughtNeeded: true,
        thoughtNumber: 1,
        totalThoughts: 5
      }
    }, 30000);

    // 4) call revision
    const call2 = await rpc.send('tools/call', {
      name: 'sequential_thinking',
      arguments: {
        thought: 'Ревизия шага 1: уточнить ограничения',
        isRevision: true,
        revisesThought: 1,
        nextThoughtNeeded: true,
        thoughtNumber: 2,
        totalThoughts: 5
      }
    }, 30000);

    // 5) branch call
    const call3 = await rpc.send('tools/call', {
      name: 'sequential_thinking',
      arguments: {
        thought: 'Альтернативная стратегия обхода логина',
        branchFromThought: 2,
        branchId: 'A',
        nextThoughtNeeded: false,
        thoughtNumber: 3,
        totalThoughts: 5
      }
    }, 30000);

    console.log(JSON.stringify({ ok: true, call1, call2, call3 }));

    try { await rpc.send('shutdown', {} , 5000); } catch (_) {}
    try { child.stdin.end(); } catch (_) {}
  } catch (e) {
    logError('Test failed', e);
    try { child.kill(); } catch (_) {}
    process.exitCode = 1;
  }
}

main();
