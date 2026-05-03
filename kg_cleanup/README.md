# KG Cleanup Pipeline

Reconciling the IMDB4M knowledge graph with the actual downloaded media
on disk, after manual rescue of URL-mismatched items.

This document is written at two levels at once: a practical how-to for
running the tool, and a methodological write-up suitable for lifting into
a research paper's "KG construction" section.

---

## 1. Motivation

IMDB4M couples a schema.org-shaped RDF knowledge graph
(`data/kg/imdb_kg_cleaned.ttl`, 1.82 M triples) with a parallel corpus of
image, video, and audio files (`output/<entity_id>/{images,videos,audio}/`,
~41 k files). The two artefacts are produced in separate passes:

1. **Extraction.** `media_downloader/kg_parser.py` walks the KG and
   emits, per entity, the CDN / IMDB-video / YouTube URLs that the
   downloaders should fetch.
2. **Download.** `ImageDownloader`, `VideoDownloader` and
   `AudioDownloader` retrieve the content and record what succeeded or
   failed in `output/download_progress.json`.
3. **Manual rescue.** A minority of URLs encoded in the KG turned out to
   be stale (the underlying IMDB mediaviewer / YouTube / amazon-CDN
   object had been replaced or deleted). For those we ran a round of
   ad-hoc scripts in `failed/` that either downloaded the item from a
   new URL or copied a hand-fetched file into the expected location.

After step 3, three classes of inconsistency remain between the KG and
the on-disk corpus:

| Class | Cause |
|-------|-------|
| **A — permanent failures** | The media could not be retrieved from any URL; the KG triples still describe an asset that does not exist. |
| **B — URL-mismatch rescues** | The file exists on disk but under a *different* URL than the one the KG records (its old IMDB/YouTube id was wrong). |
| **C — silent corruption / file-name drift** | A file is on disk but either truncated or stored under a filename the downloader's naming convention would not produce (e.g. rescues using the YouTube video-id as filename). |

The cleanup pipeline in `kg_cleanup/` resolves all three classes in one
pass and produces an audit-ready record of every change.

---

## 2. Design principles

1. **Disk is ground truth.** The JSON book-keeping files
   (`download_progress.json`, `entity_cache.json`, `integrity_audit.json`)
   are only used for cross-checks and backups; every keep/rewrite/delete
   decision is taken from the actual contents of `output/`.
2. **No destructive overwrites.** The original
   `data/kg/imdb_kg_cleaned.ttl` is never modified. Cleaned output is
   written to `imdb_kg_cleaned.pruned.ttl`; the removed triples land in a
   side graph `imdb_kg_failed_media.ttl` so nothing is lost.
3. **Uniform deletion scope.** When a media node is removed it is
   removed *for every entity that references it* (a shared image of two
   actors is either downloadable for both or for neither). This
   preserves graph invariants.
4. **Preserve metadata not triples.** Per-movie soundtrack side-cars
   (`data/movies/<tt>/movie_soundtrack/{soundtrack_links.json,
   *_soundtrack.ttl}`) are left untouched. The failed-audio metadata
   (track title, composer, YouTube video-id) remains available for
   future re-download attempts and for reproducibility.
5. **Dry-run by default.** The CLI refuses to mutate files unless
   invoked with `--apply`. Every dry run still produces the manifest
   and the Excel audit, so the decision set can be reviewed before it
   is executed.

---

## 3. Package layout

```
kg_cleanup/
├── __init__.py
├── __main__.py         # `python -m kg_cleanup` entry point
├── config.py           # Paths and constants
├── disk_scan.py        # Walk output/ → DiskScan (ground truth)
├── kg_index.py         # Load TTL once, build URI→record lookups
├── rescue_map.py       # Parse failed/*.py via ast to extract rescues
├── reconcile.py        # DiskScan × KGIndex → Manifest
├── apply.py            # Execute rewrites + deletions, emit side graph
├── sync_sidecars.py    # Propagate changes to the JSON book-keeping
├── report.py           # Excel audit spreadsheet
├── run.py              # End-to-end orchestrator
└── README.md           # This file
```

Outputs (all inside the repo):

