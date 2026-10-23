#!/usr/bin/env node
// Batch EPUB CFI generator for the WeChat-Reading annotation import pipeline
// (see plan/WeChatReading_Annotation_Import_Plan.md §4.2/§4.3).
//
// Invoked as ONE child process per book (never per annotation) by
// webserver/services/cfi_gen/launcher.py. Reads a single JSON request from
// stdin, writes a single JSON response to stdout, and does nothing else —
// no network, no writes back to the epub, no persistence.
//
// CFI generation/serialization is delegated entirely to the vendored
// `third-party/foliate-js/epubcfi.js` (git submodule, upstream
// johnfactotum/foliate-js) — this is the exact module MyReader's own
// `foliate-js`-based renderer uses to resolve `cfi` back to a DOM Range
// (see view.js `getCFI()`/`resolveCFI()`). We deliberately do not
// reimplement any part of the CFI spec here.
//
// Request shape (stdin):
//   {
//     "epubPath": "/abs/path/to/book.epub",
//     "onAmbiguous": "error" | "first_match",
//     "anchors": [
//       { "id": "wxread-123", "chapterHint": "第三章", "text": "..." },
//       { "id": "wxread-review-456", "chapterHint": "第三章" }   // no `text` -> chapter-start bookmark
//     ]
//   }
//
// Response shape (stdout), same length/order as `anchors`:
//   {
//     "results": [
//       { "id": "wxread-123", "status": "ok", "cfi": "epubcfi(...)", "matchCount": 1 },
//       { "id": "wxread-124", "status": "ambiguous", "matchCount": 3 },
//       { "id": "wxread-125", "status": "no_match" },
//       { "id": "wxread-review-456", "status": "ok", "cfi": "epubcfi(...)", "degraded": "chapter_start" },
//       { "id": "wxread-126", "status": "error", "error": "..." }
//     ],
//     "meta": { "spineCount": 24, "sectionParseErrors": 0 }
//   }
//
// Fatal, whole-book errors (can't open the zip, no OPF, etc.) are written as
// a single-line JSON `{ "error": "..." }` to stderr and the process exits
// non-zero — the Python launcher must treat that as "this whole book
// failed", never as "every anchor was a no_match" (see §4.3 边界与安全).

import { readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, join, posix } from 'node:path'
import { unzipSync, strFromU8 } from 'fflate'
import { JSDOM } from 'jsdom'

// ─── path resolution: relative to this file, never hardcoded/CWD-based ────
// See plan §4.3 "路径解析" — this must resolve identically in a local
// checkout (webserver/services/cfi_gen/cfi_batch.mjs) and in the Docker
// image (/var/www/mybooks/webserver/services/cfi_gen/cfi_batch.mjs), as
// long as `third-party/foliate-js/` stays a sibling of `webserver/` in both
// places (see Dockerfile `COPY third-party/foliate-js/ ...`).
const __dirname = dirname(fileURLToPath(import.meta.url))
const EPUBCFI_PATH = join(__dirname, '..', '..', '..', 'third-party', 'foliate-js', 'epubcfi.js')
const CFI = await import(pathToFileURL(EPUBCFI_PATH).href)

const MAX_ANCHORS = 2000

// One shared jsdom window just to get a real DOMParser implementation from;
// the Document objects it produces (one per XHTML/XML file we parse) are
// otherwise independent and unrelated to each other.
const { window: parserWindow } = new JSDOM('')
const DOMParser = parserWindow.DOMParser

async function readStdin() {
  const chunks = []
  for await (const chunk of process.stdin) chunks.push(chunk)
  return Buffer.concat(chunks).toString('utf-8')
}

function fail(message) {
  process.stderr.write(JSON.stringify({ error: message }) + '\n')
  process.exit(1)
}

// ─── zip / OPF / spine ──────────────────────────────────────────────────

function unzipEpub(epubPath) {
  const bytes = readFileSync(epubPath)
  return unzipSync(bytes) // { [path]: Uint8Array }
}

function resolvePath(baseDir, href) {
  // hrefs in OPF/NCX/nav are relative to the file that references them and
  // may be percent-encoded; zip entry names are plain POSIX paths.
  const clean = decodeURIComponent(href.split('#')[0])
  return posix.normalize(posix.join(baseDir, clean)).replace(/^\/+/, '')
}

