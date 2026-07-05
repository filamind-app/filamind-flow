# Machine Doctor

![Machine Doctor in FilaMind Flow, running on a Sovol SV08](../screenshots/machine-doctor.png)

Machine Doctor runs a single read-only scan across everything FilaMind can check and hands you back a graded report. It's the widget to open when something feels off, or when you just want a health check before a long print.

## What it does

The scan looks at your machine from several angles in one pass. It checks for pin conflicts in your config, compares driver values against the real ceilings for your hardware, and looks for config drift between what's on disk and what's actually running. It also lints your project for the kinds of mistakes that bite you later.

Beyond the config itself, it confirms firmware is in sync, flags hardware changes since the last time it looked, and checks that the install is healthy.

Every check feeds into one overall grade from A to F, and the scoring is transparent so you can see exactly why the number is what it is. The score blends two kinds of pillar. **Health checks** — config integrity, firmware sync, services — score how healthy the things the Doctor could actually read are; a signal it can't read right now, like a firmware version while Moonraker is offline, simply drops out instead of counting against you.

**Setup steps** — running input shaping, finding your max flow, and tuning your motor drivers — are the readiness half. Until you've run one it counts as zero, so a printer that hasn't been tuned scores low even when nothing is broken, and each step you finish visibly raises the number. The hero shows this as a readiness ring around the grade (one segment per step, filled as you go), a "Setup readiness" checklist, and a caution banner while any step is still pending. A clean "healthy" A only appears once nothing is broken and every setup step is done.

Each finding is actionable too. When the Doctor spots a problem — or a setup step still to run — it deep-links straight into the widget that handles it (input shaping, max flow, the Motor Drivers widget…), so you go from "what's wrong" to "here's where to fix it" in one click.

## Using it

The typical flow is short. Open Machine Doctor and start a scan. It reads across pins, drivers, config, project lint, firmware, hardware, and install health, then shows the A-F grade with the findings that produced it. Work through the findings by following each one's link into the widget that addresses it. When you're done, scan again to confirm the grade has moved.

## Notes

The scan is read-only. It looks and reports; it does not change your configuration on its own. Anything that would write follows the usual confirm gate in the widget you're sent to, and actions are refused while a print is running.

Some parts of the scan are experimental, so treat those findings as guidance rather than gospel. The Doctor works on any Klipper printer.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
