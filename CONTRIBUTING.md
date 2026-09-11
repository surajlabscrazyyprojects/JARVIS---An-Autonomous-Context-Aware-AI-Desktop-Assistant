# Contributing to JARVIS

## Development setup

Create a Python virtual environment, install `requirements.txt`, install Node dependencies with `npm install`, and copy `.env.example` to `.env`. Keep credentials and runtime memory local.

## Changes and tests

Preserve the existing voice, HUD, memory, and automation architecture. Add or update focused tests for behavior changes, then run `python -m pytest` and any relevant `npm` checks locally.

## Pull requests

Describe the user-visible change, security/privacy impact, and verification performed. Never include `.env`, logs, screenshots, recordings, browser profiles, memory files, or API values in commits or issue reports.