function findZipEntry(files, path) {
  if (files[path]) return files[path]
  // some tools zip with a leading "./" or inconsistent slashes; try a
  // case-sensitive suffix match as a last resort before giving up.
  const normalized = path.replace(/^\.\//, '')
  return files[normalized] ?? null
}

function parseXml(text) {
  return new DOMParser().parseFromString(text, 'application/xml')
}

// Loads container.xml -> OPF -> spine, mirroring what foliate-js's own
// epub.js loader does (including reusing CFI.fromElements() for the base
// per-section CFIs — see plan §4.3).
function loadPackage(files) {
  const containerText = strFromU8(findZipEntry(files, 'META-INF/container.xml') ?? fail('missing META-INF/container.xml'))
  const containerDoc = parseXml(containerText)
  const rootfileEl = containerDoc.getElementsByTagName('rootfile')[0]
  const opfPath = rootfileEl?.getAttribute('full-path')
  if (!opfPath) fail('container.xml has no <rootfile full-path>')

  const opfText = strFromU8(findZipEntry(files, opfPath) ?? fail(`missing OPF at ${opfPath}`))
  const opfDoc = parseXml(opfText)
  const opfDir = posix.dirname(opfPath)

  const manifestById = new Map()
  for (const item of Array.from(opfDoc.getElementsByTagName('item'))) {
    manifestById.set(item.getAttribute('id'), {
      href: item.getAttribute('href'),
      mediaType: item.getAttribute('media-type'),
      properties: item.getAttribute('properties') ?? '',
    })
  }

  const itemrefEls = Array.from(opfDoc.getElementsByTagName('itemref'))
  if (!itemrefEls.length) fail('OPF <spine> has no <itemref> entries')

  // The exact same function MyReader's epub.js loader uses to compute the
  // base (spine-level) CFI for each section — not reimplemented here.
  const baseCfis = CFI.fromElements(itemrefEls)

  const spine = itemrefEls.map((el, index) => {
    const idref = el.getAttribute('idref')
    const item = manifestById.get(idref)
    return {
      index,
      idref,
      href: item?.href,
      zipPath: item?.href ? resolvePath(opfDir, item.href) : null,
      baseCfi: baseCfis[index],
    }
  }).filter(s => s.zipPath)

  // Chapter titles for the "no text anchor -> chapter start" fallback
  // (§4.5). Best-effort: NCX only for now (covers EPUB2 and most EPUB3
  // books that still ship one for back-compat); EPUB3 nav.xhtml-only books
  // fall back to no title match, which just means those anchors end up
  // `no_match` instead of a degraded chapter bookmark — acceptable for the
  // first cut, see plan §7 known limitations.
  const ncxItem = Array.from(manifestById.values()).find(i => i.mediaType === 'application/x-dtbncx+xml')
  const chapterTitleByHref = new Map()
  if (ncxItem) {
    try {
      const ncxPath = resolvePath(opfDir, ncxItem.href)
      const ncxText = strFromU8(findZipEntry(files, ncxPath))
      const ncxDoc = parseXml(ncxText)
      for (const navPoint of Array.from(ncxDoc.getElementsByTagName('navPoint'))) {
        const label = navPoint.getElementsByTagName('text')[0]?.textContent?.trim()
        const src = navPoint.getElementsByTagName('content')[0]?.getAttribute('src')
        if (!label || !src) continue
        const href = resolvePath(ncxPath.split('/').slice(0, -1).join('/'), src)
        if (!chapterTitleByHref.has(href)) chapterTitleByHref.set(href, label)
      }
    } catch {
      // NCX present but unparsable — degrade silently, chapter-hint
      // matching just won't have any candidates.
    }
  }

  return { files, opfDir, spine, chapterTitleByHref }
}

// ─── per-section text index (search + CFI generation share this) ─────────
//
// Both the full-text search AND the CFI generation walk the *same* parsed
// DOM for a section — this is the whole point of doing it in one process
// (see plan §4.3): there is no separate "Python extracts text, Node
// generates CFI" step where the two could silently disagree about node
// boundaries/whitespace handling.

const SKIP_TAGS = new Set(['script', 'style'])
// Block-level elements imply a line break when rendered — two text nodes on
// either side of one must NOT be concatenated with zero separator, or
// "...异。</p><p>骄阳..." (real EPUB markup, no literal whitespace text node
// between the tags) would search as "...异。骄阳..." with the two sentences
// fused, and any anchor that spans the paragraph break (which visually reads
// as a break, not a fused run of characters) could never match. This was
// found via tests/test_cfi_gen.py, not assumed.
//
// `<br>` is deliberately EXCLUDED here, even though HTML also renders it as
// a line break: real-world (esp. Calibre-converted) Chinese EPUBs commonly
// hard-wrap every *printed line* with `<br class="calibre1"/>` mid-sentence
// — "从一座农舍走到另<br/>一座农舍" is one continuous clause, not two. CJK
// text has no inter-word spaces, so inserting one at every such wrap would
// fuse-with-a-gap what should read as one unbroken run and break matching
// for any anchor spanning that (very common) wrap point. This was also
// found via tests/test_cfi_gen.py — see the "老人与海"/"百年孤独" fixtures.
// The trade-off: a `<br>` used for a genuine content break (e.g. between
// poem lines) won't get a separator either, so text search there can
// under-match; no per-language BLOCK_TAGS vs `<br>` heuristic tried so far
// covers both cases at once, and losing a poem-line separator is the lesser
// failure mode against this codebase's actual library (see plan §7).
const BLOCK_TAGS = new Set([
  'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
  'tr', 'td', 'th', 'table', 'thead', 'tbody', 'tfoot', 'section', 'article',
  'header', 'footer', 'ul', 'ol', 'figure', 'figcaption', 'dt', 'dd', 'pre', 'address',
])

// Collects text nodes in document order, each tagged with `breakBefore: true`
// if a block-level boundary was crossed since the previous text node — the
// caller turns that into a single inserted space.
function collectTextNodes(root, out) {
  const state = { pendingBreak: false }
  walkForText(root, out, state)
}

function walkForText(node, out, state) {
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === 1) { // ELEMENT_NODE
      const tag = child.tagName?.toLowerCase()
      if (SKIP_TAGS.has(tag) || tag === 'br') continue
      const isBlock = BLOCK_TAGS.has(tag)
      if (isBlock && out.length) state.pendingBreak = true // entering a new block after we've already seen text
      walkForText(child, out, state)
      if (isBlock) state.pendingBreak = true // leaving a block, so whatever comes next starts on a new "line" too
    } else if (child.nodeType === 3 || child.nodeType === 4) { // TEXT_NODE / CDATA
      if (child.nodeValue) {
        out.push({ node: child, breakBefore: state.pendingBreak })
        state.pendingBreak = false
      }
    }
  }
}

