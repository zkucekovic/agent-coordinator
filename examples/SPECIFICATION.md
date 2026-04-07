# Tetris Game — Project Specification

Build a fully playable Tetris game as a single-file HTML application. The game should run in any modern browser with no build step, no dependencies, and no server.

## Requirements

### Core gameplay
- 10-column, 20-row playing field
- All 7 standard tetrominoes (I, O, T, S, Z, J, L) with correct shapes and colors
- Piece rotation (clockwise) with wall kick (prevent rotation into walls or other pieces)
- Piece movement: left, right, soft drop (down arrow), hard drop (spacebar)
- Line clearing when a row is completely filled
- Increasing speed as the player clears more lines (level system)
- Game over when a new piece cannot fit its full length from the top of the screen without colliding with another piece

### Display
- Show the current score, level, and number of lines cleared
- Show a "Next piece" preview
- Show the playing field with a visible grid
- Game over screen with final score

### Scoring
- Single line: 100 points
- Double: 300 points
- Triple: 500 points
- Tetris (4 lines): 800 points
- Multiply by current level

### Controls
- Left/Right arrows: move piece
- Up arrow: rotate clockwise
- Down arrow: soft drop (faster fall)
- Spacebar: hard drop (instant placement)
- P or Escape: pause/unpause

### Technical constraints
- Single HTML file (inline CSS and JavaScript)
- No external dependencies, no images, no fonts to load
- Canvas-based rendering
- Must work in Chrome, Firefox, and Safari
- Clean, readable code with comments on non-obvious logic
