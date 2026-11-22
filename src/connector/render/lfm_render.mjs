// Markdown on stdin, HTML on stdout, rendered with Lossless Flavored Markdown.
//
//   node src/connector/render/lfm_render.mjs < memo.md > body.html
//
// Called by src/connector/render/lfm.py as a subprocess, the way Pandoc is
// called. It prints the HTML body only; the caller puts it in the firm's
// branded page.
//
// Two steps, never one chain: parseMarkdown runs every LFM transform, then
// remark-rehype and rehype-stringify turn the tree into HTML. Chaining
// remarkLfm and remarkRehype in one processor attaches LFM's plugins after
// remark-rehype, so callouts and citations are silently skipped (a known LFM
// issue).
//
// Citations: LFM numbers hex keys ([^1ucdcd]) by first citation and takes the
// definitions out of the tree, handing them over in tree.data.citations.ordered.
// The sources list is rendered from that, so its numbers always match the
// inline ones. Nothing here invents a number.
//
// The /browser entry is used even in Node: it has no Open Graph fetching, so a
// render makes no network calls.

import { parseMarkdown } from "@lossless-group/lfm/browser";
import rehypeStringify from "rehype-stringify";
import remarkRehype from "remark-rehype";
import { unified } from "unified";

const esc = (value) =>
  String(value).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** LFM keeps a callout's title in its attributes; put it in the HTML. */
function titleCallouts(node) {
  if (
    node.type === "containerDirective" &&
    node.name === "callout" &&
    node.attributes?.title
  ) {
    node.children.unshift({
      type: "paragraph",
      data: { hProperties: { className: ["callout-title"] } },
      children: [{ type: "strong", children: [{ type: "text", value: node.attributes.title }] }],
    });
  }
  for (const child of node.children ?? []) titleCallouts(child);
}

function sourcesList(ordered) {
  const items = ordered.map((c) => {
    const id = `user-content-fn-${esc(c.identifier)}`;
    if (!c.url) return `<li id="${id}">${esc(c.raw ?? c.identifier)}</li>`;
    let item = `<a href="${esc(c.url)}">${esc(c.title ?? c.url)}</a>`;
    if (c.source) item += ` <span class="source-host">${esc(c.source)}</span>`;
    if (c.publishedDate) item += ` <span class="source-date">${esc(c.publishedDate)}</span>`;
    return `<li id="${id}">${item}</li>`;
  });
  return `<ol class="sources">\n${items.join("\n")}\n</ol>`;
}

// A memo's citation block is "---" then "### Citations" at the end; LFM takes
// its definitions out, leaving the heading. The list goes under that heading,
// or under a new one when the markdown has none.
const TRAILING_HEADING = /<h([23])[^>]*>\s*(?:Citations|Sources|References)\s*<\/h\1>\s*$/i;

async function render(markdown) {
  const tree = await parseMarkdown(markdown);
  titleCallouts(tree);
  const hast = await unified().use(remarkRehype, { allowDangerousHtml: true }).run(tree);
  let html = unified().use(rehypeStringify, { allowDangerousHtml: true }).stringify(hast);
  const ordered = tree.data?.citations?.ordered ?? [];
  if (ordered.length) {
    html = html.trimEnd();
    if (!TRAILING_HEADING.test(html)) html += '\n<h3 id="citations">Citations</h3>';
    html += "\n" + sourcesList(ordered);
  }
  return html + "\n";
}

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
try {
  process.stdout.write(await render(Buffer.concat(chunks).toString("utf8")));
} catch (err) {
  process.stderr.write(`lfm_render: ${err?.stack ?? err}\n`);
  process.exit(1);
}
