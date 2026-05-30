// AURA War Room — SSE consumer + narrative debate visualization
// v5 — verdict-focused UX with phase timeline and vote breakdown.

const PERSONAS = {
  cfo:       { label: "CFO",       color: "#38bdf8", fill: "#1a4a6a", glow: "rgba(56,189,248,0.55)",  side: "con", emoji: "💰" },
  cto:       { label: "CTO",       color: "#fb923c", fill: "#5c2a08", glow: "rgba(251,146,60,0.55)",  side: "pro", emoji: "🛠️" },
  customer:  { label: "Cliente",   color: "#c084fc", fill: "#361060", glow: "rgba(192,132,252,0.55)", side: "con", emoji: "🧑" },
  red_team:  { label: "Red-Team",  color: "#f87171", fill: "#5c1212", glow: "rgba(248,113,113,0.55)", side: "con", emoji: "🚨" },
  historian: { label: "Historiador", color: "#facc15", fill: "#4a3800", glow: "rgba(250,204,21,0.55)", side: "pro", emoji: "📚" },
};
const KIND_GLYPH = { propose: "◆", critique: "✕", defend: "▲", concede: "~" };
const KIND_LABEL = { propose: "propôs", critique: "criticou", defend: "defendeu", concede: "concedeu" };
const PHASES = ["convoke", "propose", "critique", "referee", "dossier"];

// ---------- Roster ------------------------------------------------------
const rosterEl = document.getElementById("roster");
Object.entries(PERSONAS).forEach(([id, p]) => {
  const li = document.createElement("li");
  li.className = "flex items-center gap-2";
  li.id = `roster-${id}`;
  li.innerHTML = `
    <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" style="background:${p.color}"></span>
    <span class="text-base">${p.emoji}</span>
    <span class="font-semibold" style="color:${p.color}">${p.label}</span>
    <span class="text-[9px] uppercase px-1.5 py-0.5 rounded ${p.side === "pro" ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"}">${p.side === "pro" ? "pró" : "contra"}</span>
    <span class="text-zinc-400 text-xs ml-auto mono" id="count-${id}">0</span>`;
  rosterEl.appendChild(li);
});

// ---------- vis-network graph -------------------------------------------
const nodes = new vis.DataSet();
const edges = new vis.DataSet();
const graphContainer = document.getElementById("graph");

// Colors per claim kind (edges + node accents)
const KIND_PALETTE = {
  propose: { stroke: "#38bdf8", glow: "rgba(56,189,248,0.55)", fill: "#082f49" },
  critique: { stroke: "#fb7185", glow: "rgba(251,113,133,0.55)", fill: "#3f1d2a" },
  defend:  { stroke: "#34d399", glow: "rgba(52,211,153,0.55)", fill: "#052e1a" },
  concede: { stroke: "#fbbf24", glow: "rgba(251,191,36,0.45)", fill: "#3a2a07" },
};

const network = new vis.Network(graphContainer, { nodes, edges }, {
  autoResize: true,
  nodes: {
    shape: "dot",
    size: 20,
    borderWidth: 2,
    borderWidthSelected: 4,
    color: { border: "#52525b", background: "#1c1917", highlight: { border: "#fafafa", background: "#27272a" } },
    font: {
      color: "#e4e4e7", size: 11, face: "Inter",
      strokeWidth: 5, strokeColor: "#0a0a0a",
      multi: false, vadjust: -2,
    },
    shadow: { enabled: true, color: "rgba(0,0,0,0.55)", size: 14, x: 0, y: 4 },
    chosen: {
      node: function (values, id, selected, hovering) {
        if (hovering || selected) {
          values.shadowSize = 22;
          values.shadowColor = "rgba(56,189,248,0.55)";
        }
      },
    },
  },
  edges: {
    color: { color: "#3f3f46", highlight: "#fafafa", hover: "#a1a1aa", opacity: 0.85 },
    width: 1.8,
    selectionWidth: 2,
    arrows: { to: { enabled: true, scaleFactor: 0.65, type: "arrow" } },
    smooth: { enabled: true, type: "cubicBezier", forceDirection: "vertical", roundness: 0.5 },
    font: {
      color: "#a1a1aa", size: 9, face: "JetBrains Mono",
      strokeWidth: 4, strokeColor: "#0a0a0a", align: "middle",
    },
    hoverWidth: 0.7,
  },
  physics: { enabled: false },
  interaction: {
    hover: true, hideEdgesOnDrag: false,
    navigationButtons: false, keyboard: false,
    multiselect: false, zoomView: true, dragView: true,
  },
  layout: {
    hierarchical: {
      enabled: true,
      direction: "UD",
      levelSeparation: 180,
      nodeSpacing: 150,
      treeSpacing: 130,
      blockShifting: true,
      edgeMinimization: true,
      parentCentralization: true,
    }
  },
});

// --- Theater overlays ---------------------------------------------------
function refreshGraphStats() {
  const empty = nodes.length === 0;
  const placeholder = document.getElementById("graph-empty");
  if (placeholder) placeholder.style.display = empty ? "flex" : "none";
  const stats = document.getElementById("graph-stats");
  if (stats) stats.classList.toggle("hidden", empty);
  if (!empty) {
    document.getElementById("stat-nodes").textContent = nodes.length;
    document.getElementById("stat-edges").textContent = edges.length;
    document.getElementById("stat-survived").textContent = survived.size;
    document.getElementById("stat-rejected").textContent = rejected.size;
  }
}

