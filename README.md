# GPT Cleaner

Local-first image cleanup tool focused on **washing away the common high-frequency artifacts from GPT-generated images** while preserving structure.

## Goal

- remove fake hair strands, plastic highlights, dirty textures, and unstable AI micro-details
- keep character structure as stable as possible
- run on a remote Windows machine with a local lightweight web UI
- support one-click install and launch for agent-assisted setup

## Planned stack

- ComfyUI as the backend engine
- CCSR-v2 as the primary restoration route
- lightweight local web UI for upload / compare / download
- Windows-first installer with GPU self-check and VRAM-aware presets

## Status

Repository scaffold initialization in progress.
