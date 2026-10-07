/* Exercise the real creation helper without a browser or a live HA write. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const sandbox = { HTMLElement: class {}, customElements: { get() { return false; }, define() {} } };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "../custom_components/edc_sharing/frontend/dashboard-generator.js"), "utf8"), sandbox);

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
  console.log("Dashboard creation, collision, authentication, partial save and slug tests passed");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