// Collapses runs of whitespace to a single space and records, for every
// character of the normalized string, which raw-text index it came from —
// so a normalized-text match can be mapped back to an exact (node, offset).
function normalizeWithMap(raw) {
  let norm = ''
  const normToRaw = []
  let i = 0
  const n = raw.length
  while (i < n) {
    if (/\s/.test(raw[i])) {
      const runStart = i
      while (i < n && /\s/.test(raw[i])) i++
      norm += ' '
      normToRaw.push(runStart)
    } else {
      norm += raw[i]
      normToRaw.push(i)
      i++
    }
  }
  return { norm, normToRaw }
}

function parseSectionDoc(files, zipPath) {
  const bytes = findZipEntry(files, zipPath)
  if (!bytes) throw new Error(`spine item not found in zip: ${zipPath}`)
  const text = strFromU8(bytes)
  let doc = new DOMParser().parseFromString(text, 'application/xhtml+xml')
  if (doc.getElementsByTagName('parsererror').length) {
    // Malformed XHTML is common in the wild; fall back to lenient HTML
    // parsing rather than failing the whole section.
    doc = new DOMParser().parseFromString(text, 'text/html')
  }
  return doc
}

function buildSectionIndex(doc) {
  const root = doc.body ?? doc.documentElement
  const textNodes = []
  collectTextNodes(root, textNodes)

  let raw = ''
  const intervals = [] // {start, end, node}, end exclusive, contiguous
  for (const { node, breakBefore } of textNodes) {
    const value = node.nodeValue ?? ''
    if (!value) continue
    // Insert the implicit block-boundary/<br> separator here. It's not part
    // of any node's actual content, so we attribute it to this node's own
    // start (offset 0) — a match that happens to begin exactly on this
    // synthetic character will land on the first real character of `node`
    // instead, which is an acceptable simplification (see BLOCK_TAGS comment).
    if (breakBefore && raw.length > 0 && !/\s$/.test(raw)) raw += ' '
    const start = raw.length
    raw += value
    intervals.push({ start, end: raw.length, node })
  }
  const { norm, normToRaw } = normalizeWithMap(raw)
  return { doc, intervals, raw, norm, normToRaw }
}