function showDetailPanel(claimId) {
  const c = claimIndex[claimId];
  const panel = document.getElementById("graph-detail");
  if (!c || !panel) return;
  const p = PERSONAS[c.persona];
  if (!p) return;
  document.getElementById("detail-emoji").textContent = p.emoji;
  document.getElementById("detail-persona").textContent = p.label;
  document.getElementById("detail-persona").style.color = p.color;
  const kindEl = document.getElementById("detail-kind");
  const palette = KIND_PALETTE[c.kind] || KIND_PALETTE.propose;
  kindEl.textContent = c.kind;
  kindEl.style.color = palette.stroke;
  kindEl.style.background = palette.fill;
  document.getElementById("detail-statement").textContent = c.statement;
  document.getElementById("detail-conf").textContent = `${Math.round((c.confidence || 0) * 100)}%`;
  document.getElementById("detail-cit").textContent = (c.citations || []).length;
  const survEl = document.getElementById("detail-survived");
  if (survived.has(claimId)) { survEl.textContent = "✓ sobreviveu"; survEl.style.color = "#34d399"; }
  else if (rejected.has(claimId)) { survEl.textContent = "✕ caiu"; survEl.style.color = "#fb7185"; }
  else { survEl.textContent = "○ pendente"; survEl.style.color = "#a1a1aa"; }
  panel.classList.remove("hidden");
}
function hideDetailPanel() {
  document.getElementById("graph-detail")?.classList.add("hidden");
}

network.on("hoverNode", (e) => showDetailPanel(e.node));
network.on("blurNode", () => hideDetailPanel());
network.on("selectNode", (e) => { if (e.nodes[0]) showDetailPanel(e.nodes[0]); });
network.on("deselectNode", () => hideDetailPanel());
network.on("afterDrawing", refreshGraphStats);
// Toolbar controls
let _physicsOn = false;
let _survivorsOnly = false;
document.getElementById("graph-fit")?.addEventListener("click", () => {
  network.fit({ animation: { duration: 600, easingFunction: "easeInOutQuad" } });
});
document.getElementById("graph-physics")?.addEventListener("click", () => {
  _physicsOn = !_physicsOn;
  network.setOptions({ physics: { enabled: _physicsOn } });
});
document.getElementById("graph-survivors")?.addEventListener("click", () => {
  _survivorsOnly = !_survivorsOnly;
  const btn = document.getElementById("graph-survivors");
  btn.classList.toggle("text-emerald-300", _survivorsOnly);
  btn.classList.toggle("bg-emerald-500/10", _survivorsOnly);
  nodes.forEach(n => {
    const hide = _survivorsOnly && !survived.has(n.id);
    nodes.update({ id: n.id, hidden: hide });
  });
  edges.forEach(e => {
    const hide = _survivorsOnly && (!survived.has(e.from) || !survived.has(e.to));
    edges.update({ id: e.id, hidden: hide });
  });
});

// ---------- State -------------------------------------------------------
const personaCounts = {};
const claimIndex = {};   // claim_id -> {persona, kind, statement, confidence, citations}
const survived = new Set(); // claim_ids
const rejected = new Set();
const roundStats = {};   // round -> {claims, survived, rejected}
let lastRound = -1;
let _selectedRounds = 3;  // rodadas que o usuário escolheu; atualizado em startDebate()

function setPhase(phase) {
  const idx = PHASES.indexOf(phase);
  document.querySelectorAll(".phase-step").forEach(el => {
    const p = el.dataset.phase;
    const pi = PHASES.indexOf(p);
    el.classList.remove("active", "done");
    if (pi < idx) el.classList.add("done");
    else if (pi === idx) el.classList.add("active");
  });
  document.getElementById("phase-bar").classList.remove("hidden");
}

function reset() {
  nodes.clear();
  edges.clear();
  survived.clear();
  rejected.clear();
  Object.keys(roundStats).forEach(k => delete roundStats[k]);
  lastRound = -1;
  Object.keys(PERSONAS).forEach(id => {
    personaCounts[id] = 0;
    document.getElementById(`count-${id}`).textContent = "0";
  });
  document.getElementById("transcript").innerHTML = "";
  document.getElementById("verdict-placeholder").classList.remove("hidden");
  document.getElementById("verdict-content").classList.add("hidden");
  document.getElementById("survivors-card").classList.add("hidden");
  document.getElementById("dossier-card").classList.add("hidden");
  const rl = document.getElementById("rounds-list");
  rl.innerHTML = '<li class="text-zinc-600 italic">Rodadas aparecerão aqui…</li>';
  document.getElementById("graph-empty").style.display = "flex";
  document.getElementById("graph-stats")?.classList.add("hidden");
  document.getElementById("graph-detail")?.classList.add("hidden");
  document.getElementById("status-dot").className = "w-2 h-2 rounded-full bg-zinc-600";
  document.getElementById("all-claims-card")?.classList.add("hidden");
  document.getElementById("convergence-note")?.classList.add("hidden");
  Object.keys(claimIndex).forEach(k => delete claimIndex[k]);
}

