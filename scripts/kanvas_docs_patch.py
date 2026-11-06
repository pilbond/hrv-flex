#!/usr/bin/env python3
"""Parche local de Kanvas: abre en el navegador los .md enlazados con [[...]] en las tareas.

- kanvas.py: ruta de solo lectura GET /<board>/api/doc?name=<nombre> que sirve .md de docs/ (nunca fuera).
- kanvas.html: cada [[nombre]] de una descripcion o nota abre ?doc=<nombre> en una pestana nueva,
  renderizado con el mismo markdown del tablero. Los [[...]] dentro de un doc tambien navegan.

Idempotente. Reaplicar tras `kanvas-board init` o una actualizacion de Kanvas:
    python scripts/kanvas_docs_patch.py
El tablero parcheado se abre con `python .agents/skills/kanvas/kanvas.py serve` (no con uvx).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KDIR = os.path.join(ROOT, ".agents", "skills", "kanvas")
MARK = "hrv-flex docs patch"


def patch(path, groups):
    """Apply each (marker, edits) group whose marker is not in the file yet, in order."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    todo = [(m, e) for m, e in groups if m not in text]
    if not todo:
        print(f"ya parcheado: {os.path.relpath(path, ROOT)}")
        return
    for _, edits in todo:
        for old, new in edits:
            if text.count(old) != 1:
                sys.exit(f"No encuentro (o no es unico) el punto de parche en {os.path.relpath(path, ROOT)}:\n{old[:200]}")
            text = text.replace(old, new, 1)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)
    print(f"parcheado: {os.path.relpath(path, ROOT)}")


PY_ROUTE_OLD = '''            return self._send(200, data, headers={"ETag": tag})
        return self._error(404, "Not found")
'''
PY_ROUTE_NEW = '''            return self._send(200, data, headers={"ETag": tag})
        if rest == ["api", "doc"]:
            return self._doc(path)
        return self._error(404, "Not found")

    def _doc(self, board_file):
        """# hrv-flex docs patch: serves a .md from the project's docs/ folder, read only, by [[name]] or path."""
        from urllib.parse import parse_qs
        name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0].strip().replace("\\\\", "/")
        if not name or len(name) > 300:
            return self._error(400, "Missing doc name")
        root = os.path.dirname(os.path.abspath(board_file))
        docs = os.path.realpath(os.path.join(root, "docs"))
        stem = name[:-3] if name.lower().endswith(".md") else name
        inside = lambda p: p.startswith(docs + os.sep) and p.lower().endswith(".md") and os.path.isfile(p)
        found = []
        if "/" in stem:
            p = os.path.realpath(os.path.join(root, stem + ".md"))
            if inside(p):
                found = [p]
        if not found:
            want = os.path.basename(stem).lower()
            for d, _, files in os.walk(docs):
                found += [os.path.join(d, f) for f in files if f.lower().endswith(".md") and f[:-3].lower() == want]
            found = [p for p in (os.path.realpath(p) for p in found) if inside(p)]
        rels = sorted(os.path.relpath(p, root).replace(os.sep, "/") for p in found)
        if not found:
            return self._error(404, f"No .md called {name} in docs/")
        if len(found) > 1:
            return self._error(409, "Several docs match: " + ", ".join(rels))
        if os.path.getsize(found[0]) > 4_000_000:
            return self._error(413, "Doc too large")
        with open(found[0], encoding="utf-8", errors="replace") as f:
            text = f.read()
        body = json.dumps({"path": rels[0], "text": text}, ensure_ascii=False).encode("utf-8")
        return self._send(200, body)
'''

JS_RE_OLD = '''  const re = /`([^`]+)`|(!?\\[)|(https?:'''
JS_RE_NEW = '''  // hrv-flex docs patch: [[name]] and [[name|alias]] open the doc from docs/ in a new tab.
  const re = /\\[\\[([^\\]\\n]+)\\]\\]|`([^`]+)`|(!?\\[)|(https?:'''
