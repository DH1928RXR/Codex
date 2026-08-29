#!/usr/bin/env node
/**
 * EOR v2 — minimal VM Exec MCP server
 *
 * Purpose:
 *   Prove ChatGPT -> MCP -> actual EOR VM round-trip with one tool:
 *
 *     vm_exec({ command }) -> { stdout, stderr, exit_code }
 *
 * This first version intentionally permits only the P1 acceptance commands:
 *   - hostname
 *   - whoami
 *   - id -u
 *   - uname -a
 *   - echo EOR_ARC_VM_CONTROL
 *
 * Requirements:
 *   - Node.js 18+
 *   - zero npm dependencies
 *
 * Run:
 *   EOR_MCP_HOST=127.0.0.1 EOR_MCP_PORT=8787 node vm-exec-mcp.mjs
 *
 * Endpoint:
 *   http://127.0.0.1:8787/mcp
 *
 * For ChatGPT, expose /mcp through a supported remote HTTPS MCP transport/tunnel.
 */

import http from "node:http";
import { execFile } from "node:child_process";

const HOST = process.env.EOR_MCP_HOST || "127.0.0.1";
const PORT = Number(process.env.EOR_MCP_PORT || "8787");

const SERVER_NAME = "eor-v2-vm-exec";
const SERVER_VERSION = "0.2.0";

// Exact P1 proof surface. Do not silently broaden this list.
const COMMANDS = new Map([
  ["hostname", ["hostname", []]],
  ["whoami", ["whoami", []]],
  ["id -u", ["id", ["-u"]]],
  ["uname -a", ["uname", ["-a"]]],
  ["echo EOR_ARC_VM_CONTROL", ["printf", ["EOR_ARC_VM_CONTROL\n"]]],
]);

const CODEX_USER = "danhebb";
const CODEX_BIN = "/home/danhebb/.local/bin/codex";
const CODEX_CWD = "/home/danhebb";

function jsonRpcResult(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function jsonRpcError(id, code, message, data = undefined) {
  const error = { code, message };
  if (data !== undefined) error.data = data;
  return { jsonrpc: "2.0", id: id ?? null, error };
}

function sendJson(res, status, body, extraHeaders = {}) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(payload),
    ...extraHeaders,
  });
  res.end(payload);
}

function sendEmpty(res, status = 202) {
  res.writeHead(status, { "content-length": "0" });
  res.end();
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(new Error("request too large"));
        req.destroy();
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : null);
      } catch (err) {
        reject(err);
      }
    });
    req.on("error", reject);
  });
}

function chooseProtocolVersion(requested) {
  if (typeof requested === "string" && /^\d{4}-\d{2}-\d{2}$/.test(requested)) {
    return requested;
  }
  return "2025-06-18";
}

function toolDefinition() {
  return {
    name: "vm_exec",
    title: "EOR VM diagnostic execution",
    description:
      "Runs one of the bounded EOR P1 acceptance commands on the actual VM and returns stdout, stderr, and exit_code.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["command"],
      properties: {
        command: {
          type: "string",
          enum: [...COMMANDS.keys()],
          description: "Exact command to run on the EOR VM.",
        },
      },
    },
    outputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["stdout", "stderr", "exit_code"],
      properties: {
        stdout: { type: "string" },
        stderr: { type: "string" },
        exit_code: { type: "integer" },
      },
    },
  };
}

function codexToolDefinition() {
  return {
    name: "codex_run",
    title: "Run Codex on the EOR VM",
    description:
      "Runs one bounded, non-interactive Codex task on the EOR VM and returns its terminal stdout, stderr, and exit code.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["prompt"],
      properties: {
        prompt: {
          type: "string",
          minLength: 1,
          maxLength: 20_000,
          description: "Exact task prompt to give Codex.",
        },
      },
    },
    outputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["stdout", "stderr", "exit_code"],
      properties: {
        stdout: { type: "string" },
        stderr: { type: "string" },
        exit_code: { type: "integer" },
      },
    },
  };
}

function runBoundedCommand(command) {
  return new Promise((resolve) => {
    const spec = COMMANDS.get(command);
    if (!spec) {
      resolve({
        ok: false,
        stdout: "",
        stderr: `command not permitted by P1 server: ${command}`,
        exit_code: 126,
      });
      return;
    }

    const [file, args] = spec;

    execFile(
      file,
      args,
      {
        encoding: "utf8",
        timeout: 10_000,
        maxBuffer: 1024 * 1024,
        windowsHide: true,
      },
      (error, stdout, stderr) => {
        let exitCode = 0;
        if (error) {
          if (typeof error.code === "number") exitCode = error.code;
          else exitCode = 1;
        }
        resolve({
          ok: !error,
          stdout: stdout ?? "",
          stderr: stderr ?? "",
          exit_code: exitCode,
        });
      },
    );
  });
}

