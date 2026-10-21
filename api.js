/* BrainBlitz API client. Same origin as the pages, so no base URL or CORS. */
(function () {
  const KEY = 'brainblitz-token';
  let mem = null; // fallback when localStorage is blocked
  const token = () => { try { return localStorage.getItem(KEY) || mem; } catch { return mem; } };
  const setToken = (t) => { mem = t; try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch {} };

  async function request(method, path, body) {
    const headers = { 'Content-Type': 'application/json' };
    if (token()) headers.Authorization = 'Bearer ' + token();
    let res;
    try { res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }); }
    catch { throw Object.assign(new Error('Can\u2019t reach the server. Is it running?'), { status: 0 }); }
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      let msg = data && data.detail;
      if (Array.isArray(msg)) msg = msg.map((m) => String(m.msg).replace(/^Value error, /, '')).join(' ');
      if (res.status === 401 && token()) setToken(null); // expired or invalid
      throw Object.assign(new Error(msg || 'Something went wrong (' + res.status + ').'), { status: res.status });
    }
    return data;
  }

  window.BBApi = {
    isLoggedIn: () => !!token(),
    logout: () => setToken(null),
    async signup(email, password) { await request('POST', '/signup', { email, password }); return this.login(email, password); },
    async login(email, password) { const r = await request('POST', '/login', { email, password }); setToken(r.access_token); return r; },
    createQuiz: (quiz) => request('POST', '/quizzes', quiz),
    updateQuiz: (id, quiz) => request('PUT', '/quizzes/' + id, quiz),
    startRoom: (pin) => request('POST', '/rooms/' + encodeURIComponent(pin) + '/start'),
    nextRoom: (pin) => request('POST', '/rooms/' + encodeURIComponent(pin) + '/next'),
    endRoom: (pin) => request('POST', '/rooms/' + encodeURIComponent(pin) + '/end'),
    /* WebSocket for the host of a room (browsers can't set headers, so the token rides in the query) */
    hostSocket(pin) {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      return new WebSocket(proto + '//' + location.host + '/rooms/' + encodeURIComponent(pin) + '/ws?token=' + encodeURIComponent(token() || ''));
    },
    createRoom: (quizId) => request('POST', '/rooms', { quiz_id: quizId }),
    /* the report as a real file: fetched with the login (a plain link can't send it), then saved from a blob */
    async downloadReportCsv(gameResultId) {
      let res;
      try { res = await fetch('/results/' + encodeURIComponent(gameResultId) + '/report.csv', { headers: { Authorization: 'Bearer ' + (token() || '') } }); }
      catch { throw Object.assign(new Error('Can\u2019t reach the server. Is it running?'), { status: 0 }); }
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        if (res.status === 401) setToken(null);
        throw Object.assign(new Error((data && data.detail) || 'Couldn\u2019t download the report (' + res.status + ').'), { status: res.status });
      }
      const name = (/filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '') || [])[1] || 'brainblitz-results.csv';
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a');
      a.href = url; a.download = name;
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      return name;
    },
    getReport: (gameResultId) => request('GET', '/results/' + encodeURIComponent(gameResultId) + '/report'),
    getResults: (pin) => request('GET', '/rooms/' + encodeURIComponent(pin) + '/results'),
    getRoom: (pin) => request('GET', '/rooms/' + encodeURIComponent(pin)),
    joinRoom: (pin, nickname, avatar) => request('POST', '/rooms/' + encodeURIComponent(pin) + '/join', { nickname, avatar }),
  };
})();