JS_LOOP_OLD = '''    if (m[2] && close < open) {'''
JS_LOOP_NEW = '''    if (m[3] && close < open) {'''
JS_BODY_OLD = '''    if (m[2] && !target) { re.lastIndex = m.index + 1; continue; }
    out += fmt(src.slice(last, m.index));
    if (m[1] != null) out += `<code>${escHtml(m[1])}</code>`;
    else if (m[2]) { out += link(target[1], src.slice(open + 1, close)); re.lastIndex = close + target[0].length; }
    else out += anchor(m[3], escHtml(m[3]));'''
JS_BODY_NEW = '''    if (m[3] && !target) { re.lastIndex = m.index + 1; continue; }
    out += fmt(src.slice(last, m.index));
    if (m[1] != null) {
      const [ref, alias] = m[1].split("|"), name = ref.split("#")[0].trim();
      const label = (alias || name.split("/").pop()).trim();
      out += name ? `<a class="doclink" href="?doc=${encodeURIComponent(name)}" target="_blank" rel="noopener">${escHtml(label)}</a>` : escHtml(m[0]);
    }
    else if (m[2] != null) out += `<code>${escHtml(m[2])}</code>`;
    else if (m[3]) { out += link(target[1], src.slice(open + 1, close)); re.lastIndex = close + target[0].length; }
    else out += anchor(m[4], escHtml(m[4]));'''
JS_BOOT_OLD = '''async function boot() {
  setupChrome();'''
JS_BOOT_NEW = '''// hrv-flex docs patch: ?doc=<name> shows that .md from docs/ instead of the board.
async function showDoc(name) {
  applyTheme();
  document.title = name.split("/").pop();
  document.body.innerHTML = "";
  document.body.classList.add("doc-mode");
  const main = document.createElement("main");
  main.className = "md doc-page";
  main.textContent = "Cargando…";
  document.body.append(main);
  try {
    const r = await fetch(`api/doc?name=${encodeURIComponent(name)}`, { cache: "no-store" });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    main.innerHTML = `<p class="doc-path"><code>${escHtml(data.path)}</code></p>` + markdown(data.text);
  } catch (e) {
    main.innerHTML = `<p><strong>No se pudo abrir ${escHtml(name)}</strong></p><p>${escHtml(e.message || String(e))}</p>`;
  }
}

async function boot() {
  const docName = new URLSearchParams(location.search).get("doc");
  if (docName && location.protocol.startsWith("http")) return showDoc(docName);
  setupChrome();'''
CSS_OLD = '''.md a { color: var(--accent); }'''
CSS_NEW = '''.md a { color: var(--accent); }
/* hrv-flex docs patch */
.md a.doclink { text-decoration: underline dotted; }
body.doc-mode { display: block; overflow: auto; height: auto; }
.doc-page { max-width: 860px; margin: 24px auto 64px; padding: 0 16px; font-size: 15px; line-height: 1.6; }
.doc-page h1, .doc-page h2 { margin: 18px 0 8px; line-height: 1.25; }
.doc-page .doc-path { color: var(--muted); }'''


# v2: plain paths docs/....md in text and markdown links [x](docs/...md) also open the doc.
MARK2 = "hrv-flex docs patch v2"
JS2_RE_OLD = r'''(?:[^\s<>().,;:!?'"]|\((?:[^\s<>()]|\([^\s<>()]*\))*\)))/g;'''
JS2_RE_NEW = r'''(?:[^\s<>().,;:!?'"]|\((?:[^\s<>()]|\([^\s<>()]*\))*\)))|(docs\/[^\n`\[\]()<>|]*?\.md)(?!\w)/g;'''
JS2_HELPER_OLD = '''  const anchor = (href, html) => `<a href="${escHtml(href)}" target="_blank" rel="noopener noreferrer">${html}</a>`;'''
JS2_HELPER_NEW = JS2_HELPER_OLD + '''
  // hrv-flex docs patch v2: a relative link to a .md, or a plain docs/....md path, opens the doc too.
  const docLink = (name, html) => `<a class="doclink" href="?doc=${encodeURIComponent(name)}" target="_blank" rel="noopener">${html}</a>`;'''