function runCodex(prompt) {
  return new Promise((resolve) => {
    execFile(
      "/usr/bin/sudo",
      [
        "-u",
        CODEX_USER,
        "-H",
        CODEX_BIN,
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        prompt,
      ],
      {
        cwd: CODEX_CWD,
        encoding: "utf8",
        timeout: 600_000,
        maxBuffer: 10 * 1024 * 1024,
        windowsHide: true,
      },
      (error, stdout, stderr) => {
        let exitCode = 0;
        if (error) {
          if (typeof error.code === "number") exitCode = error.code;
          else if (error.killed) exitCode = 124;
          else exitCode = 1;
        }
        resolve({
          ok: !error,
          stdout: stdout ?? "",
          stderr: stderr ?? "",
          exit_code: exitCode,
        });
      },
    );
  });
}

async function handleRpc(message) {
  if (!message || message.jsonrpc !== "2.0" || typeof message.method !== "string") {
    return jsonRpcError(message?.id, -32600, "Invalid Request");
  }

  const { id, method, params } = message;

  if (method === "initialize") {
    return jsonRpcResult(id, {
      protocolVersion: chooseProtocolVersion(params?.protocolVersion),
      capabilities: {
        tools: {},
      },
      serverInfo: {
        name: SERVER_NAME,
        version: SERVER_VERSION,
      },
      instructions:
        "EOR v2 primitives server. Exposes bounded P1 VM diagnostics and direct non-interactive Codex execution.",
    });
  }

  if (method === "ping") {
    return jsonRpcResult(id, {});
  }

  if (method === "tools/list") {
    return jsonRpcResult(id, {
      tools: [toolDefinition(), codexToolDefinition()],
    });
  }

  if (method === "tools/call") {
    let result;

    if (params?.name === "vm_exec") {
      const command = params?.arguments?.command;
      if (typeof command !== "string") {
        return jsonRpcError(id, -32602, "vm_exec requires string argument: command");
      }
      result = await runBoundedCommand(command);
    } else if (params?.name === "codex_run") {
      const prompt = params?.arguments?.prompt;
      if (typeof prompt !== "string" || prompt.length === 0 || prompt.length > 20_000) {
        return jsonRpcError(
          id,
          -32602,
          "codex_run requires a non-empty prompt of at most 20000 characters",
        );
      }
      result = await runCodex(prompt);
    } else {
      return jsonRpcError(id, -32602, "Unknown tool");
    }

    const structured = {
      stdout: result.stdout,
      stderr: result.stderr,
      exit_code: result.exit_code,
    };

    return jsonRpcResult(id, {
      content: [
        {
          type: "text",
          text: JSON.stringify(structured),
        },
      ],
      structuredContent: structured,
      isError: !result.ok,
    });
  }

  if (method === "notifications/initialized" || method.startsWith("notifications/")) {
    return null;
  }

  return jsonRpcError(id, -32601, `Method not found: ${method}`);
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "POST, OPTIONS",
      "access-control-allow-headers":
        "content-type, accept, mcp-protocol-version, mcp-session-id, mcp-method, mcp-name",
      "access-control-expose-headers": "mcp-session-id",
    });
    res.end();
    return;
  }

  if (req.url !== "/mcp") {
    sendJson(res, 404, { error: "not found" });
    return;
  }

  if (req.method === "GET") {
    sendJson(res, 405, { error: "GET not supported by this stateless MCP server" });
    return;
  }

  if (req.method !== "POST") {
    sendJson(res, 405, { error: "method not allowed" });
    return;
  }

  let message;
  try {
    message = await readJson(req);
  } catch (err) {
    sendJson(res, 400, jsonRpcError(null, -32700, "Parse error"));
    return;
  }

  if (Array.isArray(message)) {
    const replies = [];
    for (const item of message) {
      const reply = await handleRpc(item);
      if (reply !== null) replies.push(reply);
    }
    if (replies.length === 0) {
      sendEmpty(res, 202);
      return;
    }
    sendJson(res, 200, replies, {
      "access-control-allow-origin": "*",
    });
    return;
  }

  const reply = await handleRpc(message);
  if (reply === null) {
    sendEmpty(res, 202);
    return;
  }

  sendJson(res, 200, reply, {
    "access-control-allow-origin": "*",
  });
});

server.listen(PORT, HOST, () => {
  console.error(
    `${SERVER_NAME} ${SERVER_VERSION} listening on http://${HOST}:${PORT}/mcp`,
  );
});

function shutdown(signal) {
  console.error(`${signal}: shutting down`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 3000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
