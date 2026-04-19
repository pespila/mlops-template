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

export function buildSnippets({ url, method, body }: SnippetInput): Snippets {
  const hasBody = body !== undefined && body !== null;
  const bodyString = hasBody ? prettyJson(body) : "";

  const curlParts = [
    `curl -X ${method} '${url}'`,
    `  -H 'Content-Type: application/json'`,
    `  --cookie 'session=<your-session-cookie>'`,
  ];
  if (hasBody) curlParts.push(`  -d '${bodyString.replace(/'/g, "'\\''")}'`);
  const curl = curlParts.join(" \\\n");

  const python = hasBody
    ? `import requests

payload = ${bodyString}

response = requests.${method.toLowerCase()}(
    "${url}",
    json=payload,
    cookies={"session": "<your-session-cookie>"},
    timeout=30,
)
response.raise_for_status()
print(response.json())`
    : `import requests

response = requests.${method.toLowerCase()}(
    "${url}",
    cookies={"session": "<your-session-cookie>"},
    timeout=30,
)
response.raise_for_status()
print(response.json())`;

  const javascript = hasBody
    ? `const response = await fetch("${url}", {
  method: "${method}",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(${bodyString}),
});

if (!response.ok) throw new Error(\`API \${response.status}\`);
const data = await response.json();
console.log(data);`
    : `const response = await fetch("${url}", {
  method: "${method}",
  credentials: "include",
});

if (!response.ok) throw new Error(\`API \${response.status}\`);
const data = await response.json();
console.log(data);`;

  return { curl, python, javascript };
}
