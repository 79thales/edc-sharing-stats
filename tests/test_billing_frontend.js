/* Pure frontend helpers, date boundaries and no unescaped HTML regression. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("custom_components/edc_sharing/frontend/billing.js", "utf8");
const context = { HTMLElement: class {}, customElements: { get() {}, define() {} }, Date, Math };
vm.createContext(context); vm.runInContext(source, context);
const helpers = context.EDC_BILLING_HELPERS;
const normalize = value => JSON.parse(JSON.stringify(value));
assert.deepEqual(normalize(helpers.period("month", "2026-01-05", "")), { start: "2025-12-01", end: "2025-12-31" });
assert.deepEqual(normalize(helpers.period("month", "2028-03-05", "")), { start: "2028-02-01", end: "2028-02-29" });
assert.deepEqual(normalize(helpers.period("year", "2026-10-07", "2026-10-05")), { start: "2026-01-01", end: "2026-10-05" });
assert.equal(helpers.period("custom", "2026-10-07", ""), null);
assert.equal(helpers.escape('<img src="x" onerror="bad()">&'), "&lt;img src=&quot;x&quot; onerror=&quot;bad()&quot;&gt;&amp;");
assert.ok(source.includes('sandbox="allow-same-origin allow-modals"'));
assert.ok(!source.includes("allow-scripts"));
assert.ok(source.includes('querySelectorAll("button,input,select")'));
assert.ok(source.includes("this._pending.request_id"));
assert.ok(source.includes('this._el("issue-confirm").checked'));
assert.ok(source.includes('this._el("send-confirm").checked'));
assert.ok(source.includes('this._el("payment-confirm").checked'));
console.log("Billing helpers: calendar periods, escaping, preview confirmation and stable retry IDs passed");

/* Execute the real component handlers with a tiny DOM/service test double.
 * This is a controller test, not a claim of live-browser or SMTP delivery QA.
 */
class TestNode {
  constructor(tag = "div", attrs = "") {
    this.tag = tag; this.children = []; this.listeners = {}; this.dataset = {};
    this.value = attrs.match(/value="([^"]*)"/)?.[1] || "";
    this.checked = /\bchecked\b/.test(attrs); this.disabled = /\bdisabled\b/.test(attrs);
    this.textContent = ""; this.hidden = /\bhidden\b/.test(attrs);
    for (const match of attrs.matchAll(/data-([\w-]+)="([^"]*)"/g)) this.dataset[match[1]] = match[2];
    this.id = attrs.match(/\bid="([^"]*)"/)?.[1];
    this.href = attrs.match(/\bhref="([^"]*)"/)?.[1] || "";
    this.contentWindow = { print() {} };
  }
  set innerHTML(value) {
    this._html = value; this.children = []; this.ids = {};
    for (const match of value.matchAll(/<([\w-]+)\b([^>]*?)>/g)) {
      const node = new TestNode(match[1], match[2]); this.children.push(node);
      if (node.id) this.ids[node.id] = node;
    }
    if (this.ids.period) this.ids.period.value = "month";
  }
  get innerHTML() { return this._html || ""; }
  getElementById(id) { return this.ids[id]; }
  querySelector(selector) { return this.children.find(node => node.tag === selector); }
  querySelectorAll(selector) {
    if (selector.startsWith("[data-")) return this.children.filter(node => node.dataset[selector.slice(6, -1)] !== undefined);
    return this.children.filter(node => selector.split(",").includes(node.tag));
  }
  append(node) { this.children.push(node); if (this.tag === "select" && this.children.length === 1) this.value = node.value; }
  replaceChildren() { this.children = []; this.value = ""; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  async trigger(type) { if (!this.disabled) for (const handler of this.listeners[type] || []) await handler(); }
  scrollIntoView() {}
}

async function navigationTest() {
  for (const scenario of [
    { language: "cs", narrow: true, admin: true, fail: false },
    { language: "en", narrow: false, admin: true, fail: true },
    { language: "en", narrow: true, admin: false, fail: false },
  ]) {
    const components = new Map(); const calls = [];
    const sandbox = {
      HTMLElement: class { constructor() { this.isConnected = true; } attachShadow() { this.shadowRoot = new TestNode(); } },
      customElements: { get: key => components.get(key), define: (key, value) => components.set(key, value) },
      window: { history: { back() { throw new Error("Do not rely on browser history"); } } },
      location: { search: "" }, URLSearchParams, Date, Math,
    };
    vm.createContext(sandbox); vm.runInContext(source, sandbox);
    const Component = components.get("edc-sharing-billing-v1");
    const component = new Component(); component.narrow = scenario.narrow;
    component.hass = { language: scenario.language, user: { is_admin: scenario.admin }, async callWS(message) {
      calls.push(message); if (scenario.fail) throw new Error("offline"); return [];
    } };
    while (component._busy) await new Promise(resolve => setImmediate(resolve));
    const back = component._el("back");
    assert.ok(back, "Returning must work even if billing cannot load");
    assert.equal(back.href, "/config/integrations/integration/edc_sharing");
    assert.equal(back.disabled, false);
    assert.ok(calls.every(call => call.type === "edc_sharing/billing/groups"));
  }
  console.log("Billing navigation: return link survives mobile, empty groups, offline and unauthorized states");
}

