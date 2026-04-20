export interface SnippetInput {
  url: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
}

export interface Snippets {
  curl: string;
  python: string;
  javascript: string;
}

function prettyJson(body: unknown): string {
  return JSON.stringify(body, null, 2);
}

/**
 * Parse the protocol + host out of an absolute URL. Falls back to the origin
 * of the page when `url` is relative (same-host) so the login snippet
 * still points at the right auth endpoint.
 */
function deriveOrigin(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    if (typeof window !== "undefined") return window.location.origin;
    return "";
  }
}

export function buildSnippets({ url, method, body }: SnippetInput): Snippets {
  const hasBody = body !== undefined && body !== null;
  const bodyString = hasBody ? prettyJson(body) : "";
  const escapedBody = bodyString.replace(/'/g, "'\\''");
  const origin = deriveOrigin(url);
  const loginUrl = `${origin}/api/auth/login`;

  // ---------------- curl ----------------
  // Two steps: log in once to a cookie jar, then reuse it for the prediction.
  const curlPredictParts = [
    `curl -X ${method} '${url}' \\`,
    `  -H 'Content-Type: application/json' \\`,
    `  -b cookie.jar`,
  ];
  if (hasBody) {
    curlPredictParts[curlPredictParts.length - 1] += " \\";
    curlPredictParts.push(`  -d '${escapedBody}'`);
  }
  const curl = [
    `# 1) Log in once — stores the platform session cookie in ./cookie.jar`,
    `curl -s -X POST '${loginUrl}' \\`,
    `  -H 'Content-Type: application/json' \\`,
    `  -c cookie.jar \\`,
    `  -d '{"email":"<your-email>","password":"<your-password>"}' > /dev/null`,
    ``,
    `# 2) Call the model — reuses the cookie jar from step 1`,
    curlPredictParts.join("\n"),
  ].join("\n");

  // ---------------- python ----------------
  // requests.Session persists the cookie across calls so a long-lived
  // client only authenticates once per process.
  const pythonPayloadLine = hasBody ? `\npayload = ${bodyString}\n` : "";
  const pythonCallArgs = hasBody
    ? `    "${url}",\n    json=payload,\n    timeout=30,`
    : `    "${url}",\n    timeout=30,`;
  const python = `import requests

session = requests.Session()
session.post(
    "${loginUrl}",
    json={"email": "<your-email>", "password": "<your-password>"},
    timeout=30,
).raise_for_status()
${pythonPayloadLine}
response = session.${method.toLowerCase()}(
${pythonCallArgs}
)
response.raise_for_status()
print(response.json())`;

  // ---------------- javascript ----------------
  // credentials: "include" sends + stores the session cookie. Works in
  // Node (via undici/global fetch) with a CookieJar, or in the browser
  // directly.
  const jsBodyLine = hasBody
    ? `  body: JSON.stringify(${bodyString}),\n`
    : "";
  const javascript = `// 1) Log in once
await fetch("${loginUrl}", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "<your-email>", password: "<your-password>" }),
});

// 2) Call the model
const response = await fetch("${url}", {
  method: "${method}",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
${jsBodyLine}});

if (!response.ok) throw new Error(\`API \${response.status}\`);
const data = await response.json();
console.log(data);`;

  return { curl, python, javascript };
}
