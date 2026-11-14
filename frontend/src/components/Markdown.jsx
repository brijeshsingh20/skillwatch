import { Fragment } from "react";

/** Tiny Markdown renderer (headings, lists, tables, code blocks, bold, inline code). No HTML is ever injected. */
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code key={i} className="rounded bg-slate-100 px-1 text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    return <Fragment key={i}>{part}</Fragment>;
  });
}

const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
const isTableSep = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);

export function parseBlocks(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.startsWith("```")) {
      const code = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++;
      blocks.push({ type: "code", text: code.join("\n") });
    } else if (/^#{1,4}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      blocks.push({ type: "h", level, text: line.replace(/^#+\s*/, "") });
      i++;
    } else if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = cells(line);
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push({ type: "table", header, rows });
    } else if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ""));
      blocks.push({ type: "list", ordered, items });
    } else {
      const para = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```)/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) para.push(lines[i++]);
      blocks.push({ type: "p", text: para.join(" ") });
    }
  }
  return blocks;
}

const HEADING = { 1: "text-2xl font-bold mt-2", 2: "text-xl font-semibold mt-6", 3: "text-lg font-semibold mt-4", 4: "font-semibold mt-3" };

export default function Markdown({ source }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      {parseBlocks(source).map((b, i) => {
        if (b.type === "h") return <div key={i} className={HEADING[b.level]} role="heading" aria-level={b.level}>{inline(b.text)}</div>;
        if (b.type === "code") return <pre key={i} className="overflow-x-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{b.text}</pre>;
        if (b.type === "list") {
          const Tag = b.ordered ? "ol" : "ul";
          return (
            <Tag key={i} className={`${b.ordered ? "list-decimal" : "list-disc"} space-y-1 pl-6`}>
              {b.items.map((it, j) => <li key={j}>{inline(it)}</li>)}
            </Tag>
          );
        }
        if (b.type === "table")
          return (
            <div key={i} className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 border border-slate-200">
                <thead className="bg-slate-50">
                  <tr>{b.header.map((h, j) => <th key={j} className="th">{inline(h)}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k} className="td">{inline(c)}</td>)}</tr>)}
                </tbody>
              </table>
            </div>
          );
        return <p key={i}>{inline(b.text)}</p>;
      })}
    </div>
  );
}
