/* Exercise the real creation helper without a browser or a live HA write. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const sandbox = { HTMLElement: class {}, customElements: { get() { return false; }, define() {} } };
vm.createContext(sandbox);
const source = fs.readFileSync(path.join(__dirname, "../custom_components/edc_sharing/frontend/dashboard-generator.js"), "utf8");
vm.runInContext(source, sandbox);

/* Execute real panel initialization: the return link must not depend on
 * browser history, a successful API call, admin access or a wide screen.
 */
class TestNode {
  constructor(tag = "div", attrs = "") {
    this.tag = tag; this.children = []; this.ids = {}; this.listeners = {}; this.dataset = {};
    this.id = attrs.match(/\bid="([^"]*)"/)?.[1];
    this.href = attrs.match(/\bhref="([^"]*)"/)?.[1] || "";
    this.checked = /\bchecked\b/.test(attrs); this.disabled = /\bdisabled\b/.test(attrs);
    this.value = "";
    for (const match of attrs.matchAll(/data-([\w-]+)="([^"]*)"/g)) this.dataset[match[1]] = match[2];
  }
  set innerHTML(value) {
    this.html = value; this.children = []; this.ids = {};
    for (const match of value.matchAll(/<([\w-]+)\b([^>]*?)>/g)) {
      const node = new TestNode(match[1], match[2]); this.children.push(node);
      if (node.id) this.ids[node.id] = node;
    }
  }
  getElementById(id) { return this.ids[id]; }
  querySelector(tag) { return this.children.find(node => node.tag === tag); }
  querySelectorAll() { return this.children.filter(node => node.dataset.text); }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
}

async function navigationTest() {
  for (const scenario of [
    { language: "cs", narrow: true, admin: true, fail: false, label: "Zpět do integrace" },
    { language: "en", narrow: false, admin: true, fail: true, label: "Back to integration" },
    { language: "en", narrow: true, admin: false, fail: false, label: "Back to integration" },
  ]) {
    const components = new Map(); const calls = [];
    const context = {
      HTMLElement: class { constructor() { this.isConnected = true; } attachShadow() { this.shadowRoot = new TestNode(); } },
      customElements: { get: key => components.get(key), define: (key, component) => components.set(key, component) },
      window: { location: { search: "" }, history: { back() { throw new Error("Do not rely on browser history"); } } },
    };
    vm.createContext(context); vm.runInContext(source, context);
    const Component = components.get("edc-sharing-dashboard-generator-v1");
    const component = new Component(); component.narrow = scenario.narrow;
    component.hass = { language: scenario.language, user: { is_admin: scenario.admin }, async callWS(message) {
      calls.push(message); if (scenario.fail) throw new Error("offline"); return [];
    } };
    await new Promise(resolve => setImmediate(resolve));
    const back = component._get("back");
    assert.ok(back, "The generator needs a permanent return link");
    assert.equal(back.tag, "a");
    assert.equal(back.href, "/config/integrations/integration/edc_sharing");
    assert.ok(component.shadowRoot.children.some(node => node.dataset.text === "back" && node.textContent === scenario.label));
    component._setBusy(true);
    assert.equal(back.disabled, false, "Returning must remain possible while a request is pending");
    assert.ok(calls.every(call => call.type === "edc_sharing/dashboard/groups"));
  }
  console.log("Dashboard navigation: localized native return link survives mobile, empty groups, offline and unauthorized states");
}

async function main() {
  const request = { title: "Example EDC", url_path: "edc-example", require_admin: true, config: { title: "Example EDC", views: [] } };
  const calls = [];
  const api = async message => {
    calls.push(message);
    return message.type.endsWith("/list") ? [] : { id: "edc-example", url_path: "edc-example" };
  };
  await sandbox.createNewEdcDashboard(api, request);
  assert.deepEqual(calls.map(call => call.type), ["lovelace/dashboards/list", "lovelace/dashboards/create", "lovelace/config/save"]);
  assert.equal(calls[1].require_admin, true);
  assert.equal(calls[2].url_path, "edc-example");
  assert.equal(calls[2].config, request.config);

  const collision = [];
  await assert.rejects(sandbox.createNewEdcDashboard(async message => {
    collision.push(message);
    return [{ url_path: "edc-example", mode: "yaml" }];
  }, request), /dashboard_exists/);
  assert.equal(collision.length, 1);

  const failure = [];
  await assert.rejects(sandbox.createNewEdcDashboard(async message => {
    failure.push(message.type);
    if (message.type === "lovelace/dashboards/list") return [];
    if (message.type === "lovelace/config/save") throw new Error("storage error");
    if (message.type === "lovelace/config") throw new Error("config_not_found");
    return {};
  }, request), /dashboard_partial/);
  assert.equal(failure.some(type => type.endsWith("/delete")), false);

  const recovered = await sandbox.createNewEdcDashboard(async message => {
    if (message.type === "lovelace/dashboards/list") return [];
    if (message.type === "lovelace/config/save") throw new Error("response lost");
    if (message.type === "lovelace/config") return { views: [], title: "Example EDC" };
    return {};
  }, request);
  assert.equal(recovered.url_path, "edc-example");

  let mutations = 0;
  await assert.rejects(sandbox.createNewEdcDashboard(async () => { mutations++; }, { ...request, url_path: "lovelace" }), /invalid_path/);
  assert.equal(mutations, 0);
  await assert.rejects(sandbox.createNewEdcDashboard(async () => { throw new Error("unauthorized"); }, request), /unauthorized/);
  assert.equal(sandbox.edcDashboardPath("Sdílení elektřiny"), "edc-sdileni-elektriny");
  assert.equal(sandbox.edcDashboardPath("<script>"), "edc-script");
  await navigationTest();
  console.log("Dashboard creation, collision, authentication, partial save and slug tests passed");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
