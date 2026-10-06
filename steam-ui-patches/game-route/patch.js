// game-route: SteamVR vs Tovakai launch chooser (SharedJSContext).
// steam-frame-nix shape: steamFrame.uiPatches.patches entry targeting SharedJSContext.
// FrameTop owns ft-game-run; this patch owns intercept + UI + temporary launch options.
//
((opts) => {
  const VERSION = 5;
  const NAME = 'game-route';
  const G = window;
  const O = Object.assign({
    wrapperPath: '/home/steamos/dev/frametop/session/ft-game-run',
    launchSourceDefault: 100,
    logLimit: 120,
    enabled: true,
    optionsSettleMs: 400,
    // Steam reads launch options at CreatingProcess (often several seconds after
    // LaunchApp). Restoring too early drops the wrap (proven 2026-10-05).
    restoreAfterMs: 18000,
  }, opts || {});

  if (G.__ftGameRoute?.version === VERSION && G.__ftGameRoute?.name === NAME) {
    return 'unchanged';
  }
  try { G.__ftGameRoute?.dispose?.(); } catch {}

  const Apps = G.SteamClient?.Apps;
  if (!Apps?.RegisterForGameActionStart || !Apps?.CancelGameAction || !Apps?.RunGame) {
    return 'SteamClient.Apps launch APIs missing';
  }

  const log = [];
  const push = (row) => {
    row.t = Date.now();
    log.push(row);
    if (log.length > O.logLimit) log.shift();
    try { console.info('ft-game-route', JSON.stringify(row)); } catch {}
  };

  const bypass = new Set();
  let pending = null; // { gameActionId, gameId, appId, launchSource, name, originalOptions }
  let busy = false;
  let desktopFired = false;
  let popup = null;
  const restoreScheduled = new Set(); // appId
  const wrappedAwaiting = new Set(); // appId — wrap installed, next LaunchApp may proceed

  const appIdOf = (gameId) => {
    try { return Number(BigInt(gameId) & 0xffffffffn); } catch { return Number(gameId) || 0; }
  };

  const wrapOptions = (existing, wrapper) => {
    const e = String(existing || '').trim();
    if (e.indexOf('ft-game-run') >= 0) return e;
    if (e.indexOf('%command%') >= 0) return wrapper + ' ' + e;
    if (!e) return wrapper + ' %command%';
    return wrapper + ' %command% ' + e;
  };

  const getDetails = (appId) => new Promise((resolve, reject) => {
    let done = false;
    const t = setTimeout(() => { if (!done) { done = true; reject(new Error('details timeout')); } }, 4000);
    try {
      const u = Apps.RegisterForAppDetails(appId, (d) => {
        if (done) return;
        done = true; clearTimeout(t);
        try { u?.unregister?.() ?? u?.(); } catch {}
        resolve(d || {});
      });
    } catch (e) {
      done = true; clearTimeout(t); reject(e);
    }
  });

  const classify = async (appId) => {
    let optsList = [];
    try { optsList = await Apps.GetLaunchOptionsForApp(appId) || []; } catch {}
    let details = {};
    try { details = await getDetails(appId); } catch {}
    const flags = (optsList || []).map((o) => !!(o?.bIsVRLaunchOption));
    let classification = 'flat';
    if (details?.vr_only || details?.bVROnly) classification = 'vr_only';
    else if (flags.length && flags.every(Boolean)) classification = 'vr_only';
    else if (flags.some(Boolean) || details?.vr_supported || details?.bVRSupported) classification = 'hybrid';
    return {
      classification,
      name: details?.strDisplayName || ('App ' + appId),
      originalOptions: details?.strLaunchOptions || '',
      optsList,
    };
  };

  const closePopup = () => {
    try {
      if (popup?.id != null && SteamClient.BrowserView?.Destroy) {
        SteamClient.BrowserView.Destroy(popup.id);
      }
    } catch {}
    popup = null;
    try {
      const el = document.getElementById('ft-game-route-modal');
      if (el) el.remove();
    } catch {}
  };

  const ensureDomModal = (title, onPick) => {
    // SharedJS often has no visible document; still try. Primary path is BrowserView popup.
    try {
      if (!document?.body) return false;
      closePopup();
      const root = document.createElement('div');
      root.id = 'ft-game-route-modal';
      root.setAttribute('role', 'dialog');
      root.style.cssText = 'position:fixed;inset:0;z-index:999999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);font-family:system-ui,sans-serif;';
      root.innerHTML = `
        <div style="background:#1b2838;color:#fff;padding:24px 28px;border-radius:8px;min-width:320px;max-width:90vw;box-shadow:0 8px 32px rgba(0,0,0,.45);">
          <div style="font-size:18px;margin-bottom:18px;">Open ${title.replace(/[<>&]/g, '')} in:</div>
          <div style="display:flex;gap:12px;justify-content:center;margin-bottom:16px;">
            <button data-r="steamvr" style="padding:10px 16px;cursor:pointer;">SteamVR</button>
            <button data-r="tovakai" style="padding:10px 16px;cursor:pointer;">Tovakai</button>
          </div>
          <div style="text-align:center;"><button data-r="cancel" style="padding:8px 14px;cursor:pointer;">Cancel</button></div>
        </div>`;
      root.addEventListener('click', (ev) => {
        const b = ev.target?.closest?.('button[data-r]');
        if (!b) return;
        onPick(b.getAttribute('data-r'));
      });
      document.body.appendChild(root);
      root.querySelector('button[data-r="steamvr"]')?.focus?.();
      return true;
    } catch {
      return false;
    }
  };

  const showChooser = (title, onPick) => {
    const html = `<!doctype html><html><head><meta charset=utf-8>
<title>Open in…</title>
<style>
html,body{margin:0;height:100%;background:#0e141b;color:#fff;font-family:system-ui,Segoe UI,sans-serif;}
.wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:24px;box-sizing:border-box;}
h1{font-size:22px;font-weight:600;margin:0 0 22px;text-align:center;}
.row{display:flex;gap:14px;margin-bottom:18px;}
button{font-size:16px;padding:12px 18px;border-radius:6px;border:1px solid #3d4450;background:#2a475e;color:#fff;cursor:pointer;}
button:focus{outline:2px solid #66c0f4;outline-offset:2px;}
button.cancel{background:#1b2838;}
</style></head><body>
<div class=wrap>
  <h1>Open ${String(title).replace(/[<>&]/g,'')} in:</h1>
  <div class=row>
    <button id=steamvr>SteamVR</button>
    <button id=tovakai>Tovakai</button>
  </div>
  <button id=cancel class=cancel>Cancel</button>
</div>
<script>
const send = (r) => { try { SteamClient?.BrowserView?.PostMessageToParent?.(JSON.stringify({ftGameRoute:r})); } catch(e){}
  try { window.opener && window.opener.postMessage({ftGameRoute:r}, '*'); } catch(e){}
  try { location.hash = 'pick=' + r; } catch(e){} };
document.getElementById('steamvr').onclick = () => send('steamvr');
document.getElementById('tovakai').onclick = () => send('tovakai');
document.getElementById('cancel').onclick = () => send('cancel');
document.getElementById('steamvr').focus();
</script></body></html>`;
    const url = 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
    let opened = false;
    try {
      // Try several CreatePopup shapes observed across Steam builds.
      const BV = SteamClient.BrowserView;
      let id = null;
      try { id = BV.CreatePopup(url); opened = id != null; }
      catch { try { id = BV.CreatePopup({ url, strTitle: 'Open in…' }); opened = id != null; } catch {} }
      if (!opened) {
        try { id = BV.Create(url); opened = id != null; } catch {}
      }
      popup = { id };
      push({ event: 'popup', opened, id });
    } catch (e) {
      push({ event: 'popup_err', err: String(e) });
    }
    if (!opened) {
      if (!ensureDomModal(title, onPick)) {
        // Last resort: auto-cancel rather than silent launch.
        push({ event: 'chooser_unavailable' });
        onPick('cancel');
      }
    } else {
      // Poll hash / message bridge from parent.
      const onMsg = (ev) => {
        let data = ev?.data;
        try { if (typeof data === 'string') data = JSON.parse(data); } catch {}
        const r = data?.ftGameRoute;
        if (r === 'steamvr' || r === 'tovakai' || r === 'cancel') {
          window.removeEventListener('message', onMsg);
          onPick(r);
        }
      };
      window.addEventListener('message', onMsg);
      // CDP/manual pick uses the always-on __ftGameRoute.pick
    }
    // Keep pick as the stable API; do not overwrite with a one-shot closure.
  };

  const setLaunchOptions = async (appId, options) => {
    await Apps.SetAppLaunchOptions(appId, options);
  };

  // RunGame ignores launch options (Phase 5 proved only a normal Play path applies
  // %command% wraps). Prefer steam://run so Steam rebuilds the launch line.
  // Call ExecuteSteamURL on the URL object (do not extract — loses `this` → Unknown method).
  const relaunchWithLaunchOptions = (appId, gameId, launchSource) => {
    const urls = [
      'steam://run/' + appId,
      'steam://rungameid/' + gameId,
      'steam://launch/' + appId,
    ];
    let method = 'none';
    const URLApi = G.SteamClient?.URL;
    if (URLApi && typeof URLApi.ExecuteSteamURL === 'function') {
      for (const u of urls) {
        try {
          URLApi.ExecuteSteamURL(u);
          method = 'ExecuteSteamURL:' + u;
          push({ event: 'relaunch', method, appId });
          return method;
        } catch (e) {
          push({ event: 'relaunch_try_err', url: u, err: String(e) });
        }
      }
    } else {
      push({ event: 'relaunch_no_ExecuteSteamURL' });
    }
    // Last resort: stock RunGame (will NOT apply wraps — caller must only use for SteamVR).
    try {
      Apps.RunGame(String(gameId), '', -1, launchSource || O.launchSourceDefault);
      method = 'RunGame_fallback';
      push({ event: 'relaunch', method, appId });
    } catch (e) {
      push({ event: 'relaunch_err', err: String(e) });
    }
    return method;
  };

  const waitWrapped = async (appId, wantSubstring, attempts) => {
    const n = attempts || 8;
    for (let i = 0; i < n; i++) {
      try {
        const d = await getDetails(appId);
        const live = String(d.strLaunchOptions || '');
        if (live.indexOf(wantSubstring) >= 0) return live;
      } catch {}
      await new Promise((r) => setTimeout(r, O.optionsSettleMs));
    }
    return null;
  };

  const enterDesktopMode = () => {
    if (desktopFired) return;
    desktopFired = true;
    push({ event: 'desktop_mode_begin' });
    let method = 'none';
    try {
      SteamClient.OpenVR.VROverlay.ShowDashboard('');
      method = 'ShowDashboard';
    } catch (e) {
      push({ event: 'ShowDashboard_err', err: String(e) });
    }
    try {
      // Best-effort cursor/desktop action set (arity unknown; try common shapes).
      const f = SteamClient.Input.SetCursorActionset;
      try { f(true); method += '+SetCursorActionset(true)'; }
      catch { try { f(1); method += '+SetCursorActionset(1)'; } catch (e2) {
        push({ event: 'SetCursorActionset_err', err: String(e2) });
      } }
    } catch (e) {
      push({ event: 'SetCursorActionset_missing', err: String(e) });
    }
    push({ event: 'desktop_mode_done', method });
  };

  // Keep wrap until Steam has built CreatingProcess (often >2.5s after LaunchApp).
  const scheduleOptionsRestore = (appId) => {
    if (restoreScheduled.has(appId)) return;
    restoreScheduled.add(appId);
    const delay = O.restoreAfterMs || 18000;
    push({ event: 'restore_scheduled', appId, delay });
    setTimeout(async () => {
      try {
        const st = G.__sfuiStore?.get?.(NAME);
        const original = (st && st.appId === appId) ? st.original : '';
        const live = await getDetails(appId);
        if (String(live.strLaunchOptions || '').indexOf('ft-game-run') >= 0) {
          await setLaunchOptions(appId, original == null ? '' : original);
          push({ event: 'options_restored', appId, original });
        } else {
          push({ event: 'options_already_clear', appId });
        }
        try {
          if (st && st.appId === appId) {
            st.pending = false;
            G.__sfuiStore?.set?.(NAME, st);
          }
        } catch {}
      } catch (e) {
        push({ event: 'options_restore_err', err: String(e) });
      } finally {
        restoreScheduled.delete(appId);
      }
    }, delay);
  };

  const finishChoice = async (route) => {
    if (!pending || busy) return;
    busy = true;
    const ctx = pending;
    pending = null;
    closePopup();
    push({ event: 'choice', route, appId: ctx.appId, name: ctx.name });
    try {
      if (route === 'cancel') {
        // Ensure options not left wrapped.
        try { await setLaunchOptions(ctx.appId, ctx.originalOptions); } catch {}
        busy = false;
        return;
      }
      if (route === 'steamvr') {
        try { await setLaunchOptions(ctx.appId, ctx.originalOptions); } catch (e) {
          push({ event: 'restore_err_steamvr', err: String(e) });
          busy = false;
          return;
        }
        bypass.add(String(ctx.gameId));
        bypass.add(String(ctx.appId));
        desktopFired = false;
        Apps.RunGame(String(ctx.gameId), '', -1, ctx.launchSource || O.launchSourceDefault);
        busy = false;
        return;
      }
      // Tovakai — Phase 5 path: wrap launch options, then relaunch via steam://run
      // (Apps.RunGame does not consume SetAppLaunchOptions / %command%).
      const wrapped = wrapOptions(ctx.originalOptions, O.wrapperPath);
      try {
        await setLaunchOptions(ctx.appId, wrapped);
      } catch (e) {
        push({ event: 'wrap_err', err: String(e) });
        try { await setLaunchOptions(ctx.appId, ctx.originalOptions); } catch {}
        busy = false;
        bypass.add(String(ctx.gameId));
        bypass.add(String(ctx.appId));
        Apps.RunGame(String(ctx.gameId), '', -1, ctx.launchSource || O.launchSourceDefault);
        return;
      }
      const live = await waitWrapped(ctx.appId, 'ft-game-run', 10);
      if (!live) {
        push({ event: 'wrap_verify_fail', appId: ctx.appId, wanted: wrapped });
        try { await setLaunchOptions(ctx.appId, ctx.originalOptions); } catch {}
        busy = false;
        return;
      }
      push({ event: 'wrap_ok', appId: ctx.appId, options: live });
      try {
        G.__sfuiStore?.set?.(NAME, {
          schema: 1,
          appId: ctx.appId,
          original: ctx.originalOptions,
          installed: live,
          name: ctx.name,
          ts: Date.now(),
          pending: true,
        });
      } catch {}
      wrappedAwaiting.add(ctx.appId);
      bypass.add(String(ctx.gameId));
      bypass.add(String(ctx.appId));
      desktopFired = false;
      const method = relaunchWithLaunchOptions(ctx.appId, ctx.gameId, ctx.launchSource);
      if (method === 'none' || method === 'RunGame_fallback') {
        // steam:// failed or fell back: keep wrap + bypass and wait for a manual Play.
        push({ event: 'awaiting_play', appId: ctx.appId, reason: method });
      }
      busy = false;
    } catch (e) {
      push({ event: 'finish_err', err: String(e) });
      busy = false;
    }
  };

  const unsubStart = Apps.RegisterForGameActionStart((gameActionId, gameId, action, launchSource) => {
    if (!O.enabled) return;
    const idStr = String(gameId);
    const appId = appIdOf(gameId);
    push({ event: 'start', gameActionId, gameId: idStr, appId, action, launchSource });
    if (action !== 'LaunchApp') return;

    if (bypass.has(idStr) || bypass.has(String(appId))) {
      bypass.delete(idStr);
      bypass.delete(String(appId));
      wrappedAwaiting.delete(appId);
      push({ event: 'bypass_consumed', gameActionId, appId });
      try {
        const st = G.__sfuiStore?.get?.(NAME);
        if (st?.pending && st?.installed && String(st.installed).indexOf('ft-game-run') >= 0) {
          enterDesktopMode();
        }
      } catch {}
      (async () => {
        try {
          const d = await getDetails(appId);
          if (String(d.strLaunchOptions || '').indexOf('ft-game-run') >= 0) {
            enterDesktopMode();
            scheduleOptionsRestore(appId);
          }
        } catch {}
      })();
      return;
    }

    // Sync: wrap already installed and awaiting a Play (no bypass left).
    if (wrappedAwaiting.has(appId)) {
      wrappedAwaiting.delete(appId);
      push({ event: 'wrapped_passthrough', gameActionId, appId });
      enterDesktopMode();
      scheduleOptionsRestore(appId);
      return;
    }

    if (busy || pending) {
      push({ event: 'busy_cancel', gameActionId });
      try { Apps.CancelGameAction(gameActionId); } catch {}
      return;
    }

    // Synchronous cancel before any await.
    try { Apps.CancelGameAction(gameActionId); }
    catch (e) { push({ event: 'cancel_err', err: String(e) }); return; }
    push({ event: 'cancelled', gameActionId, appId });

    busy = true;
    (async () => {
      try {
        const meta = await classify(appId);
        push({ event: 'classified', appId, classification: meta.classification, name: meta.name });
        if (meta.classification === 'vr_only') {
          bypass.add(idStr);
          bypass.add(String(appId));
          Apps.RunGame(idStr, '', -1, launchSource || O.launchSourceDefault);
          busy = false;
          return;
        }
        pending = {
          gameActionId,
          gameId: idStr,
          appId,
          launchSource: launchSource || O.launchSourceDefault,
          name: meta.name,
          originalOptions: meta.originalOptions,
          classification: meta.classification,
        };
        busy = false;
        showChooser(meta.name, (route) => { finishChoice(route); });
      } catch (e) {
        push({ event: 'classify_err', err: String(e) });
        // Fail safe: stock relaunch
        bypass.add(idStr);
        try { Apps.RunGame(idStr, '', -1, launchSource || O.launchSourceDefault); } catch {}
        busy = false;
      }
    })();
  });

  // Crash recovery: if previous session left wrapped options, restore on install.
  (async () => {
    try {
      const st = G.__sfuiStore?.get?.(NAME);
      if (st?.pending && st?.appId && String(st.installed || '').indexOf('ft-game-run') >= 0) {
        const live = await getDetails(st.appId);
        if (String(live.strLaunchOptions || '').indexOf('ft-game-run') >= 0) {
          await setLaunchOptions(st.appId, st.original || '');
          push({ event: 'crash_recovery_restored', appId: st.appId });
        }
        st.pending = false;
        G.__sfuiStore?.set?.(NAME, st);
      }
    } catch (e) {
      push({ event: 'crash_recovery_err', err: String(e) });
    }
  })();

  G.__ftGameRoute = {
    name: NAME,
    version: VERSION,
    log,
    dump: () => log.slice(),
    // Always callable for CDP: finishes only when a chooser is pending.
    pick: (route) => {
      if (!pending) return { ok: false, error: 'no_pending' };
      finishChoice(route);
      return { ok: true, route };
    },
    pending: () => (pending ? { appId: pending.appId, name: pending.name, gameId: pending.gameId } : null),
    dispose: () => {
      try { unsubStart?.unregister?.() ?? unsubStart?.(); } catch {}
      closePopup();
      delete G.__ftGameRoute;
    },
  };
  push({ event: 'armed', version: VERSION, wrapperPath: O.wrapperPath });
  return 'patched';
})(typeof __ftGameRouteOpts === 'undefined' ? {} : __ftGameRouteOpts);
