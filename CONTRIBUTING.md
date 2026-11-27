# Contributing

## Asking for help or a new Echo

- For a run that failed, or for help running firebreak, ask in
  `#firebreak-support` in the
  [0x7E Labs Discord](https://discord.gg/huE5XhWbsz). Paste the run's output
  and what `uvx firebreak@latest report` prints. Most failed runs come from
  the Echo, the cable, the USB port or a driver. If you refuse to use Discord,
  the "Help without Discord" form asks for the same and for one short reason.
- Open an issue for a bug only when you are sure the fault is in firebreak or
  in the unlock it runs. Open one to ask for a new Echo or bootloader. Each
  form says what to paste.

Each request for an Echo carries an `unlock:` label that gives its status:

| label | meaning |
| --- | --- |
| `unlock: none known` | No public unlock exists, so firebreak has nothing to drive. |
| `unlock: exists elsewhere` | A public unlock exists, but firebreak does not drive it yet. |
| `unlock: in progress` | The unlock is being brought into firebreak. |
| `unlock: supported` | firebreak unlocks this Echo. |

## Changing the code

Read the section of `docs/unlocking.md` for a step before you change that
step. Most of it was measured on hardware.

Run the checks that CI runs:

```sh
uvx --with tox-uv tox
```

- The code runs on Python 3.9.6, Apple's `/usr/bin/python3`, with the
  standard library and three pinned dependencies. A test fails on most uses
  of an API that 3.9.6 does not have, but it cannot see methods on objects.
  Run the code on 3.9.6 to be sure.
- Each module but `__main__.py` keeps 90% line coverage. The tests fake adb,
  pyserial and amonet, so they need no Echo.
- Put no explanatory comments in the code. Write the why in
  `docs/unlocking.md`, in the section for that step.
- A change to what firebreak does adds an entry under `Unreleased` in
  `CHANGELOG.md`.
- Put no Echo serial numbers in commits, issues or docs. Write `SERIAL`.

Only a run on an Echo proves a change. In the pull request, say which Echo and
which computer you ran it on, or say that you did not.

`main` takes only signed commits, and it is merged by fast-forward. The
maintainer may rebase and sign your commits before the merge.