function updateRoundsList(totalExpected) {
  const rl = document.getElementById("rounds-list");
  const rounds = Object.keys(roundStats).map(Number).sort((a, b) => a - b);
  const maxIdx = totalExpected != null ? totalExpected - 1
               : (rounds.length > 0 ? Math.max(...rounds) : -1);
  if (maxIdx < 0) {
    rl.innerHTML = '<li class="text-zinc-600 italic">Rodadas aparecerão aqui…</li>';
    return;
  }
  const items = [];
  for (let r = 0; r <= maxIdx; r++) {
    if (roundStats[r]) {
      const s = roundStats[r];
      const total = s.claims;
      const surv = s.survived;
      const rej = s.rejected;
      const pending = total - surv - rej;
      items.push(`
        <li class="anim-in border-l-2 border-zinc-700 pl-3 py-1">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-bold text-zinc-200">Rodada ${r + 1}</span>
            <span class="text-zinc-500 mono text-[10px]">${total} claims</span>
          </div>
          <div class="h-1.5 bg-zinc-800 rounded-full overflow-hidden flex">
            <div class="bg-emerald-500" style="width:${total ? (surv/total*100) : 0}%"></div>
            <div class="bg-rose-500/60" style="width:${total ? (rej/total*100) : 0}%"></div>
            <div class="bg-zinc-700" style="width:${total ? (pending/total*100) : 0}%"></div>
          </div>
          <div class="flex justify-between text-[10px] mt-1 mono">
            <span class="text-emerald-400">✓ ${surv} sobreviveram</span>
            <span class="text-rose-400">✕ ${rej} caíram</span>
          </div>
        </li>`);
    } else {
      // Rodada configurada mas não executada — consenso antecipado
      items.push(`
        <li class="border-l-2 border-zinc-700/30 pl-3 py-1 opacity-40">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-bold text-zinc-500">Rodada ${r + 1}</span>
            <span class="text-[10px] text-zinc-600 italic">não realizada</span>
          </div>
          <div class="text-[10px] text-zinc-600 italic">Consenso atingido antes desta rodada</div>
        </li>`);
    }
  }
  rl.innerHTML = items.join("");
}

// ---------- SSE handlers ------------------------------------------------
function handleRoundStarted(payload) {
  lastRound = payload.round;
  if (!roundStats[lastRound]) roundStats[lastRound] = { claims: 0, survived: 0, rejected: 0 };
  updateRoundsList();
}

function handleClaim(payload) {
  claimIndex[payload.claim_id] = payload;
  // tag the claim with current round so we can attribute scores correctly
  payload.__round = lastRound;
  const p = PERSONAS[payload.persona];
  if (!p) return;

  // phase mapping: first propose of new round -> propose phase, else critique
  if (payload.kind === "propose") setPhase("propose");
  else setPhase("critique");

  const r = lastRound;
  if (!roundStats[r]) roundStats[r] = { claims: 0, survived: 0, rejected: 0 };
  roundStats[r].claims++;
  updateRoundsList();

  personaCounts[payload.persona] = (personaCounts[payload.persona] || 0) + 1;
  document.getElementById(`count-${payload.persona}`).textContent = personaCounts[payload.persona];

  // Node label: short persona tag only — long statement lives in hover detail.
  const palette = KIND_PALETTE[payload.kind] || KIND_PALETTE.propose;
  const conf = Math.max(0.15, Math.min(1, payload.confidence || 0.5));
  const nodeSize = 28 + conf * 22;  // 28..50 — bem maior pra leitura

  const _KIND_LEVEL = { propose: 0, critique: 1, concede: 1, defend: 2 };
  nodes.add({
    id: payload.claim_id,
    label: `${p.emoji} ${p.label}`,
    level: Math.max(0, lastRound) * 4 + (_KIND_LEVEL[payload.kind] || 0),
    color: {
      border: p.color,
      background: p.fill,
      highlight: { border: "#fafafa", background: p.fill },
      hover: { border: "#fafafa", background: p.fill },
    },
    borderWidth: 3,
    size: nodeSize,
    shadow: { enabled: true, color: p.glow, size: 22, x: 0, y: 0 },
    font: { size: 16, face: "Inter, system-ui", color: "#fafafa", strokeWidth: 6, strokeColor: "#0a0a0a", vadjust: -4, bold: { size: 16, color: "#fafafa" } },
  });
  // Auto-fit every time a new node lands so o grafo nunca fica encolhido num canto
  clearTimeout(window.__auraFitT);
  window.__auraFitT = setTimeout(() => {
    try { network.fit({ animation: { duration: 500, easingFunction: "easeInOutQuad" } }); } catch {}
  }, 250);
  const _EDGE_LABEL = {
    critique: "⚔ refuta",
    defend:   "🛡 defende",
    concede:  "✋ concede",
    propose:  "",
  };
  const _EDGE_COLOR = {
    critique: "#f43f5e",
    defend:   "#22c55e",
    concede:  "#f59e0b",
    propose:  palette.stroke,
  };
  (payload.targets || []).forEach(t => {
    if (nodes.get(t)) {
      const edgeColor = _EDGE_COLOR[payload.kind] || palette.stroke;
      const dashes = payload.kind === "concede" ? [6, 4] : false;
      const lbl = _EDGE_LABEL[payload.kind] || "";
      edges.add({
        from: t, to: payload.claim_id,
        label: lbl,
        font: {
          color: edgeColor, size: 11, face: "Inter, system-ui",
          strokeWidth: 4, strokeColor: "#0a0a0a",
          align: "middle",
        },
        color: { color: edgeColor, opacity: 0.85, highlight: "#fafafa" },
        width: 2.0 + conf * 1.4,
        dashes,
      });
    }
  });

  // Transcript
  const li = document.createElement("li");
  li.className = "border-l-2 pl-3 py-1 anim-in";
  li.style.borderColor = p.color;
  const kindCls = payload.kind === "critique" ? "bg-rose-500/15 text-rose-300"
                : payload.kind === "defend" ? "bg-emerald-500/15 text-emerald-300"
                : payload.kind === "concede" ? "bg-amber-500/15 text-amber-300"
                : "bg-sky-500/15 text-sky-300";
  const kindLabel = payload.kind === "critique" ? "critica"
                  : payload.kind === "defend" ? "defende"
                  : payload.kind === "concede" ? "concede"
                  : "propõe";
  const strippedStmt = stripMeta(payload.statement);
  const stmtHtml = strippedStmt
    ? `<div class="text-zinc-300 leading-relaxed break-words">${escapeHtml(strippedStmt)}</div>`
    : `<div class="text-zinc-500 italic text-[10px]">${payload.kind === "concede" ? "Concessão — argumento aceito sem contestação" : "Resposta interna do conselheiro"}</div>`;
  li.innerHTML = `
    <div class="flex items-center gap-2 mb-1">
      <span class="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded ${kindCls}">${kindLabel}</span>
      <span class="font-semibold text-[11px]" style="color:${p.color}">${p.emoji} ${p.label}</span>
      <span class="text-zinc-500 text-[10px] ml-auto mono">${(payload.confidence * 100).toFixed(0)}% · ${payload.citations.length}cit</span>
    </div>
    ${stmtHtml}`;
  const tEl = document.getElementById("transcript");
  tEl.appendChild(li);
  tEl.scrollTop = tEl.scrollHeight;

  document.getElementById("status").textContent = `${p.label} ${KIND_LABEL[payload.kind]}…`;
  document.getElementById("status-dot").className = "w-2 h-2 rounded-full bg-sky-400 animate-pulse";
}