JS2_LINK_OLD = '''    return ok ? anchor(href, html) : html;'''
JS2_LINK_NEW = '''    // Relative paths, and absolute ones (C:/.../docs/HRV/x.md, file:///...) cut back to docs/... or the bare name.
    if (!ok && /\\.md$/i.test(href) && (/^[^:]+$/.test(href) || /^([A-Za-z]:[\\\\/]|file:)/i.test(href))) {
      let n = href;
      try { n = decodeURIComponent(href); } catch (e) {}
      n = n.replace(/\\\\/g, "/");
      if (/^([A-Za-z]:|file:)/i.test(n)) {
        const at = n.toLowerCase().lastIndexOf("/docs/");
        n = at >= 0 ? n.slice(at + 1) : n.split("/").pop();
      }
      return docLink(n.replace(/^\\.?\\//, ""), text ? fmt(text, false) : escHtml(n));
    }
    return ok ? anchor(href, html) : html;'''
JS2_BODY_OLD = '''    else out += anchor(m[4], escHtml(m[4]));'''
JS2_BODY_NEW = '''    else if (m[5]) out += docLink(m[5], escHtml(m[5]));
    else out += anchor(m[4], escHtml(m[4]));'''


# v3: readable typography for whole documents. Kanvas renders "#" as h3 and sizes h3-h6 like body text,
# which suits short card descriptions but flattens a long document.
MARK3 = "hrv-flex docs patch v3"
CSS3_OLD = '''.doc-page .doc-path { color: var(--muted); }'''
CSS3_NEW = CSS3_OLD + '''
/* hrv-flex docs patch v3 */
.md.doc-page { display: block; flex: none; position: static; min-height: auto; max-width: 980px; font-size: 15.5px; line-height: 1.65; }
.md.doc-page p, .md.doc-page li, .md.doc-page blockquote { font-size: inherit; }
.md.doc-page h3, .md.doc-page h4, .md.doc-page h5, .md.doc-page h6 { line-height: 1.3; font-weight: 650; }
.md.doc-page h3 { font-size: 28px; margin: 8px 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.md.doc-page h4 { font-size: 21px; margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.md.doc-page h5 { font-size: 17px; margin: 24px 0 8px; }
.md.doc-page h6 { font-size: 15.5px; margin: 20px 0 6px; color: var(--muted); }
.md.doc-page p, .md.doc-page ul, .md.doc-page ol, .md.doc-page pre, .md.doc-page blockquote { margin: 0 0 14px; }
.md.doc-page ul, .md.doc-page ol { padding-left: 26px; }
.md.doc-page li { margin: 4px 0; }
.md.doc-page li > ul, .md.doc-page li > ol { margin: 4px 0; }
.md.doc-page code { font-size: 13px; padding: 1px 5px; }
.md.doc-page pre { padding: 12px 14px; font-size: 13px; line-height: 1.5; }
.md.doc-page :where(.table) { margin: 0 0 18px; border: 1px solid var(--border); border-radius: 8px; }
.md.doc-page table { width: 100%; font-size: 14px; line-height: 1.5; border: 0; }
.md.doc-page th, .md.doc-page td { padding: 8px 12px; border: 0; border-bottom: 1px solid var(--border); min-width: 120px; }
.md.doc-page tr:last-child td { border-bottom: 0; }
.md.doc-page th { position: sticky; top: 0; }
.md.doc-page tbody tr:nth-child(even) td { background: color-mix(in srgb, var(--surface-2) 55%, transparent); }
.md.doc-page blockquote { padding: 6px 14px; background: var(--surface-2); border-radius: 0 6px 6px 0; }
.md.doc-page hr { margin: 28px 0; }
.md.doc-page .doc-path { font-size: 13px; margin-bottom: 18px; }
@media (max-width: 640px) { .md.doc-page { font-size: 15px; } .md.doc-page h3 { font-size: 23px; } .md.doc-page h4 { font-size: 19px; } }'''


# v4: markdown links with an angle-bracket destination, [x](<file with spaces.md>), as the docs use them.
MARK4 = "hrv-flex docs patch v4"
JS4_DEST_OLD = r'''  const dest = /\]\(((?:[^()\s]|\((?:[^()\s]|\([^()\s]*\))*\))+)\)/y;'''
JS4_DEST_NEW = r'''  // hrv-flex docs patch v4: also [x](<dest with spaces>).
  const dest = /\]\((?:<([^<>\n]+)>|((?:[^()\s]|\((?:[^()\s]|\([^()\s]*\))*\))+))\)/y;'''
