# DataLume — Claude Code Build Package

This folder is a ready-to-drop-in project handoff for Claude Code.

## Contents

```
CLAUDE.md                    ← Claude Code reads this automatically first
docs/
  BUILD_PROMPT.md            ← full authoritative product/technical spec
  DESIGN_SYSTEM.md           ← visual design system (colors, layout, components)
```

## How to use this

1. Unzip this into a new empty git repository (or a fresh folder you'll
   `git init` yourself).
2. Open it in Claude Code (`claude` in the terminal, or the desktop app).
3. Claude Code will pick up `CLAUDE.md` automatically as project
   instructions. Kick things off with something like:

   > Read CLAUDE.md and docs/BUILD_PROMPT.md in full, then produce the
   > DataLume Build 1 Architecture Pack as described. Do not write any
   > implementation code yet.

4. Review the Architecture Pack it produces. Once you're happy with it,
   tell it to proceed sprint by sprint per the implementation order in
   `BUILD_PROMPT.md` §80.

## Note on the design mockups

The two reference screenshots you shared (app dashboard + marketing/
sign-in page) weren't retained as image files in this handoff — they
weren't accessible on disk when this package was assembled. Instead,
`docs/DESIGN_SYSTEM.md` captures everything from those mockups in writing
(exact layout structure, color values, component patterns) so Claude Code
has a concrete spec to build against.

If you still have the original PNGs, it's worth dropping them into
`docs/design-reference/` and re-uploading them directly to Claude Code at
the start of the session — a real image is always a stronger reference
than a written description for pixel-level styling decisions.