function handleScore(payload) {
  const node = nodes.get(payload.claim_id);
  if (!node) return;
  const claim = claimIndex[payload.claim_id];
  if (!claim) return;
  const p = PERSONAS[claim.persona];

  if (payload.survived) {
    survived.add(payload.claim_id);
    nodes.update({
      id: payload.claim_id,
      color: {
        border: "#22c55e",
        background: p.fill,
        highlight: { border: "#86efac", background: p.fill },
        hover: { border: "#86efac", background: p.fill },
      },
      borderWidth: 5,
      shadow: { enabled: true, color: "rgba(34,197,94,0.70)", size: 28, x: 0, y: 0 },
    });
  } else {
    rejected.add(payload.claim_id);
    nodes.update({
      id: payload.claim_id,
      color: {
        border: "#3f3f46",
        background: "#0c0a09",
        highlight: { border: "#71717a", background: "#18181b" },
        hover: { border: "#71717a", background: "#18181b" },
      },
      borderWidth: 1,
      opacity: 0.42,
      shadow: { enabled: false },
    });
    // Also fade adjacent rejected->survivor edges
    edges.forEach(e => {
      if (e.from === payload.claim_id || e.to === payload.claim_id) {
        edges.update({ id: e.id, color: { color: "#3f3f46", opacity: 0.35 } });
      }
    });
  }

  // update round stats
  Object.keys(roundStats).forEach(r => {
    roundStats[r].survived = 0;
    roundStats[r].rejected = 0;
  });
  Object.values(claimIndex).forEach(c => {
    const r = c.__round ?? 0;
    if (roundStats[r]) {
      if (survived.has(c.claim_id)) roundStats[r].survived++;
      else if (rejected.has(c.claim_id)) roundStats[r].rejected++;
    }
  });
  updateRoundsList();
  setPhase("referee");
}

// Content-based stance detection — mirrors aura.agents.referee._classify_stance
// on the backend so the UI never disagrees with the dossier's posterior.
// Persona-side prior is consulted ONLY when content is genuinely neutral.
const AGAINST_PHRASES = [
  "não devemos", "nao devemos", "não recomendo", "nao recomendo",
  "não prosseguir", "nao prosseguir", "devemos rejeitar", "devemos adiar",
  "devemos evitar", "devemos pausar", "devemos cancelar", "discordo",
  "rejeitar", "do not", "should not", "must not", "shouldn't",
  "ponto fraco",
  // "yes-but" rhetorical pattern — nominal agreement but substantive against.
  "concordo, mas", "concordo mas", "concordo, porém", "concordo porem",
  "de acordo, mas", "de acordo mas",
];
const AGAINST_STEMS = [
  "rejeit", "compromet", "falh", "fracass", "inviabiliz", "piora",
  "deteriora", "degrada", "impossibilita", "obstr", "impede",
];
const AGAINST_TOKENS = [
  "risco", "riscos", "fragiliza", "fragilidade", "downside", "perda",
  "queda", "cai", "downtime", "churn", "ameaça", "ameaca",
  "inviável", "inviavel", "vulnerável", "vulneravel",
];
const FOR_PHRASES = [
  "devemos lançar", "devemos lancar", "devemos prosseguir",
  "devemos aprovar", "devemos adquirir", "devemos investir",
  "devemos avançar", "devemos avancar", "recomendo prosseguir",
  "recomendo aprovar", "recomendo lançar", "recomendo lancar",
  "deveríamos lançar", "deveriamos lancar",
  "should proceed", "should approve", "should launch",
  "mantenho a posição", "mantenho a posicao",
];
const FOR_TOKENS = [
  "viável", "viavel", "favorável", "favoravel", "vantagem", "oportunidade",
  "retorno", "lucro", "crescimento", "expansão", "expansao", "aprovar",
  "prosseguir",
];

