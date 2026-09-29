/* 脈衝 PULSE —— 課程題庫外洩自我檢查
 *
 * 用法:在「學生會看到的那個網址」上按 F12 → Console(主控台)→ 貼上整段 → Enter
 * 要驗學生端,請用「無痕視窗」開,否則你自己的解鎖 cookie 還在,當然拿得到。
 */
(async () => {
  const j = async (u, o) => { const x = await fetch(u, o); return [x.status, await x.json().catch(() => null)]; };
  const P = (u, b) => j(u, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)});
  const COURSE = ['python', 'pytorch', 'ai', 'vba', 'emba'];

  const [, g] = await j('/api/gate');
  const [, c] = await j('/api/categories');
  const leak = (c || []).filter(x => COURSE.includes(x.key)).map(x => x.key);
  const solo = [];
  for (const k of COURSE) solo.push(k + '=' + (await P('/api/start', {category: k}))[0]);
  const room = (await P('/api/mp/create', {category: 'ai', count: 10, time: 20}))[0];

  console.log('%c脈衝 PULSE —— 課程題庫外洩自我檢查', 'font-size:15px;font-weight:bold');
  console.table({
    '鎖有沒有生效':  {結果: String(g && g.enforced),  應該是: 'true'},
    '這台已經解鎖':  {結果: String(g && g.unlocked),  應該是: '學生端 false'},
    '主題清單外洩':  {結果: leak.length ? leak.join(',') : '無', 應該是: '無'},
    '單人練習擋不擋': {結果: solo.join(' '),           應該是: '全部 403'},
    '自己開考坊':    {結果: String(room),             應該是: '403'},
  });

  if (!g || !g.enforced) {
    console.log('%c鎖沒有生效:這台伺服器沒設 TEACH_CODE(本機跑就是這樣,正常)。'
              + '要驗 Render 請連 Render 的網址。', 'font-size:14px;color:#b36b00');
  } else if (g.unlocked) {
    console.log('%c這個瀏覽器已經解鎖過了,所以上面拿得到是正常的。'
              + '要驗學生端,請開無痕視窗再跑一次。', 'font-size:14px;color:#b36b00');
  } else {
    const pass = !leak.length && solo.every(s => s.endsWith('403')) && room === 403;
    console.log(pass ? '%c全部通過:學生撈不到課程題庫。' : '%c有項目沒過,看上面那張表。',
                'font-size:14px;font-weight:bold;color:' + (pass ? '#1a7f37' : '#c00'));
  }
})();
