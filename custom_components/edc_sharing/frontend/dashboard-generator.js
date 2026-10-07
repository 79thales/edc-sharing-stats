/* Local-only generator. Uses the current HA user's connection; no tokens, CDN or telemetry. */

function edcDashboardPath(title) {
  const slug = String(title).normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return (`edc-${slug || "share"}`).slice(0, 80).replace(/-$/g, "");
}

function edcSameConfig(left, right) {
  const canonical = value => Array.isArray(value) ? value.map(canonical)
    : value && typeof value === "object"
      ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
      : value;
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

async function createNewEdcDashboard(callWS, request) {
  const path = request.url_path;
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)+$/.test(path) || path.length > 80
      || path === "edc-sharing-dashboard" || !request.title.trim() || !request.config?.views) {
    throw new Error("invalid_path");
  }
  // Never save to an existing dashboard, including YAML dashboards or Overview.
  const dashboards = await callWS({ type: "lovelace/dashboards/list" });
  if (dashboards.some(item => item.url_path === path)) throw new Error("dashboard_exists");
  await callWS({
    type: "lovelace/dashboards/create", url_path: path, title: request.title,
    icon: "mdi:transmission-tower-export", show_in_sidebar: true,
    require_admin: request.require_admin,
  });
  try {
    await callWS({ type: "lovelace/config/save", url_path: path, config: request.config });
  } catch {
    // A lost response does not prove the save failed. Check before reporting it.
    try {
      const saved = await callWS({ type: "lovelace/config", url_path: path });
      if (edcSameConfig(saved, request.config)) return { url_path: path };
    } catch { /* Preserve the newly created dashboard and offer YAML; never delete user data. */ }
    const error = new Error("dashboard_partial");
    error.url_path = path;
    throw error;
  }
  return { url_path: path };
}