// `intervals` do NOT perfectly tile `raw` — inserted block-boundary spaces
// (buildSectionIndex) sit in a 1-character gap between two intervals that
// belongs to neither node. An index landing in such a gap (or exactly on an
// interval's end, the same position numerically) snaps forward to offset 0
// of the *next* interval's node — i.e. a match boundary that lands on a
// paragraph break resolves to "start of the next paragraph", which is a
// reasonable, unsurprising place for a CFI to point.
function rawIndexToNodeOffset(intervals, idx) {
  if (!intervals.length) return null
  if (idx <= 0) return { node: intervals[0].node, offset: 0 }
  const last = intervals[intervals.length - 1]
  if (idx >= last.end) return { node: last.node, offset: last.end - last.start }
  for (const iv of intervals) {
    if (idx >= iv.start && idx < iv.end) return { node: iv.node, offset: idx - iv.start }
  }
  // idx falls in a gap (or exactly on some iv.end): find the next interval
  // that starts at or after idx and snap to its beginning.
  for (const iv of intervals) {
    if (iv.start >= idx) return { node: iv.node, offset: 0 }
  }
  return { node: last.node, offset: last.end - last.start }
}

function normalizeAnchorText(text) {
  return normalizeWithMap(text.trim()).norm
}

// Every occurrence of `needle` in `sectionIndex.norm`, mapped back to a raw
// [start, end) range in that section.
function findOccurrencesInSection(sectionIndex, needle) {
  const occurrences = []
  if (!needle) return occurrences
  let from = 0
  while (true) {
    const at = sectionIndex.norm.indexOf(needle, from)
    if (at === -1) break
    const normStart = at
    const normEnd = at + needle.length
    const rawStart = sectionIndex.normToRaw[normStart]
    const rawEnd = normEnd < sectionIndex.normToRaw.length
      ? sectionIndex.normToRaw[normEnd]
      : sectionIndex.raw.length
    occurrences.push({ rawStart, rawEnd })
    from = at + 1 // allow overlapping matches; duplicates are rare and harmless (still counted for ambiguity)
  }
  return occurrences
}

function buildCfiForOccurrence(sectionIndex, baseCfi, occurrence) {
  const { doc, intervals } = sectionIndex
  const start = rawIndexToNodeOffset(intervals, occurrence.rawStart)
  const end = rawIndexToNodeOffset(intervals, occurrence.rawEnd)
  if (!start || !end) throw new Error('could not map match back to a DOM position')
  const range = doc.createRange()
  range.setStart(start.node, start.offset)
  range.setEnd(end.node, end.offset)
  const docCfi = CFI.fromRange(range)
  const fullCfi = CFI.joinIndir(baseCfi, docCfi)
  return { fullCfi, docCfi, range }
}

// Round-trip self-check: reparse the CFI string we just produced and
// re-resolve it against the *same* doc, then compare the resolved text to
// what we originally selected. This is the "layer 0" defence from plan §7 —
// if serialization/parsing don't agree, we must not silently hand back a
// broken cfi.
function verifyDocCfiRoundTrip(sectionIndex, docCfi, expectedText) {
  const parsed = CFI.parse(docCfi)
  const resolvedRange = CFI.toRange(sectionIndex.doc, parsed)
  if (!resolvedRange) return false
  return resolvedRange.toString() === expectedText
}

// ─── chapter-start fallback for anchors with no text (§4.5) ──────────────

function collapsedRangeAtSectionStart(doc) {
  const root = doc.body ?? doc.documentElement
  const range = doc.createRange()
  range.selectNodeContents(root)
  range.collapse(true)
  return range
}

