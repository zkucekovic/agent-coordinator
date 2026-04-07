# Implementation Plan — Tetris Game

## Overview

Build a single-file HTML Tetris game (`tetris.html`) with canvas rendering, all 7 tetrominoes, full controls, scoring, and level progression.

## Task Breakdown

### task-001: HTML scaffold, canvas, game board, and game loop
Create the HTML file with inline CSS and JS. Set up a `<canvas>` element, render a 10×20 grid, and implement the core game loop (`requestAnimationFrame` with timing).

**Depends on:** nothing

### task-002: Tetromino definitions, spawning, and rendering
Define all 7 tetrominoes (I, O, T, S, Z, J, L) with correct shapes and standard colors. Implement spawning at the top center. Render the current piece on the board.

**Depends on:** task-001

### task-003: Movement, rotation, collision detection, and wall kicks
Implement left/right/down movement with keyboard input. Add clockwise rotation with wall-kick logic. Implement collision detection against walls, floor, and locked pieces.

**Depends on:** task-002

### task-004: Line clearing, scoring, and level progression
Detect and clear completed rows. Implement the scoring system (100/300/500/800 × level). Add a level system that increases drop speed every 10 lines.

**Depends on:** task-003

### task-005: UI — score display, next piece preview, game over, pause
Add HUD showing score, level, and lines cleared. Add a next-piece preview panel. Implement game over detection and screen. Add pause/unpause with P or Escape.

**Depends on:** task-004

### task-006: Hard drop, polish, and final integration
Implement spacebar hard drop (instant placement with visual feedback). Final edge-case fixes, visual polish, and cross-browser validation.

**Depends on:** task-005

## Delivery

The final deliverable is a single `tetris.html` file that opens in any modern browser and provides a complete, playable Tetris experience.