const EDC_DASHBOARD_TEXT = {
  cs: {
    heading: "EDC – generátor dashboardu", intro: "Stejný styl jako EDC Share2: barevné dlaždice, ukazatele procent, historie a detaily. Pouze nativní karty Home Assistantu.",
    group: "Skupina sdílení", title: "Název dashboardu", path: "Adresa dashboardu (musí obsahovat pomlčku)",
    language: "Jazyk dashboardu", targets: "Zahrnout jednotlivá odběrná místa a jejich vlastní ceny",
    details: "Přidat stránku detailů", energy: "Přidat tabulku nákupu a prodeje ze stávajícího Energy",
    mode: "Výstup", yamlMode: "Vygenerovat YAML", createMode: "Přímo založit nový dashboard",
    admin: "Nový dashboard zobrazovat jen správcům", preview: "Vygenerovat náhled a YAML",
    confirm: "Potvrzuji založení nového dashboardu. Existující dashboardy se nezmění.",
    create: "Založit dashboard", copy: "Kopírovat YAML", download: "Stáhnout YAML",
    empty: "Nejsou dostupné žádné nakonfigurované skupiny EDC.", unauthorized: "Generátor a přímé založení jsou dostupné pouze správci Home Assistantu.",
    ready: "Náhled je připraven. V YAML režimu nebylo do HA nic zapsáno.", success: "Dashboard byl vytvořen.",
    copied: "YAML byl zkopírován.", copyFailed: "Automatické kopírování není dostupné (např. přes HTTP). YAML je označený; použijte Ctrl+C nebo stažení.",
    invalid: "Zkontrolujte název a adresu: malá písmena, číslice, alespoň jedna pomlčka, nejvýše 80 znaků.",
    collision: "Tato adresa už existuje. Vyberte jinou; stávající dashboard se nikdy nepřepisuje.",
    partial: "Dashboard byl založen, ale uložení obsahu není potvrzené. Dashboard zůstává zachovaný. Otevřete jej a případně vložte vygenerovaný YAML ručně; opakované založení jej nepřepíše.",
    failed: "Akci se nepodařilo dokončit. Zkontrolujte připojení a dostupnost Lovelace; YAML můžete stále stáhnout.",
    warning: "Některé senzory zatím nejsou dostupné nebo jsou vypnuté. Generátor je vynechal. Po jejich zpřístupnění vygenerujte dashboard znovu pod novým názvem nebo použijte YAML.",
    summary: "Počet pohledů / odběrných míst:", open: "Otevřít dashboard", yamlLabel: "Celá konfigurace dashboardu (YAML)",
    note: "EDC data jsou obvykle zpožděná asi o jeden den. Historické grafy používají původní EDC datum. Energy tabulka používá celkovou konfiguraci domu, nikoli jen vybranou skupinu. Generátor nemění Energy, ceny, reporty ani historii.",
    steps: "YAML: Nastavení → Ovládací panely → nový prázdný dashboard → Upravit dashboard → Editor surové konfigurace. Vložte celý YAML. Není to konfigurace jediné karty ani jediného pohledu.",
  },
  en: {
    heading: "EDC dashboard generator", intro: "The EDC Share2 style: colored tiles, percentage gauges, history and details. Native Home Assistant cards only.",
    group: "Sharing group", title: "Dashboard name", path: "Dashboard URL path (must include a hyphen)",
    language: "Dashboard language", targets: "Include individual supply points and their own prices",
    details: "Include a details page", energy: "Include the purchase/sale table from existing Energy settings",
    mode: "Output", yamlMode: "Generate YAML", createMode: "Create a new dashboard directly",
    admin: "Show the new dashboard only to administrators", preview: "Generate preview and YAML",
    confirm: "I confirm creation of a new dashboard. Existing dashboards will not be changed.",
    create: "Create dashboard", copy: "Copy YAML", download: "Download YAML",
    empty: "No configured EDC groups are available.", unauthorized: "The generator and direct creation require a Home Assistant administrator.",
    ready: "Preview ready. YAML generation has not written anything to HA.", success: "Dashboard created.",
    copied: "YAML copied.", copyFailed: "Automatic copying is unavailable (for example over HTTP). YAML is selected; use Ctrl+C or download it.",
    invalid: "Check the name and path: lowercase letters, digits, at least one hyphen, at most 80 characters.",
    collision: "This URL already exists. Choose another; existing dashboards are never overwritten.",
    partial: "The dashboard was created but its content has not been confirmed saved. It has been preserved. Open it and paste the generated YAML manually if needed; retrying creation will not overwrite it.",
    failed: "The action could not be completed. Check the connection and Lovelace availability; you can still download the YAML.",
    warning: "Some sensors are not yet registered or are disabled and were omitted. After enabling them, generate a new dashboard under another name or use YAML.",
    summary: "Number of views / supply points:", open: "Open dashboard", yamlLabel: "Complete dashboard configuration (YAML)",
    note: "EDC data is typically delayed by about one day. History charts use the original EDC date. The Energy table uses the home's overall configuration, not just this group. The generator does not change Energy, prices, reports or history.",
    steps: "YAML: Settings → Dashboards → new empty dashboard → Edit dashboard → Raw configuration editor. Paste the complete YAML. This is not a single-card or single-view configuration.",
  },
};