function chapterStartCfi(sectionIndex, baseCfi) {
  const range = collapsedRangeAtSectionStart(sectionIndex.doc)
  const docCfi = CFI.fromRange(range)
  return CFI.joinIndir(baseCfi, docCfi)
}

// ─── main ──────────────────────────────────────────────────────────────

async function main() {
  let request
  try {
    request = JSON.parse(await readStdin())
  } catch (e) {
    fail(`invalid JSON request: ${e.message}`)
    return
  }

  const { epubPath, onAmbiguous = 'error', anchors = [], xpointers = [] } = request
  if (!epubPath) fail('missing epubPath')
  if (!Array.isArray(anchors) || !Array.isArray(xpointers)) fail('anchors/xpointers must be arrays')
  if (anchors.length === 0 && xpointers.length === 0) fail('anchors or xpointers must be a non-empty array')
  if (anchors.length + xpointers.length > MAX_ANCHORS) fail(`too many items: ${anchors.length + xpointers.length} > ${MAX_ANCHORS}`)
  if (onAmbiguous !== 'error' && onAmbiguous !== 'first_match') fail(`invalid onAmbiguous: ${onAmbiguous}`)

  let files, pkg
  try {
    files = unzipEpub(epubPath)
    pkg = loadPackage(files)
  } catch (e) {
    fail(`failed to open epub: ${e.message}`)
    return
  }

  // Parse every spine section once, lazily but memoized — later anchors
  // reuse an already-parsed section instead of re-parsing it.
  const sectionCache = new Map() // spine index -> sectionIndex | null (null = failed to parse)
  let sectionParseErrors = 0
  function getSectionIndex(spineIndex) {
    if (sectionCache.has(spineIndex)) return sectionCache.get(spineIndex)
    const item = pkg.spine[spineIndex]
    let result = null
    try {
      const doc = parseSectionDoc(pkg.files, item.zipPath)
      result = buildSectionIndex(doc)
    } catch (e) {
      sectionParseErrors++
      result = null
    }
    sectionCache.set(spineIndex, result)
    return result
  }

  const results = []
  for (const item of xpointers) {
    try {
      results.push(resolveXPointer(item.id, item.xpointer, pkg))
    } catch (e) {
      results.push({ id: item.id, status: 'error', error: e.message })
    }
  }
  for (const anchor of anchors) {
    const { id, text, chapterHint } = anchor
    try {
      if (text && text.trim()) {
        results.push(resolveTextAnchor(id, text, pkg, getSectionIndex, onAmbiguous))
      } else {
        results.push(resolveChapterAnchor(id, chapterHint, pkg, getSectionIndex))
      }
    } catch (e) {
      results.push({ id, status: 'error', error: e.message })
    }
  }

  process.stdout.write(JSON.stringify({
    results,
    meta: { spineCount: pkg.spine.length, sectionParseErrors },
  }))
}

function findTextNodeAtOffset(root, target) {
  const nodes = []
  const walk = node => {
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === 3) {
        if (child.nodeValue) nodes.push(child)
      } else if (child.nodeType === 1) {
        walk(child)
      }
    }
  }
  walk(root)
  let sum = 0
  for (const node of nodes) {
    const length = node.nodeValue.length
    if (sum + length >= target) return { node, offset: target - sum }
    sum += length
  }
  if (!nodes.length) return null
  const last = nodes[nodes.length - 1]
  return { node: last, offset: last.nodeValue.length }
}

