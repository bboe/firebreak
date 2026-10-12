# Changelog

This project adheres to [Semantic Versioning](https://semver.org).

## 0.1.0 - 2026-10-11

First release.

### Added

- Takes an Echo Dot (2nd Generation) over USB, from macOS, Linux or Windows,
  to one of four targets, from stock or from another target:
  - `amonet-biscuit-v1.1.0-bboe`, the default: rooted Fire OS 5.5.5.4 on
    amonet v1.1.0, with TWRP 3.7.0_9-bboe2.
  - `amonet-biscuit-v1.1.0`: the same, with amonet v1.1.0's TWRP 3.2.3.
  - `amonet-biscuit-v2.0.0`: rooted Fire OS 6 8146 on amonet v2.0.0.
  - `stock BUILD`: back to stock Fire OS 6 at build 4315, 4405, 5041, 6302,
    8138, 8142 or 8146, with the Dot erased.
- Picks up a stopped run where it left off.
- `--short` reaches the bootrom for a Dot that shows no light.
- `--report` prints what a support request needs.
- `--write-test` tells a failing eMMC from a failing USB cable.
- A run says when PyPI has a newer firebreak. `--no-update-check` skips it.
- Runs with `uvx firebreak@latest`, or as `firebreak.pyz` from a GitHub release
  on Python 3.9 or later.