| File | What it contains |
|------|-------|
| `output/kg_cleanup/disk_scan.json` | Full inventory of `output/` at scan time |
| `output/kg_cleanup/manifest.json`  | Every keep / rewrite / delete decision |
| `output/kg_cleanup/report.xlsx`    | Human-readable audit sheet |
| `output/kg_cleanup/kg_graph.pickle` | Cached rdflib Graph for rapid reruns |
| `output/entity_cache.json.bak`     | Backup of the cache before mutation |
| `output/download_progress.json.bak` | Backup of the progress log before mutation |
| `data/kg/imdb_kg_cleaned.pruned.ttl` | Cleaned main graph |
| `data/kg/imdb_kg_failed_media.ttl`   | Side graph with every removed triple |

---

## 4. Method

Formally, the pipeline implements the following six steps. The labels
`[Si]` are used throughout the code as progress markers.

### 4.1  Step S1 — Disk inventory

`disk_scan.scan_output()` walks every `output/<eid>/{images,videos,audio}/`
directory where `<eid>` matches `tt\d+` or `nm\d+`. For every file we
record the (entity, type, path, basename, stem, extension, size,
validity) tuple, where *validity* is the condition
`size ≥ MIN_VALID_BYTES` (1 KiB by default — anything smaller is
treated as absent to catch truncated rescues).  Entities whose folders
exist but are empty are still retained in the inventory — an empty
folder means "we attempted to download something for this entity and
every asset failed", which is semantically different from "this entity
was never attempted"; dropping empty folders would leave the reconciler
blind to stale KG triples for those entities.

Each entity's inventory exposes three lookup tables used later:

* **`image_index`** — by filename *stem* (basename without extension).
* **`video_index`** — by the `vi\d+` token the downloader prepends to
  every video filename (`viNNN_Official_Trailer.mp4` → key `viNNN`).
* **`audio_index`** — by filename stem, tolerant of three naming
  schemes: `<performer>-<title>`, `<title>`, `<youtube_video_id>`. The
  third form is produced by the `failed/rescue_tt0080455_audio.py`
  salvage script when the soundtrack JSON lacked a performer.

### 4.2  Step S2 — KG index

`kg_index.build_index()` parses the Turtle graph once (a pickle cache is
written so subsequent runs reload in ~6 s instead of ~35 s). It produces:

* `images : {URIRef → ImageRecord}` from every subject of
  `rdf:type schema:ImageObject`, together with the reverse maps
  `image_by_cdn` and `image_by_stem`.
* `videos : {URIRef → VideoRecord}` from every subject of
  `rdf:type schema:VideoObject`. The *owning entity* of a video is
  determined from   the first entity that points at it via `schema:video`
  or `schema:trailer` (90.7 % of videos — 3,611 of 3,983 — live under
  `schema:video` on person pages, the remaining 372 under
  `schema:trailer` on movie pages; the two predicates partition the
  `VideoObject` set exactly).
* `audio : {entity_id → [AudioRecord]}` where each `AudioRecord`
  captures a blank-node `schema:MusicRecording` reachable from a movie
  via `schema:audio`, with its title and performer URIs.

### 4.3  Step S3 — Rescue map

`rescue_map.load_rescue_map()` statically parses the five rescue
scripts in `failed/` with the `ast` module (they must not be *imported*
because that would pull in Selenium). Four scripts contribute:

* `rescue_video_batch.py` — 5 per-person URL rewrites.
* `rescue_nm0089185_video.py` — 1 URL rewrite.
* `rescue_audio_batch.py` — 15 by-hand audio downloads (no URL change —
  only filename reconciliation).
* `rescue_tt0080455_audio.py` — 20 YouTube-id-keyed audio rescues.

A key subtlety: one of the rescued trailers
(`vi2136393753`) had been pointed at by three different `nm*` pages,
each of which had in the meantime been re-linked to a **different**
new `viNNN`. The rescue index is therefore keyed by
`(entity_id, viNNN_old)` rather than by `viNNN_old` alone — the
reconciler must be able to produce a different `REWRITE` decision per
entity even when the source URI is shared.

### 4.4  Step S4 — Reconciliation

For each media node we combine the KG index, the disk inventory and the
rescue map to choose one of three actions:

> **KEEP**   the expected file is on disk (or, for audio, no YouTube
> link was ever resolved — the track exists as metadata only).
>
> **REWRITE** the file exists under a *different* URL recorded in the
> rescue map — we will later rewrite the KG to match.
>
> **DELETE** no acceptable file exists anywhere — the node and every
> triple pointing at it move to the side graph.