function resolveXPointer(id, xpointer, pkg) {
  const match = /^\/body(?:\[\d+\])?\/DocFragment\[(\d+)\]\/body(?:\[\d+\])?(.*)$/.exec(xpointer ?? '')
  if (!match) throw new Error(`invalid xpointer: ${xpointer}`)
  const spineIndex = parseInt(match[1], 10) - 1
  const item = pkg.spine.find(s => s.index === spineIndex) ?? pkg.spine[spineIndex]
  if (!item) throw new Error(`spine index out of range: ${spineIndex}`)

  let rest = match[2]
  let textIndex = null
  let textOffset = null
  const textMatch = /\/text\(\)(?:\[(\d+)\])?\.(\d+)$/.exec(rest)
  if (textMatch) {
    textIndex = textMatch[1] ? parseInt(textMatch[1], 10) : null
    textOffset = parseInt(textMatch[2], 10)
    rest = rest.slice(0, textMatch.index)
  }

  const doc = parseSectionDoc(pkg.files, item.zipPath)
  let element = doc.body
  for (const segment of rest.split('/').filter(Boolean)) {
    const step = /^(\w+)(?:\[(\d+)\])?$/.exec(segment)
    if (!step) throw new Error(`invalid xpointer segment: ${segment}`)
    const tag = step[1].toLowerCase()
    const index = step[2] ? parseInt(step[2], 10) : 1
    const children = Array.from(element.children).filter(c => c.tagName.toLowerCase() === tag)
    if (index < 1 || index > children.length) throw new Error(`element not found: ${segment}`)
    element = children[index - 1]
  }

  let node = element
  let offset = 0
  if (textOffset !== null) {
    if (textIndex !== null) {
      const texts = Array.from(element.childNodes).filter(n => n.nodeType === 3)
      node = texts[textIndex - 1]
      if (!node) throw new Error(`text node not found: text()[${textIndex}]`)
      offset = Math.min(textOffset, node.nodeValue.length)
    } else {
      const found = findTextNodeAtOffset(element, textOffset)
      if (!found) throw new Error(`text offset not found: ${textOffset}`)
      node = found.node
      offset = found.offset
    }
  }

  const range = doc.createRange()
  range.setStart(node, offset)
  range.collapse(true)
  const cfi = CFI.joinIndir(item.baseCfi, CFI.fromRange(range))
  return { id, status: 'ok', cfi }
}

function resolveTextAnchor(id, text, pkg, getSectionIndex, onAmbiguous) {
  const needle = normalizeAnchorText(text)
  if (!needle) return { id, status: 'no_match' }

  const allOccurrences = [] // { spineIndex, occurrence }
  for (const item of pkg.spine) {
    const sectionIndex = getSectionIndex(item.index)
    if (!sectionIndex) continue
    for (const occurrence of findOccurrencesInSection(sectionIndex, needle)) {
      allOccurrences.push({ spineIndex: item.index, occurrence })
    }
  }

  if (allOccurrences.length === 0) return { id, status: 'no_match' }

  if (allOccurrences.length > 1 && onAmbiguous === 'error') {
    return { id, status: 'ambiguous', matchCount: allOccurrences.length }
  }

  // Unique match, or first_match policy: first in spine order (allOccurrences
  // is already built in spine order, and within a section indexOf scans
  // left-to-right, so [0] is the correct "first" pick either way).
  const picked = allOccurrences[0]
  const item = pkg.spine[picked.spineIndex]
  const sectionIndex = getSectionIndex(picked.spineIndex)
  const { fullCfi, docCfi, range } = buildCfiForOccurrence(sectionIndex, item.baseCfi, picked.occurrence)
  const expectedText = range.toString()
  const verified = verifyDocCfiRoundTrip(sectionIndex, docCfi, expectedText)
  if (!verified) return { id, status: 'error', error: 'cfi round-trip verification failed' }

  const result = { id, status: 'ok', cfi: fullCfi, matchCount: allOccurrences.length }
  if (allOccurrences.length > 1) result.ambiguousResolution = 'first_match'
  return result
}

function resolveChapterAnchor(id, chapterHint, pkg, getSectionIndex) {
  let target = null
  if (chapterHint) {
    const hint = chapterHint.trim()
    for (const item of pkg.spine) {
      const title = pkg.chapterTitleByHref.get(item.href)
      if (title && (title === hint || title.includes(hint) || hint.includes(title))) {
        target = item
        break
      }
    }
    if (!target) return { id, status: 'no_match' }
  } else {
    // No text, no chapter hint at all -> whole-book review, pin to the very
    // start of the book (see plan §4.5).
    target = pkg.spine[0]
  }

  const sectionIndex = getSectionIndex(target.index)
  if (!sectionIndex) return { id, status: 'error', error: `failed to parse section ${target.zipPath}` }

  const fullCfi = chapterStartCfi(sectionIndex, target.baseCfi)
  return { id, status: 'ok', cfi: fullCfi, degraded: 'chapter_start' }
}

main().catch(e => fail(e.stack ?? String(e)))