JS4_USE_OLD = '''out += link(target[1], src.slice(open + 1, close));'''
JS4_USE_NEW = '''out += link(target[1] ?? target[2], src.slice(open + 1, close));'''


# v5: inside a doc, relative links (../contracts/x.md) resolve against that doc's folder.
MARK5 = "hrv-flex docs patch v5"
JS5_OLD = '''    main.innerHTML = `<p class="doc-path"><code>${escHtml(data.path)}</code></p>` + markdown(data.text);'''
JS5_NEW = JS5_OLD + '''
    // hrv-flex docs patch v5: resolve ../ and ./ links against the folder of this doc.
    const base = data.path.split("/").slice(0, -1);
    for (const a of main.querySelectorAll("a.doclink")) {
      const n = new URLSearchParams(a.search).get("doc") || "";
      if (!/^\\.\\.?\\//.test(n)) continue;
      const parts = [...base];
      for (const seg of n.split("/")) { if (seg === "..") parts.pop(); else if (seg && seg !== ".") parts.push(seg); }
      a.href = `?doc=${encodeURIComponent(parts.join("/"))}`;
    }'''


# v6: the viewer also serves research/reports/ (never research/archive/ or anything else).
MARK6 = "hrv-flex docs patch v6"
PY6_BASES_OLD = '''        docs = os.path.realpath(os.path.join(root, "docs"))'''
PY6_BASES_NEW = '''        # hrv-flex docs patch v6: docs/ plus research/reports/ only.
        bases = [os.path.realpath(os.path.join(root, *s.split("/"))) for s in ("docs", "research/reports")]'''
PY6_INSIDE_OLD = '''        inside = lambda p: p.startswith(docs + os.sep) and p.lower().endswith(".md") and os.path.isfile(p)'''
PY6_INSIDE_NEW = '''        inside = lambda p: (any(p.startswith(b + os.sep) for b in bases)
                            and p.lower().endswith(".md") and os.path.isfile(p))'''
PY6_WALK_OLD = '''            for d, _, files in os.walk(docs):'''
PY6_WALK_NEW = '''            for d, _, files in (w for b in bases for w in os.walk(b)):'''
PY6_MSG_OLD = '''f"No .md called {name} in docs/"'''
PY6_MSG_NEW = '''f"No .md called {name} in docs/ or research/reports/"'''
JS6_OLD = r'''|(docs\/[^\n`\[\]()<>|]*?\.md)(?!\w)/g;'''
JS6_NEW = r'''|((?:docs|research\/reports)\/[^\n`\[\]()<>|]*?\.md)(?!\w)/g; // hrv-flex docs patch v6'''


def main():
    patch(os.path.join(KDIR, "kanvas.py"), [
        (MARK, [(PY_ROUTE_OLD, PY_ROUTE_NEW)]),
        (MARK6, [(PY6_BASES_OLD, PY6_BASES_NEW), (PY6_INSIDE_OLD, PY6_INSIDE_NEW),
                 (PY6_WALK_OLD, PY6_WALK_NEW), (PY6_MSG_OLD, PY6_MSG_NEW)]),
    ])
    patch(os.path.join(KDIR, "kanvas.html"), [
        (MARK, [(JS_RE_OLD, JS_RE_NEW), (JS_LOOP_OLD, JS_LOOP_NEW), (JS_BODY_OLD, JS_BODY_NEW),
                (JS_BOOT_OLD, JS_BOOT_NEW), (CSS_OLD, CSS_NEW)]),
        (MARK2, [(JS2_RE_OLD, JS2_RE_NEW), (JS2_HELPER_OLD, JS2_HELPER_NEW),
                 (JS2_LINK_OLD, JS2_LINK_NEW), (JS2_BODY_OLD, JS2_BODY_NEW)]),
        (MARK3, [(CSS3_OLD, CSS3_NEW)]),
        (MARK4, [(JS4_DEST_OLD, JS4_DEST_NEW), (JS4_USE_OLD, JS4_USE_NEW)]),
        (MARK5, [(JS5_OLD, JS5_NEW)]),
        (MARK6, [(JS6_OLD, JS6_NEW)]),
    ])


if __name__ == "__main__":
    main()