function classifyStance(claim) {
  if (claim.kind === "concede") return "neutral";
  const text = " " + (claim.statement || "").toLowerCase() + " ";
  let against = 0, pro = 0;
  for (const p of AGAINST_PHRASES) if (text.includes(p)) against++;
  for (const t of AGAINST_TOKENS) {
    if (text.includes(" " + t + " ") || text.includes(" " + t + ".") || text.includes(" " + t + ",")) against++;
  }
  for (const s of AGAINST_STEMS) if (text.includes(" " + s)) against++;
  for (const p of FOR_PHRASES) if (text.includes(p)) pro++;
  for (const t of FOR_TOKENS) {
    if (text.includes(" " + t + " ") || text.includes(" " + t + ".") || text.includes(" " + t + ",")) pro++;
  }
  if (against > pro) return "against";
  if (pro > against) return "for";
  const persona = PERSONAS[claim.persona];
  if (!persona) return "neutral";
  // Personas whose role is intrinsically directional keep a prior;
  // CTO/Historian argue both sides depending on the topic — stay neutral.
  // (claim.persona is the key into PERSONAS, e.g. "cto", "historian")
  if (claim.persona === "cto" || claim.persona === "historian") return "neutral";
  return persona.side === "pro" ? "for" : "against";
}

function computeVoteBreakdown() {
  // Weight surviving claims by their *content* stance + confidence — never
  // by hardcoded persona side. Personas appear in the pro/con label sets
  // only on the side they actually argued on this debate.
  let pro = 0, con = 0;
  const proSet = new Set(), conSet = new Set();
  survived.forEach(id => {
    const c = claimIndex[id];
    if (!c) return;
    const p = PERSONAS[c.persona];
    if (!p) return;
    const stance = classifyStance(c);
    const w = c.confidence || 0.5;
    if (stance === "for") { pro += w; proSet.add(p.label); }
    else if (stance === "against") { con += w; conSet.add(p.label); }
    // neutral → no contribution (concessions widen, never bias).
  });
  const total = pro + con || 1;
  return { proPct: pro/total*100, conPct: con/total*100, proSet: [...proSet], conSet: [...conSet] };
}

