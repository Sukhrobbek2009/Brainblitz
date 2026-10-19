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
    createRoom: (quizId) => request('POST', '/rooms', { quiz_id: quizId }),
  };
})();
