# Two-AI Handoff Self-Test Artifact

Issue: #8
Phase: AI-A handoff

## Purpose

This file is a deliberately small durable artifact for testing whether a second AI session can resume work using GitHub only, without access to AI-A's chat history.

## AI-A result

AI-A created this file on the dedicated `issue-8-handoff-selftest-a` branch.

The artifact defines a deterministic continuation task for AI-B:

1. Read Issue #8 and its structured comments.
2. Fetch this file from the branch/PR referenced by the latest HANDOFF.
3. Verify the marker below exactly.
4. Append an `## AI-B verification` section stating the marker observed and whether the GitHub-only handoff contained enough information to continue.
5. Commit the update on the existing handoff branch (or a clearly referenced successor branch), open/update a PR, and post a structured RESULT to Issue #8 with the commit/PR artifact references.

## Verification marker

`AI-B-CAN-RESUME-FROM-GITHUB-ONLY-v1`

## Pass condition

The experiment passes only if AI-B can perform the continuation from GitHub state alone and records its RESULT/evidence on GitHub. AI-A does not mark the overall Issue #8 complete; it hands off at this point.
