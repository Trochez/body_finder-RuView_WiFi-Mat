# ADR-DEV19-ROADMAP-SHIFT

**Status:** Accepted  
**Release:** dev-19 / 0.2.0-experimental.19

## Decision

Temporarily redefine dev-19 from human/no-human work to **acquisition / peer-continuity hardening and scientific closure of dev-18**.

## Reason

The dev-18 second physical campaign produced a local Pixel 10 failure (`peer_expire_delta=28`) while Pixel 7 Pro and Lenovo passed. Building human-detection claims on a physically failing acquisition baseline would invalidate later evidence.

## Consequences

- dev-19 contains no validated human detection/localization/rescue feature.
- `human_scanning_enabled=false`, `human_localization_validated=false`, `rescue_use_validated=false` remain mandatory.
- human/no-human work resumes only after the final 3-Android dev-19 gate passes.
- calibration, reciprocal fusion and autogeometry remain frozen.
