/* 成績本機備份 —— 跟伺服器完全無關的一層保險
 *
 * 為什麼需要它:Render 免費方案掛不了硬碟,重新部署或休眠重啟後 leaderboard.db 會歸零。
 * 也就是說「存入班級積分」在雲端只是暫存,真正安全的是把 CSV 存到老師自己的裝置上,
 * 而那一步原本完全靠人記得按。
 *
 * 這支檔案做三件事:
 *   1. 放榜時自動下載一份 CSV 到這台電腦
 *   2. 同時把成績存進這個瀏覽器(localStorage,最近 20 場),隨時可以補匯出
 *   3. 還有沒備份的場次時,關掉分頁會先問一句
 *
 * 限制:localStorage 綁在「這台電腦的這個瀏覽器」。換電腦、清瀏覽器資料就沒了,
 * 所以它是保險,不是主檔;正式成績還是以匯出的 CSV 為準。
 */
(function (w) {
  'use strict';

  var KEY = 'pulse_backup_v1';
  var MAX = 20;                       // 最多留 20 場,免得把 localStorage 塞爆

  /* localStorage 在無痕視窗、關閉 cookie、儲存空間滿的時候都會丟例外,
     一律包起來:備份失敗不能影響上課。 */
  function attempt(fn, dflt) { try { return fn(); } catch (e) { return dflt; } }
  function load() {
    var r = attempt(function () { return JSON.parse(w.localStorage.getItem(KEY)); }, null);
    return Array.isArray(r) ? r : [];
  }
  function store(rows) {
    return attempt(function () {
      w.localStorage.setItem(KEY, JSON.stringify(rows.slice(0, MAX)));
      return true;
    }, false);
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function pad(n) { return String(n).padStart(2, '0'); }
  function stamp(t) {
    var d = new Date(t);
    return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + '-' + pad(d.getHours()) + pad(d.getMinutes());
  }
  function nice(t) {
    var d = new Date(t);
    return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  /* 這一場的指紋:重新整理放榜頁不會重複存,但「再來一局」分數不同,會算成新的一場 */
  function sign(v) {
    return [v.code, v.class_code || '', v.topic || '', v.total || 0,
            (v.final || []).map(function (p) { return (p.sid || p.name) + ':' + p.score; }).join('|')].join('#');
  }

  function record(v) {
    if (!v || !Array.isArray(v.final) || !v.final.length) return null;
    var rows = load(), sg = sign(v);
    for (var i = 0; i < rows.length; i++) if (rows[i].sign === sg) return rows[i];
    var rec = {
      id: 'g' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      sign: sg, at: Date.now(), exported: false,
      code: v.code, class_code: v.class_code || '', topic: v.topic || '',
      category: v.category || v.topic || '', mode: v.mode || 'solo', total: v.total || 0,
      players: v.final.map(function (p) {
        return { sid: p.sid || '', name: p.name, team: p.team || '',
                 score: p.score, right: p.right, bonus: p.bonus || 0 };
      }),
      teams: (Array.isArray(v.team_board) ? v.team_board : []).map(function (t) {
        return { team: t.team, avg: t.avg, total: t.total, members: t.members };
      })
    };
    rows.unshift(rec);
    store(rows);
    return rec;
  }

  function mark(id) {
    var rows = load();
    for (var i = 0; i < rows.length; i++) if (rows[i].id === id) { rows[i].exported = true; break; }
    store(rows);
  }
  function drop(id) {
    store(load().filter(function (r) { return r.id !== id; }));
  }
  function pending() {
    return load().some(function (r) { return !r.exported; });
  }

  /* ---------- CSV:欄位跟伺服器的 /api/mp/export 完全一致 ---------- */
  function cell(s) {
    s = String(s == null ? '' : s);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function csv(rec) {
    var lines = [['名次', '學號', '姓名', '組別', '分數', '答對題數', '總題數', '課堂加分'].join(',')];
    rec.players.forEach(function (p, i) {
      lines.push([i + 1, p.sid, p.name, p.team, p.score, p.right, rec.total, p.bonus].map(cell).join(','));
    });
    return '﻿' + lines.join('\r\n') + '\r\n';        // BOM:Excel 直接開不會亂碼
  }
  function filename(rec) {
    return (rec.class_code || 'PULSE') + '-' + stamp(rec.at) + '-成績.csv';
  }
  function download(rec) {
    var blob = new Blob([csv(rec)], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename(rec);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
    mark(rec.id);
    return filename(rec);
  }

  /* ---------- 放榜時掛上去的那一塊 ---------- */
  function onFinal(v) {
    var rec = record(v);
    if (!rec) return null;

    /* 先備份,再處理畫面。這兩件事必須拆開:
       萬一放榜頁的版型改了、找不到掛載的位置,成績也一定要先存下來。 */
    var kept = load().some(function (r) { return r.id === rec.id; });
    var text;
    if (!kept) {
      text = '⚠ 這個瀏覽器不能儲存備份（無痕視窗或空間已滿），<b>請務必手動按「匯出本場成績 CSV」</b>。';
    } else if (rec.exported) {
      text = '這一場已經備份過了。備份留在這台電腦，隨時可以按「歷史成績」補匯出。';
    } else {
      try {
        text = '已自動備份到這台電腦 ✓ <b>' + esc(download(rec)) + '</b>（也留了一份在瀏覽器裡）';
      } catch (e) {
        text = '已存進瀏覽器備份 ✓ 自動下載被擋住了，請按下面的「再下載一次 CSV」。';
      }
    }

    var anchor = document.querySelector('.joinacts') || document.getElementById('app');
    if (!anchor || !anchor.parentNode) return rec;

    var box = document.createElement('div');
    box.className = 'placed';
    box.id = 'pulse-bk';
    box.style.marginTop = '10px';
    box.innerHTML = '<span id="pulse-bk-msg">備份中…</span>' +
      '<div class="row" style="margin-top:8px">' +
      '<button class="btn ghost" type="button" id="pulse-bk-dl">再下載一次 CSV</button>' +
      '<button class="btn ghost" type="button" id="pulse-bk-hist">歷史成績</button></div>';
    anchor.parentNode.insertBefore(box, anchor.nextSibling);

    var msg = box.querySelector('#pulse-bk-msg');
    function say(t) { msg.innerHTML = t; }
    say(text);

    box.querySelector('#pulse-bk-dl').onclick = function () {
      say('已存到下載資料夾 ✓ <b>' + esc(download(rec)) + '</b>');
    };
    box.querySelector('#pulse-bk-hist').onclick = panel;
    return rec;
  }

  /* ---------- 歷史成績面板 ---------- */
  function panel() {
    var old = document.getElementById('pulse-bk-panel');
    if (old) old.remove();
    var rows = load();
    var wrap = document.createElement('div');
    wrap.id = 'pulse-bk-panel';
    wrap.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(9,16,30,.55);' +
      'display:flex;align-items:flex-start;justify-content:center;padding:24px 16px;overflow:auto';
    wrap.innerHTML =
      '<div style="background:var(--paper);color:var(--ink);border:1px solid var(--line);border-radius:14px;' +
      'box-shadow:var(--shadow);max-width:620px;width:100%;padding:20px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px">' +
      '<b style="font-size:1.15rem">歷史成績（這台電腦）</b>' +
      '<button class="btn ghost" type="button" id="pulse-bk-x" style="width:auto;padding:6px 14px">關閉</button></div>' +
      '<p class="note" style="margin:8px 0 14px">保留最近 ' + MAX + ' 場。備份存在這個瀏覽器裡，' +
      '跟伺服器無關——Render 重新部署、考坊關掉了，都還在。換電腦或清瀏覽器資料就會消失。</p>' +
      (rows.length ? '<div id="pulse-bk-rows"></div>' +
        '<div class="row" style="margin-top:14px"><button class="btn ghost" type="button" id="pulse-bk-clear">全部清除</button></div>'
        : '<p class="note">還沒有任何備份。放榜時會自動存進來。</p>') +
      '</div>';
    document.body.appendChild(wrap);

    wrap.onclick = function (e) { if (e.target === wrap) wrap.remove(); };
    wrap.querySelector('#pulse-bk-x').onclick = function () { wrap.remove(); };

    var list = wrap.querySelector('#pulse-bk-rows');
    if (list) {
      rows.forEach(function (r) {
        var row = document.createElement('div');
        row.className = 'entry';
        row.innerHTML = '<span class="who"><b>' + esc(r.class_code || '（沒有班級代碼）') + '</b>' +
          '<small>' + nice(r.at) + '・' + esc(r.category || r.topic) + '・' + r.players.length + ' 人・' +
          r.total + ' 題' + (r.exported ? '' : '・<b style="color:var(--cinnabar)">還沒匯出</b>') + '</small></span>';
        var acts = document.createElement('span');
        acts.style.cssText = 'display:flex;gap:6px;flex-shrink:0';
        var dl = document.createElement('button');
        dl.type = 'button'; dl.className = 'btn ghost';
        dl.style.cssText = 'width:auto;padding:6px 12px;font-size:.88rem';
        dl.textContent = '下載 CSV';
        dl.onclick = function () { download(r); dl.textContent = '已下載 ✓'; };
        var rm = document.createElement('button');
        rm.type = 'button'; rm.className = 'btn ghost';
        rm.style.cssText = 'width:auto;padding:6px 12px;font-size:.88rem';
        rm.textContent = '刪除';
        rm.onclick = function () {
          if (!w.confirm('刪除這一場的備份？沒有匯出過的話就找不回來了。')) return;
          drop(r.id); panel();
        };
        acts.appendChild(dl); acts.appendChild(rm);
        row.appendChild(acts);
        list.appendChild(row);
      });
      wrap.querySelector('#pulse-bk-clear').onclick = function () {
        if (!w.confirm('清除這台電腦上的所有成績備份？這個動作無法復原。')) return;
        store([]); panel();
      };
    }
  }

  /* ---------- 關閉考坊前的確認 ---------- */
  function confirmClose() {
    if (!pending()) return true;
    return w.confirm('還有場次沒有匯出成績。\n\n' +
      '雲端版重新部署或休眠重啟後，伺服器上的成績會歸零。\n' +
      '確定要關閉考坊嗎？（備份還留在這台電腦的「歷史成績」裡）');
  }

  /* ---------- 還有沒匯出的場次時,關分頁先問一聲 ---------- */
  w.addEventListener('beforeunload', function (e) {
    if (!pending()) return;
    e.preventDefault();
    e.returnValue = '';
  });

  /* ---------- 右下角的小入口:有備份才出現 ---------- */
  function mount() {
    if (document.getElementById('pulse-bk-fab')) return;
    var n = load().length;
    if (!n) return;
    var b = document.createElement('button');
    b.id = 'pulse-bk-fab';
    b.type = 'button';
    b.textContent = '歷史成績 ' + n;
    b.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:9998;border:1px solid var(--line);' +
      'background:var(--paper);color:var(--muted);border-radius:999px;padding:8px 14px;font-size:.85rem;' +
      'box-shadow:var(--shadow);cursor:pointer;opacity:.85';
    b.onclick = panel;
    document.body.appendChild(b);
  }
  if (document.readyState === 'loading') w.addEventListener('DOMContentLoaded', mount);
  else mount();

  w.PulseBackup = {
    onFinal: onFinal, panel: panel, confirmClose: confirmClose,
    list: load, pending: pending, download: download, csv: csv, filename: filename
  };
})(window);
