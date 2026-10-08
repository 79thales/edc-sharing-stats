/* Private, opt-in settlements. No scheduled billing, bank API or remote assets. */
function edcBillingEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function edcBillingPeriod(kind, today, latest) {
  const parsed = new Date(`${today}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) throw new Error("invalid_period");
  const year = parsed.getUTCFullYear(), month = parsed.getUTCMonth();
  const iso = value => value.toISOString().slice(0, 10);
  if (kind === "month") return {
    start: iso(new Date(Date.UTC(year, month - 1, 1))),
    end: iso(new Date(Date.UTC(year, month, 0))),
  };
  if (kind === "year") return { start: `${year}-01-01`, end: latest && latest >= `${year}-01-01` && latest < today ? latest : iso(new Date(parsed.getTime() - 86400000)) };
  return null;
}

function edcBillingRequestId() {
  return globalThis.crypto?.randomUUID?.() || `manual-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

globalThis.EDC_BILLING_HELPERS = { escape: edcBillingEscape, period: edcBillingPeriod };

const EDC_BILLING_TEXT = {
  cs: {
    back: "Zpět do integrace",
    heading: "EDC – Platby a vyúčtování", group: "Skupina sdílení", profiles: "Profil reportů",
    noProfiles: "Nejprve vytvořte profil reportů. Bez uloženého profilu nelze vystavit ani odeslat nové vyúčtování. Archiv již vystavených dokladů zůstává dostupný.",
    configure: "Otevřít integraci a vytvořit / upravit profil", settings: "Vystavitel a volitelná evidence úhrad",
    issuer: "Jméno vystavitele", issuerAddress: "Adresa vystavitele (volitelné)", tracking: "Povolit ruční potvrzování úhrad (pouze interní informace)", save: "Uložit nastavení evidence",
    intro: "Soukromé vyúčtování sdílené elektřiny, nikoli automatický daňový doklad. Vystavení ani odeslání nepotvrzuje platbu. Odečítají se jen ručně potvrzené úhrady. Bez potvrzení integrace nezná skutečný stav peněz; částku dál nabízí k zaplacení.",
    draft: "Vystavit vyúčtování", recipient: "Jméno odběratele / příjemce dokladu", recipientAddress: "Adresa odběratele (volitelné)",
    period: "Období", month: "Poslední kalendářní měsíc", year: "Aktuální rok do dostupných dat", custom: "Vlastní období", start: "Od (včetně)", end: "Do (včetně)", due: "Splatnost", preview: "Zkontrolovat a vytvořit náhled",
    previewTitle: "Náhled před vystavením", issue: "Potvrdit vystavení a uložit doklad", issueConfirm: "Potvrzuji rozsah a údaje. Vystavení doklad uloží, ale nic neodešle ani nepotvrdí úhradu.",
    routing: "Příjemci profilu", routingNote: "Všichni příjemci tohoto profilu dostanou stejný doklad se všemi uvedenými EANy. Pro oddělená vyúčtování používejte samostatné profily. Pozastavený profil lze ručně použít; jeho rozvrh se nezmění.",
    complete: "Všechny požadované denní součty jsou dostupné. Toto neověřuje každý interval uvnitř dne.", incomplete: "Chybějící nebo nekonzistentní denní data: konečné vystavení je zablokované. Nula a chybějící data nejsou totéž.",
    ambiguous: "Částečná úhrada zasahuje přes hranici tohoto období nebo výběru EANů. Její přiřazení nelze odhadnout; vystavení a QR jsou zablokované. Upravte ruční přiřazení úhrady.",
    noSmtp: "Profil nyní nemá všechny dostupné SMTP příjemce. Doklad lze uložit a tisknout, ale e-mail není dostupný.",
    history: "Archiv vyúčtování", empty: "Zatím není vystaven žádný doklad.", number: "Doklad", customer: "Odběratel", value: "Hodnota sdílení", confirmed: "Potvrzené úhrady", remaining: "K úhradě", status: "Stav úhrady", open: "Otevřít",
    overview: "Celkový zůstatek unikátních sdílení – nikoli součet překrývajících se dokladů", document: "Uložené vyúčtování", download: "Stáhnout tiskové HTML", print: "Tisk / uložit do PDF", send: "Odeslat / připomenout přes profil",
    sendConfirm: "Potvrzuji odeslání zobrazeného dokladu a aktuálního zůstatku všem příjemcům původního profilu.",
    sendNote: "Opakovaná výzva nezvyšuje dluh. Předání SMTP nepotvrzuje doručení do schránky ani platbu. Při nejistém výsledku ověřte schránku před novým odesláním. Změněný nebo odstraněný profil blokuje odeslání starého dokladu.",
    delivery: "Poslední předání SMTP", handoff_in_progress: "Probíhá / výsledek zatím nepotvrzen", handed_to_smtp: "Předáno SMTP, nikoli potvrzeno doručení", partial_or_uncertain: "Částečný nebo nejistý výsledek", failed_or_uncertain: "Selhání nebo nejistý výsledek",
    payment: "Volitelné ruční potvrzení přijaté platby", amount: "Skutečně přijatá částka (Kč)", paidOn: "Datum přijetí", allocation: "Přiřadit platbu", allEans: "Všechny EANy tohoto dokladu", payConfirm: "Potvrzuji skutečně přijatou částku za uvedené EANy a dny. Nejde o potvrzení odeslání e-mailu.", record: "Zaznamenat úhradu",
    payNote: "Výchozí přiřazení je celý doklad. Pro částečné období nebo konkrétní EAN zvolte přesný rozsah a zadejte odpovídající částku. Integrace rozdělení úhrady neodhaduje. Vypnutí evidence dřívější potvrzení nemaže.",
    receipts: "Související interní potvrzení", reverse: "Zrušit chybné potvrzení", reverseAsk: "Zrušit toto ruční potvrzení? Záznam zůstane v historii a částka se znovu nabídne k úhradě. Navazující úplné potvrzení je nutné zrušit nejprve.", voided: "Potvrzení zrušeno", refreshed: "Evidence byla aktualizována.",
    issued: "Vyúčtování je uložené. Nebylo odesláno a úhrada není tímto potvrzena.",
    unconfirmed: "Úhrada nepotvrzena", partial: "Částečně potvrzeno", confirmedStatus: "Úhrada potvrzena ručně", no_payment_required: "Není částka k úhradě", allocation_required: "Nutné upřesnit přiřazení úhrady",
    privacy: "Jen pro správce. Evidence v Home Assistantu obsahuje osobní údaje, celé EANy, bankovní účet a doklady a je součástí záloh. Nesdílejte export veřejně. Nic se automaticky nevystavuje ani neodesílá; současné reporty a Energy statistiky se nemění.",
  },
  en: {
    back: "Back to integration",
    heading: "EDC – Payments and settlements", group: "Sharing group", profiles: "Report profile",
    noProfiles: "Create a report profile first. Without an explicitly saved profile, new settlements cannot be issued or sent. Existing archived documents remain accessible.",
    configure: "Open the integration to create / edit a profile", settings: "Issuer and optional payment records", issuer: "Issuer name", issuerAddress: "Issuer address (optional)", tracking: "Enable manual payment confirmation (internal information only)", save: "Save ledger settings",
    intro: "A private-person electricity-sharing settlement, not an automatically generated tax invoice. Issuing and sending do not confirm payment. Only manually confirmed receipts are deducted. Without confirmation, the actual payment status is unknown and the amount remains offered for payment.",
    draft: "Issue a settlement", recipient: "Customer / document recipient name", recipientAddress: "Customer address (optional)", period: "Period", month: "Previous calendar month", year: "Current year through available data", custom: "Custom range", start: "From (inclusive)", end: "To (inclusive)", due: "Due date", preview: "Check and preview",
    previewTitle: "Preview before issuing", issue: "Confirm issue and save document", issueConfirm: "I confirm the scope and details. Issuing saves the document but does not send it or confirm payment.", routing: "Profile recipients", routingNote: "Every recipient in this profile receives the same document with all listed EANs. Use separate profiles for private per-customer settlements. Paused profiles can be used manually without changing their schedule.",
    complete: "All requested daily totals are available. This does not verify every intraday interval.", incomplete: "Missing or inconsistent daily data blocks final issue. Missing data is not zero.", ambiguous: "A partial receipt extends beyond this period or EAN selection. Its allocation cannot be inferred; issue and QR are blocked. Review manual receipt allocation.", noSmtp: "Not all profile recipients are currently available SMTP entities. You can save and print the document, but email is unavailable.",
    history: "Settlement archive", empty: "No documents have been issued yet.", number: "Document", customer: "Customer", value: "Sharing value", confirmed: "Confirmed payments", remaining: "Remaining to pay", status: "Payment status", open: "Open", overview: "Balance of unique sharing charges, not the sum of overlapping documents", document: "Saved settlement", download: "Download printable HTML", print: "Print / save as PDF", send: "Send / remind through profile", sendConfirm: "I confirm sending the displayed document and current balance to all recipients of its original profile.",
    sendNote: "Repeated reminders do not add debt. SMTP handoff does not confirm inbox delivery or payment. Check the inbox before resending an uncertain attempt. Changed or removed profiles block sending old documents.", delivery: "Latest SMTP handoff", handoff_in_progress: "In progress / outcome unconfirmed", handed_to_smtp: "Handed to SMTP, inbox delivery unconfirmed", partial_or_uncertain: "Partial or uncertain outcome", failed_or_uncertain: "Failed or uncertain outcome",
    payment: "Optional manual receipt confirmation", amount: "Amount actually received (CZK)", paidOn: "Date received", allocation: "Allocate receipt", allEans: "All EANs in this document", payConfirm: "I confirm the amount actually received for the specified EANs and dates, not email delivery.", record: "Record payment", payNote: "Allocation defaults to the entire document. For a partial period or one EAN, choose the exact range and enter its received amount. Allocation is never guessed. Disabling tracking does not erase previous confirmations.", receipts: "Related internal confirmations", reverse: "Reverse an incorrect confirmation", reverseAsk: "Reverse this manual confirmation? Its audit record is retained and the amount becomes payable again. A dependent full confirmation must be reversed first.", voided: "Confirmation reversed", refreshed: "Ledger updated.", issued: "Settlement saved. Nothing was sent and payment was not confirmed.", unconfirmed: "Payment unconfirmed", partial: "Partially confirmed", confirmedStatus: "Manually confirmed", no_payment_required: "No amount payable", allocation_required: "Receipt allocation needs review",
    privacy: "Administrators only. The local ledger contains personal details, full EANs, bank accounts and documents and is included in HA backups. Do not share exports publicly. Nothing is automatically issued or sent; existing reports and Energy statistics are unchanged.",
  },
};

const EDC_BILLING_ERRORS = {
  profile_required: ["Nejprve vytvořte nebo zvolte existující profil reportů.", "Create or select an existing report profile first."],
  finance_required: ["Ve vybraném profilu musí být povolené finance.", "Enable financial details in the selected profile."],
  invalid_parties: ["Uložte jméno vystavitele a vyplňte odběratele; zkontrolujte délku údajů.", "Save the issuer and enter a customer; check field lengths."],
  invalid_period: ["Zkontrolujte období: od ≤ do, jen minulé dny a nejvýše 3660 dnů.", "Check the range: from ≤ to, past days only, at most 3660 days."],
  incomplete_data: ["Chybějící denní data blokují vystavení. Doplňte historii EDC nebo změňte období.", "Missing daily data blocks issue. Backfill EDC history or change the range."],
  ambiguous_payment: ["Úhradu nelze jednoznačně přiřadit tomuto rozsahu. Upravte její ruční přiřazení.", "A receipt cannot be unambiguously allocated to this range. Review its manual allocation."],
  invalid_due_date: ["Splatnost nesmí být v minulosti.", "The due date cannot be in the past."],
  invalid_amount: ["Zadejte kladnou skutečně přijatou částku s nejvýše dvěma desetinnými místy.", "Enter the positive amount actually received with at most two decimals."],
  overpayment: ["Částka přesahuje zbývající hodnotu vybraných EANů a dnů.", "The receipt exceeds the selected EANs and dates' remaining value."],
  invalid_payment_date: ["Datum přijetí platby nesmí být v budoucnosti.", "The receipt date cannot be in the future."],
  tracking_disabled: ["Nejprve volitelně zapněte ruční evidenci úhrad.", "Enable optional manual payment tracking first."],
  dependent_payment: ["Nejdříve zrušte navazující úplné potvrzení úhrady.", "Reverse the dependent full confirmation first."],
  stale_revision: ["Evidence se mezitím změnila. Obnovte přehled a znovu vytvořte náhled.", "The ledger changed. Refresh and preview again."],
  preview_changed: ["Data, ceny nebo profil se změnily. Zkontrolujte nový náhled.", "Data, prices or the profile changed. Review a new preview."],
  profile_changed: ["Příjemci nebo rozsah profilu se změnili. Vystavte nový doklad přes zvolený profil; sdílení se nezapočítá podruhé.", "The profile's recipients or scope changed. Issue a new explicitly reviewed document; sharing is not counted twice."],
  smtp_unavailable: ["Ověřte SMTP příjemce profilu a dostupnost akce smtp.send_message.", "Check the profile's SMTP recipients and smtp.send_message availability."],
  storage_invalid: ["Úložiště evidence není čitelné. Nebude automaticky resetováno; obnovte správnou zálohu. Stávající EDC funkce se nemění.", "The ledger store is unreadable and will not be reset. Restore a valid backup. Existing EDC functions are unaffected."],
};

class EdcSharingBilling extends HTMLElement {
  constructor() {
    super(); this.attachShadow({ mode: "open" }); this._busy = false; this._quote = null; this._doc = null; this._pending = null;
  }
  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this._initialized) this._initialize();
    const menu = this.shadowRoot.querySelector("ha-menu-button"); if (menu) menu.hass = value;
  }
  set narrow(value) { this._narrow = value; const menu = this.shadowRoot.querySelector("ha-menu-button"); if (menu) menu.narrow = value; }
  connectedCallback() { if (this._hass && !this._initialized) this._initialize(); }
  _el(id) { return this.shadowRoot.getElementById(id); }
  _error(err) {
    const index = this._cs ? 0 : 1;
    return EDC_BILLING_ERRORS[err?.code]?.[index] || (this._cs ? "Akci se nepodařilo dokončit. Obnovte přehled; při nejistém odeslání nejprve ověřte schránku." : "The action could not complete. Refresh the ledger; check the inbox before retrying an uncertain send.");
  }
  _status(text) { this._el("status").textContent = text; }
  _initialize() {
    this._initialized = true; this._cs = this._hass.language?.startsWith("cs"); this._t = EDC_BILLING_TEXT[this._cs ? "cs" : "en"];
    this.shadowRoot.innerHTML = `
      <style>:host{display:block;height:100%;overflow:auto;background:var(--primary-background-color);color:var(--primary-text-color);font:15px/1.5 sans-serif}header{display:flex;align-items:center;gap:12px;padding:12px 16px;background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff)}h1{font-size:20px;margin:0}h2{font-size:21px}main{max-width:1100px;margin:auto;padding:20px}.card{background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color);border-radius:12px;padding:20px;margin:0 0 18px}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}label.field{display:flex;flex-direction:column;gap:6px}input,select{box-sizing:border-box;padding:10px;font:inherit;border:1px solid var(--divider-color);border-radius:6px;color:var(--primary-text-color);background:var(--secondary-background-color);min-width:0}input[type=checkbox]{width:20px;height:20px;vertical-align:middle;margin-right:10px;accent-color:var(--primary-color)}.check{display:block;margin:16px 0}button{font:inherit;border:0;border-radius:24px;padding:10px 16px;background:var(--primary-color);color:var(--text-primary-color,#fff);cursor:pointer;margin:6px 8px 6px 0}button:disabled{opacity:.45;cursor:default}a{color:var(--primary-color)}.muted{color:var(--secondary-text-color)}.scroll{overflow:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid var(--divider-color);white-space:nowrap}iframe{width:100%;height:780px;border:1px solid var(--divider-color);background:#fff}#status{white-space:pre-wrap}[hidden]{display:none!important}@media(max-width:650px){main{padding:12px}.card{padding:14px}.fields{grid-template-columns:1fr}}</style>
      <style>
        header{position:sticky;top:0;z-index:2}header h1{flex:1;min-width:0}
        header a.back{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-width:44px;min-height:44px;flex-shrink:0;color:inherit;text-decoration:none;border-radius:24px}
        .back-icon{font-size:26px}.back:focus-visible{outline:2px solid currentColor;outline-offset:2px}.back:hover{background:rgba(127,127,127,.15)}
        @media(max-width:650px){.back-label{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}}
      </style>
      <header><a id="back" class="back" href="/config/integrations/integration/edc_sharing"><span class="back-icon" aria-hidden="true">←</span><span class="back-label" data-text="back"></span></a><h1 data-text="heading"></h1><ha-menu-button></ha-menu-button></header><main>
      <div class="card"><p data-text="intro"></p><label class="field"><span data-text="group"></span><select id="group"></select></label><button id="refresh">↻</button><p id="status" role="status" aria-live="polite"></p><p class="muted" data-text="privacy"></p></div>
      <div class="card" id="profile-gate" hidden><p data-text="noProfiles"></p><a href="/config/integrations/integration/edc_sharing" data-text="configure"></a></div>
      <div class="card" id="settings-card" hidden><h2 data-text="settings"></h2><div class="fields"><label class="field"><span data-text="issuer"></span><input id="issuer" maxlength="300"></label><label class="field"><span data-text="issuerAddress"></span><input id="issuer-address" maxlength="300"></label></div><label class="check"><input id="tracking" type="checkbox"><span data-text="tracking"></span></label><button id="save" data-text="save"></button></div>
      <div class="card" id="draft-card" hidden><h2 data-text="draft"></h2><div class="fields">
      <label class="field"><span data-text="profiles"></span><select id="profile"></select></label><label class="field"><span data-text="period"></span><select id="period"><option value="month" data-text="month"></option><option value="year" data-text="year"></option><option value="custom" data-text="custom"></option></select></label>
      <label class="field"><span data-text="start"></span><input id="start" type="date"></label><label class="field"><span data-text="end"></span><input id="end" type="date"></label><label class="field"><span data-text="recipient"></span><input id="recipient" maxlength="300"></label><label class="field"><span data-text="recipientAddress"></span><input id="recipient-address" maxlength="300"></label><label class="field"><span data-text="due"></span><input id="due" type="date"></label></div>
      <p><strong data-text="routing"></strong>: <span id="routing"></span></p><p class="muted" data-text="routingNote"></p><label class="check"><input id="allow-missing" type="checkbox"><span id="allow-missing-label"></span></label><button id="preview" data-text="preview"></button></div>
      <div class="card" id="preview-card" hidden><h2 data-text="previewTitle"></h2><div id="preview-summary"></div><p id="availability"></p><p id="smtp-warning" data-text="noSmtp" hidden></p><iframe id="preview-frame" title="Draft settlement preview" sandbox="allow-same-origin allow-modals" referrerpolicy="no-referrer"></iframe><label class="check"><input id="issue-confirm" type="checkbox"><span data-text="issueConfirm"></span></label><button id="issue" disabled data-text="issue"></button></div>
      <div class="card"><h2 data-text="history"></h2><p id="balance"></p><div class="scroll" id="archive"></div></div>
      <div class="card" id="document-card" hidden><h2 data-text="document"></h2><iframe id="document-frame" title="Settlement preview" sandbox="allow-same-origin allow-modals" referrerpolicy="no-referrer"></iframe><button id="download" data-text="download"></button><button id="print" data-text="print"></button><p id="delivery"></p>
      <label class="check"><input id="send-confirm" type="checkbox"><span data-text="sendConfirm"></span></label><button id="send" disabled data-text="send"></button><p class="muted" data-text="sendNote"></p>
      <div id="payment-box" hidden><h2 data-text="payment"></h2><p class="muted" data-text="payNote"></p><div class="fields"><label class="field"><span data-text="allocation"></span><select id="payment-ean"></select></label><label class="field"><span data-text="amount"></span><input id="amount" inputmode="decimal"></label><label class="field"><span data-text="start"></span><input id="payment-start" type="date"></label><label class="field"><span data-text="end"></span><input id="payment-end" type="date"></label><label class="field"><span data-text="paidOn"></span><input id="paid-on" type="date"></label></div><label class="check"><input id="payment-confirm" type="checkbox"><span data-text="payConfirm"></span></label><button id="record" disabled data-text="record"></button></div>
      <h2 data-text="receipts"></h2><div class="scroll" id="receipts"></div></div></main>`;
    this.shadowRoot.querySelectorAll("[data-text]").forEach(el => { el.textContent = this._t[el.dataset.text]; });
    const menu = this.shadowRoot.querySelector("ha-menu-button"); menu.hass = this._hass; menu.narrow = this._narrow;
    this._el("refresh").textContent = this._cs ? "Obnovit přehled" : "Refresh ledger";
    this._el("refresh").addEventListener("click", () => this._run(async () => { const id = this._doc?.id; this._pending = null; await this._overview(); if (id) this._showDocument(await this._call("document", { document_id: id })); this._status(this._t.refreshed); }));
    this._el("group").addEventListener("change", () => this._run(async () => { this._el("allow-missing").checked = false; this._quote = null; this._doc = null; this._el("document-card").hidden = true; await this._overview(); }));
    this._el("profile").addEventListener("change", () => this._profileChanged());
    this._el("period").addEventListener("change", () => this._periodChanged());
    this._el("allow-missing-label").textContent = this._cs ? "Výslovně souhlasím s vyúčtováním pouze dostupných dat. Chybějící dny budou uvedeny na dokladu a nejsou považovány za nulu ani automaticky za dobu před zahájením sdílení." : "I explicitly accept billing only available data. Missing dates will be listed on the document and are not treated as zero or automatically as dates before sharing began.";
    ["start", "end", "recipient", "recipient-address", "due"].forEach(id => this._el(id).addEventListener("input", () => { this._el("allow-missing").checked = false; this._invalidate(); }));
    this._el("allow-missing").addEventListener("input", () => this._invalidate());
    ["issuer", "issuer-address", "tracking"].forEach(id => this._el(id).addEventListener("input", () => this._invalidate()));
    this._el("issue-confirm").addEventListener("change", () => this._el("issue").disabled = this._busy || !this._quote?.can_issue || !this._el("issue-confirm").checked);
    this._el("send-confirm").addEventListener("change", () => this._el("send").disabled = this._busy || !this._doc || !this._el("send-confirm").checked);
    this._el("payment-confirm").addEventListener("change", () => this._el("record").disabled = this._busy || !this._el("payment-confirm").checked);
    this._el("save").addEventListener("click", () => this._run(async () => { await this._mutate("settings", { issuer: this._el("issuer").value, issuer_address: this._el("issuer-address").value, tracking: this._el("tracking").checked }); await this._overview(); this._status(this._t.refreshed); }));
    this._el("preview").addEventListener("click", () => this._run(async () => {
      this._parameters = this._parametersFromForm(); this._quote = await this._call("preview", this._parameters);
      this._el("preview-frame").srcdoc = this._quote.html;
      this._el("issue-confirm").checked = false; this._el("issue").disabled = true; this._el("preview-card").hidden = false;
      const b = this._quote.balance;
      this._el("preview-summary").textContent = `${this._quote.start} – ${this._quote.end}: ${this._t.value} ${b.total} CZK; ${this._t.confirmed} ${b.confirmed} CZK; ${this._t.remaining} ${b.ambiguous.length ? "—" : b.remaining} CZK`;
      const missing = Object.values(this._quote.missing_days).flat();
      this._el("availability").textContent = b.ambiguous.length ? this._t.ambiguous : this._quote.can_issue && !missing.length ? this._t.complete : this._quote.can_issue ? `${this._el("allow-missing-label").textContent} ${[...new Set(missing)].slice(0, 16).join(", ")}` : `${this._t.incomplete} ${[...new Set([...missing, ...this._quote.inconsistent_days])].slice(0, 16).join(", ")}`;
      this._el("smtp-warning").hidden = this._quote.smtp_ready;
    }));
    this._el("issue").addEventListener("click", () => this._run(async () => {
      if (!this._quote?.can_issue || !this._el("issue-confirm").checked) return;
      const doc = await this._mutate("issue", { parameters: this._parameters, preview_id: this._quote.preview_id });
      await this._overview(); this._showDocument(doc); this._status(this._t.issued);
    }));
    this._el("send").addEventListener("click", () => this._run(async () => {
      if (!this._doc || !this._el("send-confirm").checked) return;
      const doc = await this._mutate("send", { document_id: this._doc.id }); await this._overview(); this._showDocument(doc);
    }));
    this._el("record").addEventListener("click", () => this._run(async () => {
      if (!this._doc || !this._el("payment-confirm").checked) return;
      const id = this._doc.id;
      await this._mutate("payment", { document_id: id, amount: this._el("amount").value.replace(",", "."), paid_on: this._el("paid-on").value, start: this._el("payment-start").value, end: this._el("payment-end").value, ean: this._el("payment-ean").value });
      await this._overview(); this._showDocument(await this._call("document", { document_id: id })); this._status(this._t.refreshed);
    }));
    this._el("download").addEventListener("click", () => {
      if (!this._doc) return;
      const url = URL.createObjectURL(new Blob([this._doc.html], { type: "text/html;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = `${this._doc.number}.html`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    this._el("print").addEventListener("click", () => { if (this._doc) this._el("document-frame").contentWindow.print(); });
    this._run(async () => {
      if (!this._hass.user?.is_admin) throw { code: "unauthorized" };
      const groups = await this._hass.callWS({ type: "edc_sharing/billing/groups" });
      groups.forEach(group => { const option = document.createElement("option"); option.value = group.entry_id; option.textContent = group.name; this._el("group").append(option); });
      const selected = new URLSearchParams(location.search).get("entry_id"); if (groups.some(g => g.entry_id === selected)) this._el("group").value = selected;
      if (groups.length) await this._overview();
    });
  }
  async _call(action, payload = {}, revision) {
    return this._hass.callWS({ type: "edc_sharing/billing/action", entry_id: this._el("group").value, action, payload, ...(revision === undefined ? {} : { revision }) });
  }
  async _mutate(action, payload) {
    const signature = JSON.stringify([this._el("group").value, action, payload]);
    if (this._pending?.signature !== signature) this._pending = { signature, request_id: edcBillingRequestId(), revision: this._revision };
    const result = await this._call(action, { ...payload, request_id: this._pending.request_id }, this._pending.revision);
    this._pending = null; return result;
  }
  async _run(task) {
    if (this._busy) return; this._busy = true;
    this.shadowRoot.querySelectorAll("button,input,select").forEach(element => { element.disabled = true; });
    try { await task(); } catch (err) { this._status(this._error(err)); }
    finally {
      this._busy = false; this.shadowRoot.querySelectorAll("button,input,select").forEach(element => { element.disabled = false; });
      this._el("issue").disabled = !this._quote?.can_issue || !this._el("issue-confirm").checked;
      this._el("send").disabled = !this._doc || !this._el("send-confirm").checked;
      this._el("record").disabled = !this._el("payment-confirm").checked;
    }
  }
  _invalidate() { this._quote = null; this._el("preview-card").hidden = true; this._el("issue-confirm").checked = false; this._el("issue").disabled = true; }
  _parametersFromForm() { return { profile_id: this._el("profile").value, start: this._el("start").value, end: this._el("end").value, due: this._el("due").value, recipient: this._el("recipient").value, recipient_address: this._el("recipient-address").value, allow_missing: this._el("allow-missing").checked }; }
  _profileChanged() {
    this._el("allow-missing").checked = false;
    this._invalidate(); const profile = this._profiles?.find(p => p.id === this._el("profile").value);
    if (profile) { this._el("recipient").value = profile.name; this._el("routing").textContent = profile.targets.map(id => this._hass.states[id]?.attributes.friendly_name || id).join(", "); }
  }
  _periodChanged() {
    this._el("allow-missing").checked = false;
    this._invalidate(); const range = edcBillingPeriod(this._el("period").value, this._data.today, this._data.latest_day);
    if (range) { this._el("start").value = range.start; this._el("end").value = range.end; }
  }
  async _overview() {
    this._data = await this._call("overview"); this._revision = this._data.revision; this._profiles = this._data.profiles; this._invalidate();
    this._el("profile-gate").hidden = this._profiles.length !== 0; this._el("settings-card").hidden = !this._profiles.length; this._el("draft-card").hidden = !this._profiles.length;
    this._el("issuer").value = this._data.settings.issuer; this._el("issuer-address").value = this._data.settings.issuer_address; this._el("tracking").checked = this._data.settings.tracking;
    const selected = this._el("profile").value; this._el("profile").replaceChildren();
    this._profiles.forEach(profile => { const option = document.createElement("option"); option.value = profile.id; option.textContent = profile.name; this._el("profile").append(option); });
    if (this._profiles.some(p => p.id === selected)) this._el("profile").value = selected;
    this._profileChanged(); this._periodChanged();
    if (!this._el("due").value) this._el("due").value = new Date(new Date(`${this._data.today}T00:00:00Z`).getTime() + 14 * 86400000).toISOString().slice(0, 10);
    const b = this._data.balance; this._el("balance").textContent = `${this._t.overview}: ${b.remaining} CZK (${this._t.confirmed}: ${b.confirmed} CZK)`;
    const esc = edcBillingEscape;
    this._el("archive").innerHTML = this._data.documents.length ? `<table><thead><tr>${["number", "customer", "period", "value", "remaining", "status"].map(k => `<th>${esc(this._t[k])}</th>`).join("")}<th></th></tr></thead><tbody>${this._data.documents.map(d => `<tr><td>${esc(d.number)}</td><td>${esc(d.recipient)}</td><td>${esc(d.start)} – ${esc(d.end)}</td><td>${esc(d.total)} CZK</td><td>${d.balance.ambiguous.length ? "—" : esc(d.balance.remaining)} CZK</td><td>${esc(this._paymentStatus(d.payment_status))}</td><td><button data-document="${esc(d.id)}">${esc(this._t.open)}</button></td></tr>`).join("")}</tbody></table>` : `<p>${esc(this._t.empty)}</p>`;
    this._el("archive").querySelectorAll("[data-document]").forEach(button => button.addEventListener("click", () => this._run(async () => this._showDocument(await this._call("document", { document_id: button.dataset.document })))));
  }
  _paymentStatus(status) { return status === "confirmed" ? this._t.confirmedStatus : this._t[status] || status; }
  _showDocument(doc) {
    this._doc = doc; this._el("document-card").hidden = false; this._el("document-frame").srcdoc = doc.html;
    this._el("send-confirm").checked = false; this._el("payment-confirm").checked = false;
    const last = doc.deliveries.at(-1); this._el("delivery").textContent = last ? `${this._t.delivery}: ${this._t[last.status] || last.status} (${last.successful} / ${last.failed_or_uncertain})` : "";
    this._el("payment-box").hidden = !this._data.settings.tracking;
    this._el("amount").value = doc.balance.ambiguous.length ? "" : doc.balance.remaining;
    this._el("paid-on").value = this._data.today; this._el("paid-on").max = this._data.today;
    this._el("payment-start").value = doc.start; this._el("payment-end").value = doc.end;
    ["payment-start", "payment-end"].forEach(id => { this._el(id).min = doc.start; this._el(id).max = doc.end; });
    this._el("payment-ean").replaceChildren(); const all = document.createElement("option"); all.value = ""; all.textContent = this._t.allEans; this._el("payment-ean").append(all);
    [...new Set(Object.values(doc.charges).map(row => row.ean))].sort().forEach(ean => { const row = Object.values(doc.charges).find(r => r.ean === ean); const option = document.createElement("option"); option.value = ean; option.textContent = `${row.name} / EAN ${ean}`; this._el("payment-ean").append(option); });
    const keys = new Set(doc.charge_keys); const receipts = this._data.payments.filter(p => p.charge_keys.some(k => keys.has(k))); const esc = edcBillingEscape;
    this._el("receipts").innerHTML = `<table><tbody>${receipts.map(p => `<tr><td>${esc(p.paid_on)}</td><td>${esc(p.amount)} CZK</td><td>${esc(this._data.documents.find(d => d.id === p.document_id)?.number || p.document_id)}<br>${esc(p.allocation_start)} – ${esc(p.allocation_end)}<br>${esc((p.allocation_eans || []).join(", "))}</td><td>${p.voided_at ? esc(this._t.voided) : `<button data-receipt="${esc(p.id)}">${esc(this._t.reverse)}</button>`}</td></tr>`).join("")}</tbody></table>`;
    this._el("receipts").querySelectorAll("[data-receipt]").forEach(button => button.addEventListener("click", () => this._run(async () => {
      if (!window.confirm(this._t.reverseAsk)) return;
      const id = this._doc.id; await this._mutate("void_payment", { payment_id: button.dataset.receipt }); await this._overview(); this._showDocument(await this._call("document", { document_id: id }));
    })));
    this._el("document-card").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

if (!customElements.get("edc-sharing-billing-v1")) customElements.define("edc-sharing-billing-v1", EdcSharingBilling);
