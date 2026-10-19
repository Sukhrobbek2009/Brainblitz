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
| `theme.js` | Light/dark toggle. Loaded in `<head>` so there is no flash. Saves the choice in `localStorage` (`brainblitz-theme`), follows the system setting until you choose, and syncs across tabs. | |
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

## On a phone

- **Home:** the nav collapses to a burger menu (Join, Discover, Game Modes, For Teachers, Create, Host a game). On a phone the join card comes first, above the hero copy.
- **Editor:** the three panels become tabs (Questions, Edit, Settings). Cover colour and visibility move into the Settings tab, and each question gets ▲▼ buttons because drag-and-drop doesn't work on touch.
- **Game (`lobby.html`, 640px and narrower, or a landscape phone):** the question screen is the player's pad, like Kahoot. It is four giant shapes in a 2×2 grid (two tall tiles for True/False), with no question or answer text. The question and answers stay in the page as hidden text for screen readers. The host-only controls (Pause, Skip, results chart, Back to lobby) are hidden. Wider screens show the host view with the question.
- Every control is at least 44px tall on a phone (the colour swatches have a 44px hit area).

## Accessibility

- **Shape and colour:** every answer has a shape (▲ ◆ ● ■) as well as a colour, in the editor, the game, the results chart and the phone pad. Selected options use a ✓ as well as a colour, and Easy/Tricky/Hard on the report is always written out.
- **Labels:** every button, link and field has an accessible name. Icon-only buttons say what they do (e.g. "Delete “Space Explorers”", "Move question 2 up"), and answer fields name their shape (“Answer 1, red triangle”). The theme button names the action ("Switch to light mode"). Home and the editor have a skip link.
- **Focus:** a 3px ring on everything focusable (lime on dark, violet on light). Answer tiles get a dark ring with a white halo so it shows on every colour. The text fields' own focus styles also show.
- **Reduced motion** (system setting, checked live): no animations or springy hovers, no smooth scrolling, no confetti or drumroll (the results appear at once), and scores don't count up.
- **Theme:** the toggle is in the nav of every page. Colours come from tokens in `brainblitz.css` (`:root[data-theme="light"]`); the footer, feedback screens, pause veil and host controls stay dark in both themes (`.dark-zone`).

## Notes

- Quizzes are saved in `localStorage` (keys `brainblitz-quizzes`, `brainblitz-current`). If storage is blocked, the editor keeps them in memory for the tab.
- There is no server. Players in the lobby are simulated, with one exception: if you finish the join flow on `index.html` in another tab of the same browser using the lobby's PIN, that player appears in the lobby's roster. Their answers are still simulated.
- After a game, the final screen has a Report tab (summary, per-question accuracy, players who may need help) and an Export CSV button. Accuracy counts players who didn't answer as wrong.
- Of the game modes, only Speed Round changes the rules so far (timers capped at 10 seconds). The others are labels.
