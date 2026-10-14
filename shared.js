/* BrainBlitz shared data and routes.
   Loaded by index.html, create.html and lobby.html so the three pages agree on
   where things live and which quizzes exist. index.html is the hub. */
(() => {
  const mcq = (q, time, pts, opts, right) => ({ q, type: 'quiz', time, pts, a: opts.map((t, i) => ({ t, c: i === right })) });
  const tfq = (q, time, pts, ans) => ({ q, type: 'tf', time, pts, a: [{ t: 'True', c: ans }, { t: 'False', c: !ans }] });

  /* Quizzes that ship with the site. Same question format the editor saves. */
  const CATALOG = [
    {
      id: 'space', title: 'Space Explorers', creator: 'BrainBlitz', emoji: '🚀', color: '#7C3AED', c1: '#7C3AED', c2: '#312E81', plays: '12.3K', trending: false,
      qs: [
        mcq('Which planet is known as the Red Planet?', 10, 1, ['Venus', 'Jupiter', 'Mars', 'Mercury'], 2),
        tfq('The Sun is a star.', 10, 1, true),
        mcq('Who was the first human to walk on the Moon?', 10, 1, ['Neil Armstrong', 'Buzz Aldrin', 'Yuri Gagarin', 'John Glenn'], 0),
        tfq('Sound can travel through the vacuum of space.', 10, 1, false),
        mcq('Which planet has the most known moons?', 20, 1, ['Jupiter', 'Saturn', 'Uranus', 'Neptune'], 1),
        mcq('About how long does sunlight take to reach Earth?', 20, 2, ['8 seconds', '8 hours', '8 days', '8 minutes'], 3),
        tfq('A day on Venus is longer than a year on Venus.', 20, 2, true),
        mcq('Which star is the closest to Earth after the Sun?', 30, 2, ['Proxima Centauri', 'Sirius', 'Betelgeuse', 'Polaris'], 0),
      ],
    },
    {
      id: 'capitals', title: 'World Capitals Showdown', creator: 'Ms. Alvarez', avatar: '#EC4899', emoji: '🌍', color: '#8B5CF6', c1: '#8B5CF6', c2: '#4C1D95', plays: '48.2K', trending: true,
      qs: [
        mcq('What is the capital of Australia?', 15, 1, ['Sydney', 'Canberra', 'Melbourne', 'Perth'], 1),
        mcq('Which city is the capital of Canada?', 15, 1, ['Toronto', 'Vancouver', 'Ottawa', 'Montreal'], 2),
        tfq('Istanbul is the capital of Turkey.', 10, 1, false),
        mcq('Which capital city sits on the River Seine?', 15, 1, ['Paris', 'Rome', 'Madrid', 'Berlin'], 0),
        mcq('Nairobi is the capital of which country?', 15, 2, ['Tanzania', 'Uganda', 'Kenya', 'Ethiopia'], 2),
      ],
    },
    {
      id: 'elements', title: 'Periodic Table Panic', creator: 'Dr. Okafor', avatar: '#0EA5E9', emoji: '🧪', color: '#EC4899', c1: '#EC4899', c2: '#9D174D', plays: '31.7K', trending: true,
      qs: [
        mcq('What is the chemical symbol for gold?', 10, 1, ['Ag', 'Au', 'Gd', 'Go'], 1),
        mcq('Which gas do plants absorb from the air?', 10, 1, ['Oxygen', 'Nitrogen', 'Carbon dioxide', 'Helium'], 2),
        tfq('Water is made of hydrogen and oxygen.', 10, 1, true),
        mcq('Which element has the atomic number 1?', 10, 1, ['Helium', 'Hydrogen', 'Lithium', 'Carbon'], 1),
        mcq('Which noble gas gives classic glowing red-orange signs?', 15, 2, ['Neon', 'Argon', 'Radon', 'Xenon'], 0),
      ],
    },
    {
      id: 'rome', title: 'Ancient Rome in 15 Minutes', creator: 'Mr. Jenkins', avatar: '#7C3AED', emoji: '🏛️', color: '#F59E0B', c1: '#F59E0B', c2: '#B45309', plays: '22.9K', trending: true,
      qs: [
        mcq('Who was the first Roman emperor?', 15, 1, ['Julius Caesar', 'Augustus', 'Nero', 'Caligula'], 1),
        tfq('The Colosseum was built in ancient Rome.', 10, 1, true),
        mcq('What language did the ancient Romans speak?', 10, 1, ['Greek', 'Latin', 'Italian', 'Etruscan'], 1),
        mcq('Which city was buried by Mount Vesuvius in 79 AD?', 15, 1, ['Pompeii', 'Athens', 'Carthage', 'Troy'], 0),
        tfq('Julius Caesar was a Roman emperor.', 15, 2, false),
      ],
    },
    {
      id: 'maths', title: 'Mental Maths Mayhem', creator: 'Priya Nair', avatar: '#F59E0B', emoji: '➗', color: '#0EA5E9', c1: '#0EA5E9', c2: '#1E3A8A', plays: '67.5K', trending: true,
      qs: [
        mcq('What is 12 × 12?', 10, 1, ['124', '144', '142', '112'], 1),
        mcq('What is the square root of 81?', 10, 1, ['7', '8', '9', '11'], 2),
        tfq('A triangle has four sides.', 5, 1, false),
        mcq('What is 15% of 200?', 15, 2, ['20', '25', '30', '35'], 2),
        mcq('How many degrees are in a right angle?', 10, 1, ['45', '90', '180', '360'], 1),
      ],
    },
    {
      id: 'dinos', title: 'Dinosaurs: Fact or Fossil?', creator: 'Team Triassic', avatar: '#EC4899', emoji: '🦖', color: '#84CC16', c1: '#84CC16', c2: '#166534', plays: '18.4K', trending: true,
      qs: [
        tfq('Tyrannosaurus rex lived at the same time as humans.', 10, 1, false),
        mcq('Which dinosaur had three horns on its face?', 15, 1, ['Triceratops', 'Stegosaurus', 'Velociraptor', 'Brachiosaurus'], 0),
        tfq('Birds are descended from dinosaurs.', 10, 1, true),
        mcq('What do we call scientists who study fossils?', 15, 1, ['Geologists', 'Paleontologists', 'Biologists', 'Archaeologists'], 1),
        mcq('Which of these was a flying reptile, not a dinosaur?', 15, 2, ['Pteranodon', 'Allosaurus', 'Iguanodon', 'Ankylosaurus'], 0),
      ],
    },
    {
      id: 'movies', title: 'Name That Movie Quote', creator: 'Sam Whitfield', avatar: '#16A34A', emoji: '🎬', color: '#A855F7', c1: '#A855F7', c2: '#6B21A8', plays: '40.1K', trending: true,
      qs: [
        mcq('"May the Force be with you" comes from which film series?', 15, 1, ['Star Trek', 'Star Wars', 'Dune', 'Alien'], 1),
        mcq('"There’s no place like home" is said in which film?', 15, 1, ['The Wizard of Oz', 'Annie', 'Mary Poppins', 'Peter Pan'], 0),
        mcq('"To infinity and beyond!" is said by which character?', 10, 1, ['Woody', 'Buzz Lightyear', 'Rex', 'Slinky'], 1),
        tfq('"Hakuna Matata" is from The Lion King.', 10, 1, true),
        mcq('"Just keep swimming" is said by which character?', 10, 2, ['Nemo', 'Dory', 'Marlin', 'Bruce'], 1),
      ],
    },
  ];

  /* Game modes. Only Speed Round changes the rules so far (timers capped at 10s); the rest are labels. */
  const MODES = { classic: 'Classic', team: 'Team Battle', gold: 'Gold Rush', tower: 'Tower Defense', speed: 'Speed Round' };

  const ROUTES = { home: 'index.html', create: 'create.html', lobby: 'lobby.html' };
  const qs = (o) => { const p = new URLSearchParams(); Object.entries(o).forEach(([k, v]) => v && p.set(k, v)); const s = p.toString(); return s ? '?' + s : ''; };

  const BB = {
    routes: ROUTES,
    CATALOG, MODES,
    /* links between the pages: index.html (hub) ⇄ create.html ⇄ lobby.html */
    hostUrl: (quizId, mode) => ROUTES.lobby + qs({ quiz: quizId, mode }),
    editUrl: (quizId) => ROUTES.create + qs({ id: quizId }),
    newQuizUrl: () => ROUTES.create + '?new=1',
    myQuizzesUrl: () => ROUTES.create + '?mine=1',
    joinUrl: (pin) => ROUTES.home + qs({ pin }) + '#join',

    /* quizzes saved by the editor (localStorage) */
    savedQuizzes() {
      try { const a = JSON.parse(localStorage.getItem('brainblitz-quizzes')); return Array.isArray(a) ? a : []; } catch { return []; }
    },
    currentSaved() {
      try { const id = localStorage.getItem('brainblitz-current'); return BB.savedQuizzes().find((z) => z.id === id) || null; } catch { return null; }
    },
    getQuiz: (id) => BB.savedQuizzes().find((z) => z.id === id) || CATALOG.find((z) => z.id === id) || null,
  };
  /* design tokens that JavaScript needs come from brainblitz.css, so there is one source */
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  BB.ANSWER = { red: cssVar('--ans-red'), blue: cssVar('--ans-blue'), yellow: cssVar('--ans-yellow'), green: cssVar('--ans-green') };
  BB.GLOW = { common: cssVar('--rar-common'), rare: cssVar('--rar-rare'), epic: cssVar('--rar-epic'), legendary: cssVar('--rar-legendary') };
  BB.BLITZERS = [
    { e: '🐸', n: 'Hoppy', r: 'common' },   { e: '🐙', n: 'Octo', r: 'common' },
    { e: '🐼', n: 'Pando', r: 'common' },   { e: '🦊', n: 'Foxy', r: 'common' },
    { e: '🦉', n: 'Hootie', r: 'rare' },    { e: '🐧', n: 'Waddles', r: 'rare' },
    { e: '🦖', n: 'Rexie', r: 'rare' },     { e: '🦄', n: 'Sparkle', r: 'epic' },
    { e: '🐲', n: 'Ember', r: 'epic' },     { e: '🤖', n: 'Bolt', r: 'epic' },
    { e: '🦁', n: 'Kingsley', r: 'legendary' }, { e: '🐉', n: 'Nova', r: 'legendary' },
  ];
  /* the lobby publishes its state so the join page can say "full" or "already started" */
  BB.lobbyStatus = (pin) => {
    try {
      const st = JSON.parse(localStorage.getItem('brainblitz-lobby'));
      if (st && st.pin === pin && Date.now() - st.t < 15000) return st; // older than 15s: that lobby is gone
    } catch {}
    return null;
  };
  window.BB = BB;
})();
