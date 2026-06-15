# Input Shaping

Input Shaping turns a Klipper resonance capture into a ready `[input_shaper]` config, without touching the command line. It is for anyone fighting ghosting and ringing in their prints, whether you have run resonance tuning a dozen times or never once.

## What it does

At its core, the widget reads a resonance capture and tells you what to do with it. It picks a recommended shaper, draws an SVG frequency-response chart so you can see where your machine resonates, and handles the X and Y axes separately. When you want to compare two captures, an A-vs-B view puts them side by side.

It does not just hand you numbers and walk away. Every capture gets a quality grade from A to F, backed by illustrated diagnostics that explain what went wrong and how to fix it. The point is to tell you whether a measurement is trustworthy before you act on it.

Beyond reading a capture, the widget includes live tooling for the rest of the resonance-tuning process. There are live tests, belt tooling, an axes-map check, and vibration measurement. A guided wizard ties these together and walks you through tuning step by step. Taken together it is a complete resonance-tuning suite, not a single calculator.

## Using it

The typical flow looks like this:

1. Start a resonance capture, or bring in one you already have.
2. Let the widget recommend a shaper and read the frequency-response chart.
3. Check the X and Y axes, and use the A-vs-B compare if you have a second capture to weigh against the first.
4. Read the quality grade and the illustrated diagnostics. If the grade is poor, follow the suggested fixes and capture again.
5. When you are happy with the result, apply the recommended `[input_shaper]` config.

If you would rather not drive this yourself, the guided wizard runs the same steps in order and tells you what to do at each one. The belt, axes-map, and vibration tools are there when you want to dig deeper into a specific problem.

## Notes

This widget works on any Klipper printer with resonance testing available.

Live tests and other actions that move the machine ask you to confirm before they run, and they are refused while a print is in progress. Some parts of the suite are experimental. The quality grade and diagnostics are guidance to help you judge a capture, not a guarantee, so use your own judgment before committing a config change.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
