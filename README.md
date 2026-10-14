# BrainBlitz

A live quiz game. Open `index.html` in a browser (no build step).

## How the pages connect

`index.html` is the hub. Every page links back to it, and links between pages are built from `shared.js` (`BB.routes`, `BB.hostUrl()`, `BB.joinUrl()` and friends).

| Page | What it is | Deep links |
| --- | --- | --- |
| `index.html` | Landing page, join flow (PIN → nickname → Blitzer), Game Modes, Trending quizzes, For Teachers | `#join`, `#discover`, `#modes`, `#how`, `#teachers`, `?pin=123456` (prefills the PIN) |
| `create.html` | Quiz editor with My Quizzes | `?new=1` (new quiz), `?id=<quizId>` (open a saved quiz), `?mine=1` (open My Quizzes) |
| `lobby.html` | Host lobby and the full game: question → reveal → feedback → leaderboard → final results | `?quiz=<id>` (saved or built-in quiz), `?mode=classic\|team\|gold\|tower\|speed`, `?source=sample` |
| `brainblitz.css` | The design system: colour, radius and edge tokens, the answer colours, 3D buttons, logo, nav, toast, and the empty / blocked / banner / skeleton components. Every page links it first. | |
| `shared.js` | Built-in quizzes (the Space sample and the six trending quizzes), game-mode names and route helpers | |

Flows:

- **Host:** `index.html` → Host a game → `create.html` (build or pick a quiz) → Save & Host → `lobby.html`. A trending quiz's Play button and a Game Mode tile go straight to `lobby.html`.
- **Create:** `index.html` → Create / For Teachers → `create.html` → Save & Host → `lobby.html?quiz=<id>`
- **Join:** `lobby.html` → "Try joining as a player" → `index.html?pin=…#join`
- **After a game:** Play again restarts the same quiz with the same players. New quiz opens My Quizzes (`create.html?mine=1`). Home goes to `index.html`.
- **Back home:** the logo on every page, plus Home links in My Quizzes and the final results.

## Design previews and test switches

- `index.html?preview=full | started | reconnecting` shows the join card's "Game is full", "Game already started" and "Reconnecting…" states. `?preview=loading` keeps the Trending skeleton cards on screen.
- The join page shows the real versions of those states when a lobby with the same PIN is open in another tab: "full" when the lobby has reached its limit (`lobby.html?max=12` lowers it), "already started" once the host presses Start, and "Reconnecting…" if that lobby stops answering.
- "My Quizzes" shows its empty state whenever no quiz has been saved yet.

## Notes

- Quizzes are saved in `localStorage` (keys `brainblitz-quizzes`, `brainblitz-current`). If storage is blocked, the editor keeps them in memory for the tab.
- There is no server. Players in the lobby are simulated, with one exception: if you finish the join flow on `index.html` in another tab of the same browser using the lobby's PIN, that player appears in the lobby's roster. Their answers are still simulated.
- After a game, the final screen has a Report tab (summary, per-question accuracy, players who may need help) and an Export CSV button. Accuracy counts players who didn't answer as wrong.
- Of the game modes, only Speed Round changes the rules so far (timers capped at 10 seconds). The others are labels.
