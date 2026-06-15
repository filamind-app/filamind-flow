# Board Topology

Board Topology draws an interactive map of the control boards inside your printer. If you have ever lost track of which MCU is your mainboard, which one rides on the toolhead, or what is actually plugged into what, this widget lays it out for you and links each part straight to its catalog record.

## What it does

The centerpiece is a live SVG node-graph that you can pan and click. It comes in two views.

The **Physical view** shows the hardware as it is wired. A single-board computer is drawn inside the mainboard it ships on, so a combined SBC-plus-MCU board reads as one unit instead of two floating nodes. A CAN toolhead sits on a shared backbone, the way it really hangs off the CAN bus. Boards on USB or UART appear as separate units. Edges between nodes are colour-coded by bus, so you can tell at a glance whether two parts talk over CAN, USB, or UART.

The **Logical view** drops the wiring and shows Klipper's command tree instead: the host at the root, with each MCU branching off it. This is the view to reach for when you care about how Klipper addresses your boards rather than how the cables run.

Every node is clickable. Click a board, an SBC, or an MCU and you get its catalog record: specifications, ports, electronics caveats, configuration notes, and a Klipper config snippet you can copy. From there you can deep-link into the hardware database for the full entry.

Detection is not always certain, so you stay in control of it. For any MCU you can confirm the board the widget detected, or override it with the right one. Your choice is saved on the host and reused on every later read, so you only have to correct a given board once.

Throughout the widget there is illustrated help explaining the views, the bus colours, and the confirm/override flow.

## Using it

1. Open Board Topology. The map loads with the Physical view and the boards it detected from your running Klipper instance.
2. Pan around the graph and follow the coloured edges to see how your boards connect.
3. Switch to the Logical view if you want to see the host-to-MCU command tree instead.
4. Click any node to open its catalog record. Read the specs and notes, and copy the config snippet if you need it.
5. From a record, deep-link into the hardware database for the complete entry.
6. If an MCU shows the wrong board, or you simply want to lock in the right one, confirm or override it. The choice is stored on the host and applied automatically next time.

## Notes

This widget works on any Klipper printer. It reads your live configuration rather than assuming a particular machine, so the map reflects whatever boards you actually run.

Confirming or overriding a board is a deliberate step. The detection is a best guess; your confirmation is what makes it stick, and it is saved per MCU on the host so it carries across reads.

Catalog records can include electronics caveats and configuration notes. Read those before acting on a snippet, especially around wiring and power, where a wrong assumption can damage hardware.

← [All widgets](./README.md) · [FilaMind Flow](../../README.md)