function handleDossier(d) {
  _lastDossier = d;  // persist for share/export
  setPhase("dossier");
  document.getElementById("status").textContent = "Dossiê pronto. Decisão entregue.";
  document.getElementById("status-dot").className = "w-2 h-2 rounded-full bg-emerald-400";

  // Verdict
  document.getElementById("verdict-placeholder").classList.add("hidden");
  document.getElementById("verdict-content").classList.remove("hidden");
  const conf = d.confidence;
  const survCount = survived.size;
  let verdict, vc1, vc2, sub, insight;
  if (survCount === 0) {
    verdict = "EVIDÊNCIA INSUFICIENTE"; vc1 = "#a1a1aa"; vc2 = "#52525b";
    sub = "Nenhum argumento sobreviveu ao crivo";
    insight = `Todos os argumentos iniciais foram <span class="text-zinc-300 font-bold">refutados pelo Red-Team / Juiz</span> — geralmente por baixa fundamentação ou falta de citações. Reformule a pergunta com mais contexto factual, anexe dados de mercado, ou peça uma análise específica em vez de uma decisão binária.`;
  } else if (conf >= 0.66) {
    verdict = "PROSSEGUIR"; vc1 = "#22c55e"; vc2 = "#15803d";
    sub = "Conselho convergiu com alta confiança";
    insight = `Após ${d.rounds.length} rodada(s) de debate adversarial, o conselho atingiu <span class="text-emerald-300 font-bold">convergência clara</span>. Os argumentos pró sobreviveram à crítica do Red-Team e CFO. Pode avançar com confiança calibrada.`;
  } else if (conf <= 0.34) {
    verdict = "NÃO PROSSEGUIR"; vc1 = "#f43f5e"; vc2 = "#9f1239";
    sub = "Conselho convergiu contra a proposta";
    insight = `Após ${d.rounds.length} rodada(s), os argumentos contra <span class="text-rose-300 font-bold">sobreviveram ao crivo</span>. Avançar agora seria ignorar evidência substantiva. Recomenda-se reformular a proposta ou abandonar.`;
  } else {
    verdict = "PROSSEGUIR COM CAUTELA"; vc1 = "#f59e0b"; vc2 = "#b45309";
    sub = "Decisão calibrada — divergência genuína";
    insight = `O conselho está <span class="text-amber-300 font-bold">honestamente dividido</span> (${survCount} argumentos sobreviveram). Em decisões deste nível de risco, unanimidade seria suspeita. Avance só se mitigar os riscos sobreviventes listados — ou peça mais dados antes de decidir.`;
  }
  const badge = document.getElementById("verdict-badge");
  badge.style.setProperty("--vc1", vc1);
  badge.style.setProperty("--vc2", vc2);
  document.getElementById("verdict-text").textContent = verdict;
  document.getElementById("verdict-sub").textContent = sub;
  document.getElementById("verdict-insight").innerHTML = insight;
  // Update page title with verdict for browser tab / sharing
  const q = document.getElementById("question")?.value?.slice(0, 40) || "debate";
  document.title = `${verdict} · AURA War Room`;

  // Vote breakdown — bar widths come from the dossier's posterior (single
  // source of truth), labels come from per-claim content classification so
  // each persona appears on the side it actually argued.
  const v = computeVoteBreakdown();
  const proPct = conf * 100;
  const conPct = (1 - conf) * 100;
  document.getElementById("vote-pro").style.width = `${proPct}%`;
  document.getElementById("vote-con").style.width = `${conPct}%`;
  // Vote labels: hide when both sides are empty (all args refuted)
  const labelsEl = document.getElementById("vote-labels");
  if (v.proSet.length === 0 && v.conSet.length === 0) {
    if (labelsEl) labelsEl.classList.add("hidden");
  } else {
    if (labelsEl) labelsEl.classList.remove("hidden");
    document.getElementById("pro-personas").textContent = v.proSet.join(" · ") || "—";
    document.getElementById("con-personas").textContent = v.conSet.join(" · ") || "—";
  }
  document.getElementById("vote-summary").textContent = `${survived.size} argumentos sobreviventes`;
  // Exibe convicção na direção da recomendação (não a probabilidade de aprovação bruta),
  // para que o número reflita o quão certo o conselho está do veredito emitido.
  const isAgainst = conf <= 0.34;
  const isPro     = conf >= 0.66;
  const convPct   = isAgainst ? Math.round((1 - conf) * 100) : Math.round(conf * 100);
  const convLabel = isAgainst ? "contra" : (isPro ? "a favor" : "equilíbrio");
  const [lo, hi] = d.confidence_interval;
  const ciLo = isAgainst ? Math.round((1 - hi) * 100) : Math.round(lo * 100);
  const ciHi = isAgainst ? Math.round((1 - lo) * 100) : Math.round(hi * 100);
  document.getElementById("conf-num").textContent = `${convPct}% ${convLabel}`;
  document.getElementById("conf-ci").textContent = `[${ciLo}%, ${ciHi}%]`;

  // Telemetria — torna visível o custo real e a economia obtida via cache +
  // paralelismo. Para o pitch e para confiança do júri.
  const tel = d.telemetry || {};
  const telRow = document.getElementById("telemetry-row");
  if (telRow && (tel.llm_calls != null || tel.elapsed_s != null)) {
    telRow.classList.remove("hidden");
    telRow.classList.add("flex");
    const elapsed = tel.elapsed_s != null ? `${Number(tel.elapsed_s).toFixed(1)}s` : "—";
    document.getElementById("tel-time").textContent = elapsed;
    document.getElementById("tel-llm").textContent = tel.llm_calls ?? 0;
    document.getElementById("tel-emb").textContent = tel.embed_calls ?? 0;
    document.getElementById("tel-cache").textContent = tel.embed_cache_hits ?? 0;
  }

  // Nota de convergência antecipada — explica ao usuário leigo por que o
  // debate terminou em menos rodadas do que ele configurou.
  const roundsRun = Array.isArray(d.rounds) ? d.rounds.length : _selectedRounds;
  const cnEl = document.getElementById("convergence-note");
  if (cnEl) {
    if (roundsRun < _selectedRounds) {
      cnEl.textContent = `⚡ Convergência antecipada: o conselho atingiu consenso em ${roundsRun} de ${_selectedRounds} rodadas — mais rodadas não mudariam o resultado.`;
      cnEl.classList.remove("hidden");
    } else {
      cnEl.classList.add("hidden");
    }
  }

  // Finaliza o afunilamento mostrando TODAS as rodadas configuradas,
  // incluindo as não-executadas (consenso antecipado)
  updateRoundsList(_selectedRounds);

  // Surviving args card — pick top 4 highest-confidence survivors
  const topSurvivors = [...survived]
    .map(id => claimIndex[id])
    .filter(c => c)
    .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
    .slice(0, 4);
  if (topSurvivors.length > 0) {
    document.getElementById("survivors-card").classList.remove("hidden");
    const ul = document.getElementById("survivors");
    ul.innerHTML = topSurvivors.map(c => {
      const p = PERSONAS[c.persona];
      return `
        <li class="rounded-lg p-2.5 bg-zinc-900/60 border-l-2 anim-in" style="border-color:${p.color}">
          <div class="flex items-center gap-2 mb-1">
            <span class="text-sm">${p.emoji}</span>
            <span class="font-semibold text-[11px]" style="color:${p.color}">${p.label}</span>
            <span class="text-zinc-500 text-[10px] ml-auto mono">${(c.confidence*100).toFixed(0)}%</span>
          </div>
          <div class="text-zinc-300 leading-snug break-words">${escapeHtml(stripMeta(c.statement))}</div>
        </li>`;
    }).join("");
  }

  // Dossier details
  document.getElementById("dossier-card").classList.remove("hidden");
  const risksEl = document.getElementById("risks");
  risksEl.innerHTML = d.surviving_risks.map(r => `<li class="break-words">${escapeHtml(stripMeta(r))}</li>`).join("") || '<li class="text-zinc-500 italic">Nenhum risco residual identificado.</li>';

  const cfEl = document.getElementById("counterfactuals");
  cfEl.innerHTML = d.counterfactuals.map(cf =>
    `<li class="break-words"><span class="text-amber-400 font-semibold mono">${(cf.probability*100).toFixed(0)}%</span> · ${escapeHtml(cf.description)}</li>`
  ).join("") || '<li class="text-zinc-500 italic">Nenhum cenário relevante.</li>';

  // Todos os argumentos — visão completa: sobreviventes + rejeitados
  const allIds = Object.keys(claimIndex);
  if (allIds.length > 0) {
    document.getElementById("all-claims-card").classList.remove("hidden");
    const survList = allIds.filter(id => survived.has(id))
      .map(id => claimIndex[id])
      .sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    const rejList = allIds.filter(id => !survived.has(id))
      .map(id => claimIndex[id])
      .sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    const _renderClaimLi = c => {
      const p = PERSONAS[c.persona];
      if (!p) return "";
      return `<li class="rounded-md p-2 bg-zinc-900/60 border-l-2 mb-1.5" style="border-color:${p.color}">
        <div class="flex items-center gap-1.5 mb-0.5">
          <span class="text-xs">${p.emoji}</span>
          <span class="font-semibold text-[10px]" style="color:${p.color}">${p.label}</span>
          <span class="text-zinc-500 text-[10px] mono ml-auto">${(c.confidence*100).toFixed(0)}%</span>
        </div>
        <div class="text-zinc-400 text-[11px] leading-snug break-words">${escapeHtml(stripMeta(c.statement))}</div>
      </li>`;
    };
    document.getElementById("all-survivors").innerHTML =
      survList.map(_renderClaimLi).join("") ||
      '<li class="text-zinc-600 italic text-[11px]">Nenhum sobrevivente.</li>';
    document.getElementById("all-rejected").innerHTML =
      rejList.map(_renderClaimLi).join("") ||
      '<li class="text-zinc-600 italic text-[11px]">Nenhum rejeitado.</li>';
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

// Remove debate-internal meta-language before showing claims/risks to the user.
// Mirrors backend aura_bot._strip_meta — same prefixes, same fallback logic.
const _META_RE = /^\s*(Concordo(?:\s*com isso)?[,;]?\s*(?:mas\s*)?(?:é importante notar que\s*|que\s*)?|Discordo(?:\s*com isso)?[,;]?\s*(?:pois\s*|porque\s*|mas\s*)?|Mantenho (?:a|minha) posição[,;]?\s*(?:porque\s*|pois\s*)?|Devemos (?:rejeitar|apoiar)[^,;]+[,;]\s*|Afirmo que\s*|Considero que\s*)/i;
// Palavras que são pura meta-linguagem interna sem conteúdo para o usuário
const _PURE_META_RE = /^(concedo|concede|concordo|discordo|refuto|aceito|aceitar|ok|sim|não|nao|certo|correto)\.?[!?]?$/i;
function stripMeta(text) {
  const cleaned = text.replace(_META_RE, "").replace(/^["'.,;:\-\s.\u2026]+/, "").trim();
  // Se o que sobrou é pura meta-palavra sem conteúdo real, retorna vazio
  if (_PURE_META_RE.test(cleaned) || _PURE_META_RE.test(text.trim())) return "";
  if (cleaned.length < 20) return text;
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

// ---------- Driver ------------------------------------------------------
async function startDebate() {
  const question = document.getElementById("question").value.trim();
  if (question.length < 10) { alert("Pergunta deve ter ao menos 10 caracteres."); return; }
  const context = document.getElementById("context").value.trim() || null;
  const rounds = parseInt(document.getElementById("rounds").value, 10);
  _selectedRounds = rounds;
  const mode = document.getElementById("mode")?.value || "free";
  const ghModel = document.getElementById("gh-model")?.value || null;

  reset();
  setPhase("convoke");
  document.getElementById("status").textContent = "Convocando conselho…";
  document.getElementById("status-dot").className = "w-2 h-2 rounded-full bg-sky-400 animate-pulse";

  const btn = document.getElementById("start");
  const cancelBtn = document.getElementById("cancel");
  btn.disabled = true; btn.classList.add("opacity-60", "cursor-wait");
  cancelBtn?.classList.remove("hidden");

  // Allow user to abort the in-flight debate
  const controller = new AbortController();
  window.__auraAbort = controller;
  const onCancel = () => controller.abort();
  cancelBtn?.addEventListener("click", onCancel, { once: true });

  try {
    const res = await fetch("/debates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question, context, max_rounds: rounds, mode,
        ...(mode === "free" && ghModel ? { gh_model: ghModel } : {}),
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.text();
      document.getElementById("status").textContent = `Erro: ${err.slice(0, 200)}`;
      document.getElementById("status-dot").className = "w-2 h-2 rounded-full bg-rose-500";
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split(/\r?\n\r?\n/);
      buf = frames.pop();
      for (const frame of frames) {
        const evMatch = frame.match(/^event:\s*(.+)$/m);
        const dataMatch = frame.match(/^data:\s*(.+)$/m);
        if (!dataMatch) continue;
        const evName = evMatch ? evMatch[1].trim() : "message";
        let payload;
        try { payload = JSON.parse(dataMatch[1]); } catch { continue; }
        if (evName === "round.started") handleRoundStarted(payload.payload);
        else if (evName === "claim.emitted") handleClaim(payload.payload);
        else if (evName === "score.emitted") handleScore(payload.payload);
        else if (evName === "dossier") handleDossier(payload);
      }
    }
  } catch (e) {
    if (e && e.name === "AbortError") {
      document.getElementById("status").textContent = "Debate cancelado pelo usuário.";
      document.getElementById("status-dot").className = "w-2 h-2 rounded-full bg-amber-500";
    } else {
      document.getElementById("status").textContent = `Erro: ${(e?.message || e).toString().slice(0,200)}`;
      document.getElementById("status-dot").className = "w-2 h-2 rounded-full bg-rose-500";
    }
  } finally {
    btn.disabled = false; btn.classList.remove("opacity-60", "cursor-wait");
    cancelBtn?.classList.add("hidden");
    cancelBtn?.removeEventListener("click", onCancel);
    window.__auraAbort = null;
  }
}

document.getElementById("start").addEventListener("click", startDebate);
// Toggle model dropdown visibility based on mode
const _modeSel = document.getElementById("mode");
const _ghWrap = document.getElementById("gh-model-wrap");
function _syncGhVisibility() {
  if (!_modeSel || !_ghWrap) return;
  _ghWrap.style.display = _modeSel.value === "free" ? "" : "none";
}
_modeSel?.addEventListener("change", _syncGhVisibility);
_syncGhVisibility();
document.getElementById("help-toggle").addEventListener("click", () => {
  document.getElementById("help-panel").classList.toggle("hidden");
});
document.getElementById("transcript-toggle").addEventListener("click", (e) => {
  const t = document.getElementById("transcript");
  t.classList.toggle("hidden");
  e.target.textContent = t.classList.contains("hidden") ? "mostrar" : "esconder";
});
document.querySelectorAll(".example-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.getElementById("question").value = btn.dataset.q || "";
    document.getElementById("context").value = btn.dataset.c || "";
  });
});

// Mode pill
const modeSel = document.getElementById("mode");
const modePill = document.getElementById("mode-pill");
function refreshModePill() {
  if (!modePill) return;
  const v = modeSel.value;
  const map = {
    mock:  { text: "mock · offline",     dot: "bg-zinc-400",    cls: "bg-zinc-500/10 text-zinc-300 border-zinc-500/30" },
    free:  { text: "free · gpt-4o-mini", dot: "bg-emerald-400", cls: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30" },
    azure: { text: "azure · gpt-4o",     dot: "bg-sky-400",     cls: "bg-sky-500/10 text-sky-300 border-sky-500/30" },
  };
  const cfg = map[v] || map.mock;
  modePill.className = "hidden sm:inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wider px-2.5 py-1 rounded-md border " + cfg.cls;
  modePill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full ${cfg.dot} animate-pulse"></span>${cfg.text}`;
}
modeSel?.addEventListener("change", refreshModePill);
refreshModePill();

// ---------- Share / Export ----------------------------------------------
let _lastDossier = null;  // stored when handleDossier fires

function _dossierToShareText(d) {
  const q = document.getElementById("question")?.value?.trim() || "Pergunta estratégica";
  const verdict = document.getElementById("verdict-text")?.textContent || "";
  const conf = d.confidence != null ? d.confidence : 0.5;
  const isAgainst = conf <= 0.34;
  const isPro = conf >= 0.66;
  const convPct = isAgainst ? Math.round((1 - conf) * 100) : Math.round(conf * 100);
  const convLabel = isAgainst ? "contra" : (isPro ? "a favor" : "equilíbrio");
  const [lo, hi] = d.confidence_interval || [0, 1];
  const ciLo = isAgainst ? Math.round((1 - hi) * 100) : Math.round(lo * 100);
  const ciHi = isAgainst ? Math.round((1 - lo) * 100) : Math.round(hi * 100);
  const risks = (d.surviving_risks || []).slice(0, 3).map(r => `  • ${stripMeta(r)}`).join("\n") || "  (nenhum)";
  const rounds = d.rounds?.length ?? "?";
  return [
    `🏛️ AURA · Veredicto do Conselho`,
    ``,
    `Pergunta: "${q}"`,
    `Veredicto: ${verdict}`,
    `Convicção: ${convPct}% ${convLabel} (95% CI [${ciLo}%, ${ciHi}%]) · ${rounds} rodadas adversariais`,
    ``,
    `Riscos sobreviventes:`,
    risks,
    ``,
    `⚡ Powered by AURA — Adversarial Unified Reasoning Arena`,
    window.location.href,
  ].join("\n");
}

document.getElementById("share-btn")?.addEventListener("click", async () => {
  if (!_lastDossier) return;
  const text = _dossierToShareText(_lastDossier);
  try {
    await navigator.clipboard.writeText(text);
    const toast = document.getElementById("share-toast");
    if (toast) { toast.style.opacity = "1"; setTimeout(() => { toast.style.opacity = "0"; }, 2000); }
  } catch {
    prompt("Copie o texto abaixo:", text);
  }
});

document.getElementById("export-json-btn")?.addEventListener("click", () => {
  if (!_lastDossier) return;
  const blob = new Blob([JSON.stringify(_lastDossier, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "aura-dossier.json"; a.click();
  URL.revokeObjectURL(url);
});