async function controllerTest(language) {
  const components = new Map();
  const calls = [];
  const overview = {
    revision: 0, today: "2026-10-07", latest_day: "2026-10-05",
    settings: { issuer: "", issuer_address: "", tracking: false },
    profiles: [], documents: [], payments: [],
    balance: { total: "0.00", confirmed: "0.00", remaining: "0.00", ambiguous: [] },
  };
  const html = '<html><body><p>Example customer / EAN EAN-A</p></body></html>';
  const doc = {
    id: "document-1", number: "EDC-2026-000001", recipient: "Example customer",
    start: "2026-09-01", end: "2026-09-30", total: "60.00", charge_keys: ["charge-1"],
    charges: { "charge-1": { ean: "EAN-A", name: "Example", day: "2026-09-01" } },
    balance: { total: "60.00", confirmed: "0.00", remaining: "60.00", ambiguous: [] },
    payment_status: "unconfirmed", deliveries: [], html,
  };
  const sandbox = {
    HTMLElement: class { constructor() { this.isConnected = true; } attachShadow() { this.shadowRoot = new TestNode(); } },
    customElements: { get: key => components.get(key), define: (key, value) => components.set(key, value) },
    document: { createElement: tag => new TestNode(tag) },
    window: { confirm: () => true }, location: { search: "?entry_id=entry-1" },
    URLSearchParams, Date, Math,
  };
  vm.createContext(sandbox); vm.runInContext(source, sandbox);
  const Component = components.get("edc-sharing-billing-v1");
  const component = new Component();
  component.hass = {
    user: { is_admin: true }, language, states: { "notify.example": { attributes: { friendly_name: "Example recipient" } } },
    async callWS(message) {
      calls.push(normalize(message));
      if (message.type === "edc_sharing/billing/groups") return [{ entry_id: "entry-1", name: "Example group" }];
      if (message.action === "overview") return normalize(overview);
      if (message.action === "settings") { overview.settings = { issuer: message.payload.issuer, issuer_address: message.payload.issuer_address, tracking: message.payload.tracking }; overview.revision++; return { revision: overview.revision }; }
      if (message.action === "preview") return { ...message.payload, preview_id: "server-preview", can_issue: true, smtp_ready: true, balance: doc.balance, missing_days: {}, inconsistent_days: [], html };
      if (message.action === "issue") { overview.documents = [doc]; overview.balance = doc.balance; overview.revision++; return normalize(doc); }
      if (message.action === "send") { doc.deliveries.push({ request_id: message.payload.request_id, status: "handed_to_smtp", successful: 1, failed_or_uncertain: 0 }); overview.revision++; return normalize(doc); }
      if (message.action === "payment") { doc.balance = { total: "60.00", confirmed: "20.00", remaining: "40.00", ambiguous: [] }; doc.payment_status = "partial"; overview.balance = doc.balance; overview.revision++; return { revision: overview.revision }; }
      if (message.action === "document") return normalize(doc);
      throw new Error("Unexpected controller request");
    },
  };
  while (component._busy) await new Promise(resolve => setImmediate(resolve));
  const el = id => component.shadowRoot.getElementById(id);
  assert.ok(el("back"), "Billing needs a return link even without profiles");
  assert.equal(el("back").tag, "a");
  assert.equal(el("back").href, "/config/integrations/integration/edc_sharing");
  assert.ok(component.shadowRoot.children.some(node => node.dataset.text === "back" && node.textContent === (language === "cs" ? "Zpět do integrace" : "Back to integration")));
  assert.equal(el("profile-gate").hidden, false);
  assert.equal(el("draft-card").hidden, true);
  assert.equal(calls.filter(call => ["issue", "send", "payment"].includes(call.action)).length, 0);
  overview.profiles = [{ id: "profile-1", name: "Example profile", targets: ["notify.example"], smtp_ready: true }];
  await el("refresh").trigger("click");
  assert.equal(el("draft-card").hidden, false);
  el("issuer").value = "Example supplier"; el("tracking").checked = true;
  await el("save").trigger("click");
  await el("preview").trigger("click");
  assert.equal(el("preview-frame").srcdoc, html);
  assert.equal(calls.find(call => call.action === "preview").payload.allow_missing, false);
  el("allow-missing").checked = true;
  await el("allow-missing").trigger("input");
  assert.equal(el("preview-card").hidden, true);
  await el("preview").trigger("click");
  assert.equal(calls.filter(call => call.action === "preview").at(-1).payload.allow_missing, true);
  assert.equal(el("issue").disabled, true);
  await el("issue").trigger("click");
  assert.equal(calls.filter(call => call.action === "issue").length, 0);
  el("issue-confirm").checked = true; await el("issue-confirm").trigger("change");
  await el("issue").trigger("click");
  assert.equal(el("document-frame").srcdoc, html);
  assert.equal(calls.filter(call => call.action === "send").length, 0);
  assert.equal(el("payment-box").hidden, false);
  el("send-confirm").checked = true; await el("send-confirm").trigger("change");
  await el("send").trigger("click");
  assert.equal(calls.filter(call => call.action === "send").length, 1);
  assert.equal(component._doc.balance.remaining, "60.00");
  el("amount").value = "20,00"; el("payment-confirm").checked = true; await el("payment-confirm").trigger("change");
  await el("record").trigger("click");
  assert.equal(calls.find(call => call.action === "payment").payload.amount, "20.00");
  assert.equal(component._doc.balance.remaining, "40.00");
  // Retrying a lost response keeps the exact mutation ID and revision.
  let attempts = 0; const retries = [];
  component._hass.callWS = async message => { retries.push(message); if (++attempts === 1) throw new Error("lost response"); return {}; };
  await assert.rejects(component._mutate("send", { document_id: "document-1" }));
  await component._mutate("send", { document_id: "document-1" });
  assert.equal(retries[0].payload.request_id, retries[1].payload.request_id);
  assert.equal(retries[0].revision, retries[1].revision);
  assert.equal(el("back").disabled, false);
  console.log("Billing controller: profile-first gate, complete preview, explicit issue/send/payment and lost-response retry passed");
}
navigationTest().then(() => controllerTest("cs")).then(() => controllerTest("en")).catch(error => { console.error(error); process.exitCode = 1; });
