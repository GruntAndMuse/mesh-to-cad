# Roadmap

Where mesh-to-cad is going. This is a living document — it changes as we learn.

## Now: Phase 1 — Measure (done)

The pipeline can take a mesh, validate its units, check its quality, analyze its geometry, and suggest whether it's a prismatic or organic rebuild. Every step ends with a number, not a feeling.

## Next: Phase 2 — Rebuild (in progress)

Automated reconstruction:
- **RANSAC feature detection** — find holes, cylinders, and planes automatically
- **Denoise → MeshToFeatures** — clean the mesh, extract features
- **Primitive-to-CAD generation** — turn detected features into parametric FreeCAD/build123d models
- **Section → spline → loft** — for organic shapes, slice the mesh and rebuild surfaces
- **Adaptive deviation loop** — put more effort where the error is highest

Goal: go from scan to editable CAD with minimal manual work.

## Then: Phase 3 — Prove

- Full round-trip testing on real scanner output (Creality Raptor Pro)
- Benchmark suite with known-good models
- Drawing generation (2D manufacturing drawings from the rebuilt CAD)

## Beyond: The Bigger Picture

mesh-to-cad started as a 3D printing tool, but the core idea — *don't ask if it looks right, measure how much it deviates* — applies anywhere dumb geometry needs to become smart geometry:

- **Animation & game dev** — clean up scanned assets, retopologize with measurable fidelity
- **Video production** — the GruntAndMuse show itself will use this pipeline
- **Reverse engineering** — document and reproduce physical parts

## Accessibility roadmap

Not everyone can use a command-line tool. We build for the people with the fewest options first:

- **Now:** Standalone executables (no Python needed) + QUICKSTART with screenshots
- **Next:** Simple GUI — **drag-and-drop** STL files onto the window, Run button, progress bar, plain-English results. (Dennis, 2026-10-03: "definitely gui and drag and drop if possible.") Tkinter (zero new dependencies, works everywhere) unless drag-and-drop needs more — then evaluate Dear PyGui (MIT, FOSS, offline).
- **Later:** Package managers (Chocolatey, Homebrew) — `choco install mesh-to-cad`
- **Eventually:** Ports to other platforms/languages where the need exists. Low priority by user count, high priority by principle — the people with the fewest options appreciate it most.
- **Spoken languages:** All-inclusive means all languages. UI strings via gettext, community-contributable translations. Spanish first (large maker community), then wherever contributors take it.
- **Voice output:** Two options. **Local** (Piper TTS — FOSS, offline, private) is the default, matching our privacy principle. **Cloud** (higher quality voices) as opt-in for users who don't need offline. Every pipeline gets a `--voice` flag. (Dennis, 2026-10-02: "Any software we have to write to make it work is worth the effort.")

## What we won't do

- We won't add cloud features. Your files stay on your machine. Ever.
- We won't add telemetry. We don't want your data.
- We won't paywall features. MIT means MIT.
- We won't rush. Slow is smooth, smooth is fast.

---

*Last updated: 2026-10-02*