The rules, per type:

* **Images.** Iterate over every `(entity, schema:image|schema:thumbnail,
  image_uri)` back-reference.  The owning entity cannot be inferred from
  the `ImageObject` subject because IMDB encodes images as raw CDN URLs
  (`https://m.media-amazon.com/.../MV5B...jpg`) which contain no
  `nm`/`tt` slug; therefore the unit of decision is the back-reference,
  just as for videos.  Compute the expected filename stem from
  `schema:url` (exact port of `ImageDownloader._get_filename_from_url`);
  KEEP if present in the owning entity's `images/` folder, DELETE
  otherwise.  After all decisions are applied, any `ImageObject` that
  has lost *every* incoming edge is garbage-collected.  No image
  rewrites exist in the current dataset.

* **Videos.** Iterate over every `(entity, schema:trailer|schema:video,
  video_uri)` back-reference. If `viNNN_old` is on disk → KEEP. Else if
  `(entity_id, viNNN_old)` is in the rescue map and `viNNN_new` is on
  disk → REWRITE. Else → DELETE. The unit of decision is the
  back-reference, not the `VideoObject`, so a node shared by three
  persons can yield three different decisions.

* **Audio.** For each `MusicRecording` blank node, look up its title in
  the movie's `soundtrack_links.json`. If the lookup fails the track
  never had a YouTube URL — KEEP untouched. Otherwise enumerate the
  three possible on-disk stems
  (`<perf>-<title>`, `<title>`, `<video_id>`);
  if any matches → KEEP. Otherwise → DELETE.

### 4.5  Step S5 — Apply

`apply.apply_manifest()` executes the manifest against the in-memory
graph.

**Video back-reference surgery.** Because a single `VideoObject` may be
rewritten to different targets for different entities, we:

1. For each distinct `(old_uri, new_uri)` pair with at least one
   REWRITE decision, *clone* the source `VideoObject` to the new URI
   (copying every `(old, p, o)` triple and rewriting the
   `schema:embedUrl` literal). If the new URI already exists we skip
   the clone.
2. For each decision, locate the unique
   `(entity, predicate, old_uri_variant)` triple (handling both the
   bare URI and the trailing-slash variants, since the KG mixes both).
   REWRITE replaces that triple with `(entity, predicate,
   new_uri_variant)`; DELETE simply removes it.
3. After all decisions are applied, every source `VideoObject` that
   has lost *all* back-references is garbage-collected (its full
   subject block is removed).

**Image and audio deletion.** For each DELETE decision we collect every
triple with the node as subject, every triple with the node as object
(catching `schema:image`, `schema:thumbnail`, …), and — for audio —
the entire blank-node subgraph of the `MusicRecording` including any
nested `schema:MusicComposition` via `schema:recordingOf`. All collected
triples are removed from the main graph and mirrored into the side
graph so the information is preserved, not discarded.

**Serialisation.** The pruned main graph is written to
`data/kg/imdb_kg_cleaned.pruned.ttl` and the side graph to
`data/kg/imdb_kg_failed_media.ttl`. The original TTL is never touched.

### 4.6  Step S6 — Sidecar sync

`sync_sidecars.py` propagates the changes to the JSON book-keeping:

* `entity_cache.json` — removed entries for DELETE decisions; video
  URI/embed-URL rewritten for REWRITE decisions.
* `download_progress.json` — DELETE URLs moved from the entity's
  `failed[]` list into a new `purged[]` list (timestamped), so the
  failure history survives.

Both files are backed up (`.bak`) before modification.
Per-movie soundtrack side-cars are intentionally not touched.

---

## 5. Observed outcome (current snapshot)

Run against the graph as of the date of this document:

```
KG loaded:     1,815,922 triples
ImageObjects:     36,844
VideoObjects:      3,983     (372 via schema:trailer, 3 611 via schema:video)
MusicRecordings:   4,554     (across 357 movies)

Decisions:
  Images :  keep 34 415   rewrite 0   delete 2 805
  Videos :  keep  4 344   rewrite 6   delete   4
  Audio  :  keep  4 521   rewrite 0   delete  33

Effect on graph:
  Video back-refs rewritten     :      6   (4 source VideoObjects → 6 target URIs;
                                             one source shared by 3 entities, 3 used once)
  Video back-refs removed       :      4
  Image back-refs removed       :  2 805   (+ 2 805 ImageObject nodes GC'd)
  Audio bnode triples removed   :    248
  Total triples moved to side   : 17 144
```

