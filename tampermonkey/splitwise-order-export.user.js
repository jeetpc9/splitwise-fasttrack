// ==UserScript==
// @name         Splitwise FastTrack — Auto sync to app
// @namespace    splitwise-fasttrack
// @version      0.3.1
// @description  Sends visible orders from Amazon, Apollo, Urban Company to Splitwise FastTrack while you browse
// @author       Jeet
// @match        https://www.amazon.in/*
// @match        https://amazon.in/*
// @match        https://www.apollopharmacy.in/*
// @match        https://apollopharmacy.in/*
// @match        https://www.urbancompany.com/*
// @match        https://urbancompany.com/*
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const APP_BASE = "http://127.0.0.1:8765";
  const SCAN_MS = 2000;
  const DEFAULT_SPLIT = "split_half";

  // ── Helpers ───────────────────────────────────────────────────────────────

  function text(el) {
    return (el?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function parseInrAmount(raw) {
    if (!raw) return null;
    const cleaned = raw.replace(/[₹,\s]/g, "").replace(/[^\d.]/g, "");
    const value = parseFloat(cleaned);
    if (!Number.isFinite(value) || value <= 0) return null;
    return value.toFixed(2);
  }

  function parseDateToIso(raw) {
    if (!raw) return new Date().toISOString().slice(0, 10);
    const s = raw.trim();

    // DD/MM/YY or DD/MM/YYYY (Indian default) — e.g. 03/04/26
    let m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
    if (m) {
      const dd = m[1].padStart(2, "0");
      const mm = m[2].padStart(2, "0");
      const yearPart = m[3];
      const yyyy = yearPart.length === 2 ? `20${yearPart}` : yearPart;
      return `${yyyy}-${mm}-${dd}`;
    }

    m = s.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[1]}-${m[2]}-${m[3]}`;
    const months = {
      jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
      jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12",
    };
    m = s.match(/(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})/);
    if (m) {
      const mon = months[m[2].slice(0, 3).toLowerCase()];
      if (mon) return `${m[3]}-${mon}-${m[1].padStart(2, "0")}`;
    }
    if (/today/i.test(s)) return new Date().toISOString().slice(0, 10);
    if (/yesterday/i.test(s)) {
      const d = new Date();
      d.setDate(d.getDate() - 1);
      return d.toISOString().slice(0, 10);
    }
    return new Date().toISOString().slice(0, 10);
  }

  function rowKey(row) {
    return `${row.date}|${row.description}|${row.amount}`;
  }

  // ── Site extractors ───────────────────────────────────────────────────────

  const extractors = [
    {
      id: "amazon-in",
      name: "Amazon India",
      test: () => /amazon\.in/i.test(location.hostname),
      isOrderPage() {
        const path = `${location.pathname}${location.search}`;
        return /\/your-orders\/|order-history|gp\/css\/order-history|\/gp\/your-account\/order/i.test(path);
      },
      extract() {
        if (!this.isOrderPage()) return [];

        const rows = [];
        const seen = new Set();

        function findOrderBlocks() {
          const selectors = [
            ".order-card",
            ".order.js-order-card",
            ".a-box-group.order",
            '[class*="order-card"]',
            "div.order",
          ];
          for (const sel of selectors) {
            const found = [...document.querySelectorAll(sel)];
            if (found.length) return found;
          }

          const placed = [...document.querySelectorAll("span, div, li")].filter((el) => {
            const t = text(el);
            return /^Order placed/i.test(t) && t.length < 80;
          });
          if (!placed.length) return [];

          return placed
            .map((el) => {
              let node = el;
              for (let i = 0; i < 10; i++) {
                if (!node) break;
                if (node.querySelector('a[href*="/dp/"], a[href*="/gp/product/"]')) return node;
                node = node.parentElement;
              }
              return el.closest(".a-box, .a-section, [class*='order']") || el.parentElement?.parentElement;
            })
            .filter(Boolean);
        }

        findOrderBlocks().forEach((block) => {
          const blockText = text(block);

          const dateMatch =
            blockText.match(/Order placed\s+(.+?)(?:\s+Total|\s+Order\s*#|\s+View order|$)/i) ||
            blockText.match(/(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})/);
          const date = parseDateToIso(dateMatch?.[1]?.trim() || dateMatch?.[0] || "");

          const amountMatch =
            blockText.match(/(?:Grand Total|Order Total|Total)[:\s]*₹\s*([\d,]+(?:\.\d{2})?)/i) ||
            blockText.match(/₹\s*([\d,]+(?:\.\d{2})?)/);
          const amount = parseInrAmount(amountMatch?.[0] || amountMatch?.[1]);

          const titleEls = block.querySelectorAll(
            'a[href*="/dp/"], a[href*="/gp/product/"], .yohtmlc-product-title, .a-link-normal'
          );
          let description = "Amazon order";
          const titles = [...titleEls]
            .map((el) => text(el))
            .filter((t) => t.length > 3 && !/^(View|Track|Return|Invoice|Order #)/i.test(t));
          if (titles.length) {
            description = `Amazon — ${[...new Set(titles)].slice(0, 2).join("; ")}`.slice(0, 120);
          }

          const key = rowKey({ date, description, amount });
          if (amount && !seen.has(key)) {
            seen.add(key);
            rows.push({ date, description, amount, split: DEFAULT_SPLIT });
          }
        });

        return rows;
      },
    },
    {
      id: "apollo",
      name: "Apollo Pharmacy",
      test: () => /apollopharmacy\.in/i.test(location.hostname),
      extract() {
        const rows = [];
        const cards = document.querySelectorAll(
          "[class*='order'], [class*='Order'], .order-card, .order-list-item, li[class*='order']"
        );
        cards.forEach((card) => {
          const cardText = text(card);
          const amount = parseInrAmount(cardText);
          if (!amount) return;
          const dateMatch = cardText.match(
            /\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}/
          );
          const date = parseDateToIso(dateMatch?.[0] || "");
          let description = "Apollo Pharmacy order";
          const nameEl = card.querySelector("[class*='product'], [class*='title'], h2, h3, h4");
          if (nameEl) description = `Apollo — ${text(nameEl)}`.slice(0, 120);
          else description = `Apollo — ${cardText.slice(0, 80)}`;
          rows.push({ date, description, amount, split: DEFAULT_SPLIT });
        });
        return rows;
      },
    },
    {
      id: "urban-company",
      name: "Urban Company",
      test: () => /urbancompany\.com/i.test(location.hostname),
      extract() {
        const rows = [];
        const items = document.querySelectorAll(
          "[class*='booking'], [class*='Booking'], [class*='order'], [data-testid*='booking']"
        );
        items.forEach((item) => {
          const itemText = text(item);
          const amount = parseInrAmount(itemText);
          if (!amount) return;
          const dateMatch = itemText.match(
            /\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|Today|Yesterday/i
          );
          const date = parseDateToIso(dateMatch?.[0] || "");
          let description = "Urban Company booking";
          const svc = item.querySelector("[class*='service'], [class*='title'], h2, h3, h4");
          if (svc) description = `Urban Company — ${text(svc)}`.slice(0, 120);
          else description = `Urban Company — ${itemText.slice(0, 80)}`;
          rows.push({ date, description, amount, split: DEFAULT_SPLIT });
        });
        return rows;
      },
    },
  ];

  function activeExtractor() {
    return extractors.find((e) => e.test());
  }

  // ── App sync ──────────────────────────────────────────────────────────────

  let appOnline = false;
  let autoSync = true;
  let sentKeys = new Set(JSON.parse(sessionStorage.getItem("sw-sent-keys") || "[]"));
  let totalSent = 0;

  function persistSentKeys() {
    sessionStorage.setItem("sw-sent-keys", JSON.stringify([...sentKeys].slice(-500)));
  }

  function gmRequest(method, path, body) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method,
        url: `${APP_BASE}${path}`,
        headers: body ? { "Content-Type": "application/json" } : {},
        data: body ? JSON.stringify(body) : undefined,
        timeout: 4000,
        onload(resp) {
          try {
            resolve({ status: resp.status, data: JSON.parse(resp.responseText || "{}") });
          } catch {
            resolve({ status: resp.status, data: {} });
          }
        },
        onerror: () => reject(new Error("Network error")),
        ontimeout: () => reject(new Error("Timeout")),
      });
    });
  }

  async function checkApp() {
    try {
      const resp = await gmRequest("GET", "/api/health");
      appOnline = resp.status === 200 && resp.data.ok;
    } catch {
      appOnline = false;
    }
    updatePanelStatus();
    return appOnline;
  }

  async function sendOrders(orders) {
    const ext = activeExtractor();
    if (!ext || !orders.length) return { added: 0 };

    const fresh = orders.filter((o) => {
      const key = rowKey(o);
      if (sentKeys.has(key)) return false;
      return true;
    });
    if (!fresh.length) return { added: 0 };

    const resp = await gmRequest("POST", "/api/orders", {
      source: ext.name,
      orders: fresh,
    });
    if (resp.status === 200) {
      fresh.forEach((o) => sentKeys.add(rowKey(o)));
      persistSentKeys();
      totalSent += resp.data.added || 0;
    }
    return resp.data;
  }

  async function scanAndSync(force = false) {
    if (!autoSync && !force) return;
    const ext = activeExtractor();
    if (!ext) return;

    if (ext.id === "amazon-in" && !ext.isOrderPage()) {
      updatePanelStatus("Not on order history — open Your Orders");
      return;
    }

    if (!appOnline) {
      await checkApp();
      if (!appOnline) return;
    }

    let orders;
    try {
      orders = ext.extract();
    } catch {
      return;
    }
    if (!orders.length) {
      updatePanelStatus("No orders visible — scroll to load more");
      return;
    }

    try {
      const result = await sendOrders(orders);
      if (result.added > 0) {
        updatePanelStatus(`+${result.added} sent to app (${orders.length} visible)`);
      } else {
        updatePanelStatus(`${orders.length} visible · already synced`);
      }
    } catch {
      appOnline = false;
      updatePanelStatus("App not reachable — open Splitwise FastTrack");
    }
  }

  // ── UI ────────────────────────────────────────────────────────────────────

  GM_addStyle(`
    #sw-sync-panel {
      position: fixed; bottom: 20px; right: 20px; z-index: 2147483646;
      background: #fff; border: 1px solid #c8c5bd; border-radius: 10px;
      box-shadow: 0 8px 28px rgba(0,0,0,.18);
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 13px; color: #1c1b18; width: 290px; padding: 14px 16px;
    }
    #sw-sync-panel h3 { margin: 0 0 6px; font-size: 15px; color: #01696f; }
    #sw-sync-panel .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
    #sw-sync-panel .online { background: #2d6a1e; }
    #sw-sync-panel .offline { background: #9b1b5a; }
    #sw-sync-panel p { margin: 0 0 8px; font-size: 12px; color: #444; line-height: 1.4; }
    #sw-sync-panel label { font-size: 12px; cursor: pointer; }
    #sw-sync-panel button {
      width: 100%; margin-top: 8px; padding: 9px; border: none; border-radius: 6px;
      background: #01696f; color: #fff; font-weight: 600; cursor: pointer; font-size: 12px;
    }
    #sw-sync-status { font-size: 12px; margin-top: 8px; min-height: 32px; color: #2d6a1e; }
  `);

  function panelHint(ext) {
    if (!ext) return "Unsupported site";
    if (ext.id === "amazon-in" && !ext.isOrderPage()) {
      return 'Open <a href="https://www.amazon.in/your-orders/orders" target="_blank">Your Orders</a> — not the homepage.';
    }
    return `${ext.name} — visible orders auto-send to your app.`;
  }

  function updatePanelStatus(extra) {
    const el = document.getElementById("sw-sync-status");
    const dot = document.querySelector("#sw-sync-panel .dot");
    const subtitle = document.getElementById("sw-sync-subtitle");
    if (!el) return;
    if (dot) {
      dot.className = `dot ${appOnline ? "online" : "offline"}`;
    }
    const ext = activeExtractor();
    if (subtitle && ext) {
      subtitle.innerHTML = panelHint(ext);
    }
    el.innerHTML = appOnline
      ? `<strong>${ext?.name || "Site"}</strong><br>${extra || "Watching visible orders…"}<br>${totalSent} total sent this session`
      : `Open <strong>Splitwise FastTrack</strong> on your Mac,<br>then browse order pages here.`;
  }

  function buildPanel() {
    if (document.getElementById("sw-sync-panel")) return;
    const ext = activeExtractor();
    const panel = document.createElement("div");
    panel.id = "sw-sync-panel";
    panel.innerHTML = `
      <h3><span class="dot offline"></span>Splitwise sync</h3>
      <p id="sw-sync-subtitle">${ext ? panelHint(ext) : "Unsupported site"}</p>
      <label><input type="checkbox" id="sw-auto" checked> Auto-sync while I browse</label>
      <button id="sw-sync-now">Sync visible orders now</button>
      <div id="sw-sync-status">Checking app…</div>
    `;
    document.body.appendChild(panel);

    document.getElementById("sw-auto").addEventListener("change", (e) => {
      autoSync = e.target.checked;
      if (autoSync) scanAndSync();
    });
    document.getElementById("sw-sync-now").addEventListener("click", () => scanAndSync(true));
  }

  // ── Auto watch ────────────────────────────────────────────────────────────

  buildPanel();
  checkApp().then(() => scanAndSync());

  setInterval(() => {
    checkApp();
    scanAndSync();
  }, SCAN_MS);

  window.addEventListener("scroll", () => {
    clearTimeout(window._swScrollTimer);
    window._swScrollTimer = setTimeout(scanAndSync, 600);
  }, { passive: true });

  const observer = new MutationObserver(() => {
    clearTimeout(window._swMutTimer);
    window._swMutTimer = setTimeout(scanAndSync, 800);
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