class EdcSharingDashboardGenerator extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._preview = null;
    this._busy = false;
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this._initialized) this._initialize();
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = value;
  }

  set narrow(value) {
    this._narrow = value;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = value;
  }

  connectedCallback() {
    if (this._hass && !this._initialized) this._initialize();
  }

  _initialize() {
    this._initialized = true;
    this._text = EDC_DASHBOARD_TEXT[this._hass.language?.startsWith("cs") ? "cs" : "en"];
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;height:100%;overflow:auto;color:var(--primary-text-color);background:var(--primary-background-color);font-family:var(--paper-font-body1_-_font-family, sans-serif)}
        header{display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff)}
        h1{font-size:20px;margin:0}main{max-width:1000px;margin:auto;padding:20px}.card{padding:20px;margin:0 0 20px;border:1px solid var(--divider-color);border-radius:var(--ha-card-border-radius,12px);background:var(--ha-card-background,var(--card-background-color));box-shadow:var(--ha-card-box-shadow,none)}
        .fields{display:grid;grid-template-columns:1fr 1fr;gap:16px}label.field{display:flex;flex-direction:column;gap:6px}input,select,textarea{box-sizing:border-box;font:inherit;color:var(--primary-text-color);background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:6px;padding:10px;min-width:0}input[type=checkbox]{accent-color:var(--primary-color);width:20px;height:20px;vertical-align:middle;margin-right:10px}
        .check{display:flex;align-items:center;margin:14px 0;line-height:1.5}.actions{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}button{font:inherit;cursor:pointer;padding:12px 18px;border:0;border-radius:24px;color:var(--text-primary-color,#fff);background:var(--primary-color)}button:disabled{opacity:.45;cursor:default}button.secondary{color:var(--primary-color);background:var(--secondary-background-color)}textarea{width:100%;height:420px;font-family:monospace;font-size:13px}p{line-height:1.5}.muted{color:var(--secondary-text-color)}[hidden]{display:none!important}#status{white-space:pre-wrap}a{color:var(--primary-color)}@media(max-width:650px){main{padding:12px}.fields{grid-template-columns:1fr}.card{padding:16px}}
      </style>
      <header><ha-menu-button></ha-menu-button><h1 data-text="heading"></h1></header>
      <main><div class="card"><p data-text="intro"></p><div class="fields">
        <label class="field"><span data-text="group"></span><select id="group"></select></label>
        <label class="field"><span data-text="title"></span><input id="title" maxlength="120"></label>
        <label class="field"><span data-text="path"></span><input id="path" maxlength="80" spellcheck="false"></label>
        <label class="field"><span data-text="language"></span><select id="language"><option value="cs">Čeština</option><option value="en">English</option></select></label>
      </div>
      <label class="check"><input id="targets" type="checkbox" checked><span data-text="targets"></span></label>
      <label class="check"><input id="details" type="checkbox" checked><span data-text="details"></span></label>
      <label class="check"><input id="energy" type="checkbox"><span data-text="energy"></span></label>
      <label class="field"><span data-text="mode"></span><select id="mode"><option value="yaml" data-text="yamlMode"></option><option value="create" data-text="createMode"></option></select></label>
      <div id="create-options" hidden><label class="check"><input id="admin" type="checkbox" checked><span data-text="admin"></span></label></div>
      <div class="actions"><button id="preview" data-text="preview" disabled></button></div>
      <p class="muted" data-text="note"></p></div>
      <div class="card" id="result" hidden><p id="summary"></p><p id="warning" hidden data-text="warning"></p>
        <label class="field"><span data-text="yamlLabel"></span><textarea id="yaml" readonly spellcheck="false"></textarea></label>
        <div class="actions"><button id="copy" class="secondary" data-text="copy"></button><button id="download" class="secondary" data-text="download"></button></div>
        <p class="muted" data-text="steps"></p>
        <div id="confirmation" hidden><label class="check"><input id="confirm" type="checkbox"><span data-text="confirm"></span></label><button id="create" data-text="create" disabled></button></div>
      </div><div class="card" id="status-box" hidden><p id="status" role="status" aria-live="polite"></p><a id="open" hidden data-text="open"></a></div></main>`;
    this.shadowRoot.querySelectorAll("[data-text]").forEach(element => {
      element.textContent = this._text[element.dataset.text];
    });
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;
    this._get("language").value = this._hass.language?.startsWith("cs") ? "cs" : "en";
    for (const id of ["group", "title", "path", "language", "targets", "details", "energy"]) {
      this._get(id).addEventListener("input", () => {
        if (id === "title" && !this._manualPath) this._get("path").value = edcDashboardPath(this._get("title").value);
        if (id === "path") this._manualPath = true;
        this._invalidate();
      });
    }
    this._get("mode").addEventListener("change", () => this._syncMode());
    this._get("confirm").addEventListener("change", () => this._syncMode());
    this._get("preview").addEventListener("click", () => this._generate());
    this._get("create").addEventListener("click", () => this._create());
    this._get("copy").addEventListener("click", () => this._copy());
    this._get("download").addEventListener("click", () => this._download());
    this._loadGroups();
  }

  _get(id) { return this.shadowRoot.getElementById(id); }

  _status(message, path = null) {
    this._get("status-box").hidden = false;
    this._get("status").textContent = message;
    this._get("open").hidden = !path;
    if (path) this._get("open").href = `/${path}/overview`;
  }

  _invalidate() {
    this._preview = null;
    this._get("result").hidden = true;
    this._get("confirm").checked = false;
    this._syncMode();
  }

  _syncMode() {
    const create = this._get("mode").value === "create";
    this._get("create-options").hidden = !create;
    this._get("confirmation").hidden = !create;
    this._get("create").disabled = this._busy || !this._preview || !this._get("confirm").checked;
  }

  _setBusy(value) {
    this._busy = value;
    for (const id of ["group", "title", "path", "language", "targets", "details", "energy", "mode", "admin", "preview"]) {
      this._get(id).disabled = value;
    }
    this._syncMode();
  }

  async _loadGroups() {
    if (!this._hass.user?.is_admin) { this._status(this._text.unauthorized); return; }
    try {
      const groups = await this._hass.callWS({ type: "edc_sharing/dashboard/groups" });
      if (!groups.length) { this._status(this._text.empty); return; }
      for (const group of groups) {
        const option = document.createElement("option");
        option.value = group.entry_id;
        option.textContent = group.name;
        this._get("group").append(option);
      }
      const selected = new URLSearchParams(window.location.search).get("entry_id");
      if (groups.some(group => group.entry_id === selected)) this._get("group").value = selected;
      this._get("title").value = "EDC Share";
      this._get("path").value = edcDashboardPath(this._get("title").value);
      this._get("preview").disabled = false;
    } catch { this._status(this._text.failed); }
  }

  async _generate() {
    if (this._busy) return;
    this._setBusy(true);
    this._invalidate();
    const request = {
      type: "edc_sharing/dashboard/preview", entry_id: this._get("group").value,
      title: this._get("title").value.trim(), url_path: this._get("path").value,
      language: this._get("language").value, include_targets: this._get("targets").checked,
      include_details: this._get("details").checked, include_energy: this._get("energy").checked,
    };
    try {
      const response = await this._hass.callWS(request);
      this._preview = { ...response, title: request.title, url_path: request.url_path };
      this._get("yaml").value = response.yaml;
      this._get("summary").textContent = `${this._text.summary} ${response.config.views.length} / ${response.target_count}`;
      this._get("warning").hidden = !response.missing_entities.length;
      this._get("result").hidden = false;
      this._status(this._text.ready);
    } catch (error) {
      this._status(["invalid_title", "invalid_path", "invalid_format"].includes(error.code) ? this._text.invalid : this._text.failed);
    } finally { this._setBusy(false); }
  }

  async _create() {
    if (this._busy || !this._preview || !this._get("confirm").checked || this._get("mode").value !== "create") return;
    this._setBusy(true);
    try {
      const result = await createNewEdcDashboard(message => this._hass.callWS(message), {
        ...this._preview, require_admin: this._get("admin").checked,
      });
      this._status(this._text.success, result.url_path);
      this._get("confirm").checked = false;
    } catch (error) {
      this._status(error.message === "dashboard_exists" ? this._text.collision
        : error.message === "dashboard_partial" ? this._text.partial : this._text.failed, error.url_path);
      this._get("confirm").checked = false;
    } finally { this._setBusy(false); }
  }

  async _copy() {
    try {
      await navigator.clipboard.writeText(this._get("yaml").value);
      this._status(this._text.copied);
    } catch {
      this._get("yaml").focus();
      this._get("yaml").select();
      this._status(this._text.copyFailed);
    }
  }

  _download() {
    if (!this._preview) return;
    const url = URL.createObjectURL(new Blob([this._get("yaml").value], { type: "application/yaml;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${this._preview.url_path}.yaml`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

if (!customElements.get("edc-sharing-dashboard-generator-v1")) {
  customElements.define("edc-sharing-dashboard-generator-v1", EdcSharingDashboardGenerator);
}