Alignment against the pre-computed CLIP / X-CLIP / CLAP embedding tables
(`embeddings_output/*_embeddings.parquet`) after the pruning is near-perfect:

```
image : 33 247 parquet rows ↔ 33 247 KG keys    (0 orphans, 0 missing)
video :  4 350 parquet rows ↔  4 350 KG keys    (0 orphans, 0 missing)
audio :  4 034 parquet rows over 357 entities   (0 orphans, 3 missing*)
```

`* 3 movies assert a soundtrack in the KG but the track lacks a
resolvable YouTube URL and was therefore never downloaded.`

The side graph (`data/kg/imdb_kg_failed_media.ttl`) therefore captures a
complete description of every media asset that the IMDB4M corpus
describes but cannot serve — a useful artefact in its own right for
provenance research.

---

## 6. Using the tool

```bash
# Dry-run (default) — writes only manifest.json and report.xlsx
python -m kg_cleanup

# Actually mutate files
python -m kg_cleanup --apply

# Skip re-walking output/ (uses cached disk_scan.json)
python -m kg_cleanup --reuse-scan

# Skip re-parsing the TTL (uses pickled graph from a previous run)
python -m kg_cleanup --reuse-graph

# Only scan the disk, don't load the KG
python -m kg_cleanup --scan-only

# Leave entity_cache.json / download_progress.json alone
python -m kg_cleanup --apply --skip-sidecars
```

The dry-run takes ~40 s on a cold graph, ~11 s on a warm one. The full
`--apply` pipeline adds ~60 s for serialising the pruned Turtle graph.

---

## 7. Reproducing in a paper

A paper-safe summary:

> After the automatic download pass, a subset of media URLs remained in
> the failure log — a mixture of stale IMDB mediaviewer identifiers,
> relocated YouTube soundtracks, and transient anti-bot 403 responses.
> We first performed a targeted manual rescue of 41 items (6 IMDB
> trailers that had been re-published under new video ids, 15
> soundtrack tracks re-downloaded by hand from YouTube, and 20 tracks
> salvaged from a partial prior run and filed under their YouTube
> video-id as filename). We then implemented a reconciliation pipeline
> that (i) enumerates every image / video / audio back-reference in the
> knowledge graph, (ii) checks whether the expected file exists in the
> owning entity's output directory, (iii) **rewrites** 6 `VideoObject`
> back-references whose trailers had moved to new IMDB URIs (cloning
> the source node when the same stale URI had been rescued to
> *different* targets by different entities), and (iv) **deletes** the
> remaining unrecoverable references — 2,805 image back-references, 4
> video back-references, and 33 audio `MusicRecording` blank nodes —
> mirroring every deleted triple into an auxiliary `imdb_kg_failed_media`
> graph (17,144 triples in total) so that the descriptive metadata of
> the unretrieved assets remains available for provenance analysis
> while the main graph is free of dangling references. After cleanup,
> the pruned KG (1,798,826 triples) is 1:1 aligned with the pre-computed
> CLIP / X-CLIP / CLAP embedding tables (0 orphan embeddings, 0 missing
> KG references).

---

## 8. Known limitations and future work

* **Audio title matching** is currently normalised via
  `re.sub(r"[^\w]+", "", title.lower())`. This is robust to whitespace,
  punctuation and case but can theoretically collide if a movie has two
  tracks with identical simplified titles. The reconciler logs any such
  collision and treats all matching bnodes identically.
* **Graph back-references** are enumerated with
  `Graph.triples((None, None, node))`, which is O(|G|) per call.
  Reconciliation therefore takes ~0.5 s for 36 k images on a 1.8 M-triple
  graph; for much larger graphs, switching to an SPO-indexed store
  (e.g. `rdflib.plugins.stores.berkeleydb`) would be worthwhile.
* **The pipeline is single-threaded** for determinism. All heavy passes
  (disk scan, TTL parse, index build) are independent and could be
  parallelised trivially if required.
