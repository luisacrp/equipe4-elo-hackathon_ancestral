/*
 * tracker.js — camada de captura de acessos (protótipo, Portal Petronect)
 * ------------------------------------------------------------------------
 * First-party cookie de identidade (anonymous_id) + session_id com janela
 * de 30 min. Cada pageview vira um POST para o endpoint de captura.
 * Em produção isso entraria como snippet no app React (ver diagrama).
 */
(function () {
  // Em produção (ou em qualquer deploy), o tracker.js é servido pelo mesmo
  // processo que expõe /api/track (ver tracker_server.py), então o padrão
  // certo é "mesma origem de onde este script foi carregado" — nunca
  // localhost fixo. window.PETRONECT_TRACKER_ENDPOINT continua disponível
  // para apontar a um servidor de captura em outro domínio, se necessário.
  var ENDPOINT = window.PETRONECT_TRACKER_ENDPOINT || (location.origin + "/api/track");
  var COOKIE_AID = "_pn_aid";  // identidade do dispositivo — 2 anos
  var COOKIE_SID = "_pn_sid";  // sessão — renovada a cada evento (30 min)

  function getCookie(nome) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + nome + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : null;
  }
  function setCookie(nome, valor, maxAgeSeg) {
    document.cookie = nome + "=" + encodeURIComponent(valor) +
      "; max-age=" + maxAgeSeg + "; path=/; samesite=lax";
  }
  function uuid() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  var anonymousId = getCookie(COOKIE_AID);
  if (!anonymousId) {
    anonymousId = "anon_" + uuid();
    setCookie(COOKIE_AID, anonymousId, 60 * 60 * 24 * 730);
  }

  var sessionId = getCookie(COOKIE_SID);
  var novaSessao = !sessionId;
  if (novaSessao) sessionId = anonymousId + "-S" + Date.now().toString(36);
  setCookie(COOKIE_SID, sessionId, 60 * 30);

  function track(pagina, area, extra) {
    var payload = Object.assign({
      timestamp: new Date().toISOString(),
      anonymous_id: anonymousId,
      session_id: sessionId,
      pagina_entrada: novaSessao ? 1 : 0,
      area: area || "publica",
      pagina: pagina,
      usuario_id: window.PETRONECT_USER_ID || "",
      identificado: window.PETRONECT_USER_ID ? 1 : 0,
      utm_source: new URLSearchParams(location.search).get("utm_source") || "",
      device: /Mobi/i.test(navigator.userAgent) ? "mobile" : "desktop",
    }, extra || {});

    novaSessao = false; // só a primeira chamada desta carga de página conta como entrada

    var body = JSON.stringify(payload);
    if (navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, new Blob([body], { type: "application/json" }));
    } else {
      fetch(ENDPOINT, { method: "POST", headers: { "Content-Type": "application/json" }, body: body, keepalive: true });
    }
  }

  window.petronectTrack = track;
  window.petronectAnonymousId = anonymousId;
  window.petronectSessionId = sessionId;
})();
