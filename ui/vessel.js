const ZONES = {
  overview: { kicker: "VESSEL", title: "Overview", hint: "Tap a space on the plan.", fields: [["port.oil_psi","Port oil","psi",0,"oil_psi"],["stbd.oil_psi","Stbd oil","psi",0,"oil_psi"],["fuel_pct","Fuel","%",0,"fuel_pct"],["water_pct","Fresh water","%",0,"water_pct"],["house_v","House bank","V",1,"volts_24"],["gen.oil_psi","Gen oil","psi",0,"gen_oil_psi"]] },
  helm: { kicker: "COMMAND DECK", title: "Helm", hint: "Garmin pages already show Cummins.", fields: [["port.rpm","Port RPM","rpm",0,"rpm"],["stbd.rpm","Stbd RPM","rpm",0,"rpm"],["gen.running","Generator","",0,"gen_rpm"]] },
  gen: { kicker: "ENGINE ROOM", title: "Phasor K4-12", hint: "Serial 8098. Oil via Veratron instance 2.", fields: [["gen.running","State","",0,"gen_rpm"],["gen.rpm","RPM","rpm",0,"gen_rpm"],["gen.oil_psi","Oil pressure","psi",0,"gen_oil_psi"],["gen.coolant_f","Coolant","\u00b0F",0,"gen_coolant_f"],["gen.ac_v","AC volts","V",0,"gen_ac_v"],["gen.ac_hz","Frequency","Hz",1,"gen_ac_hz"],["gen.ac_a","AC amps","A",0,"gen_ac_a"],["gen.hours","Hours","hrs",1,"hours"]] },
  port: { kicker: "ENGINE ROOM", title: "Port Cummins QSC 600", hint: "ESN 73676035", fields: [["port.rpm","RPM","rpm",0,"rpm"],["port.coolant_f","Coolant","\u00b0F",0,"coolant_f"],["port.oil_psi","Oil","psi",0,"oil_psi"],["port.fuel_rate_gph","Burn","gph",1,"fuel_rate_gph"]] },
  stbd: { kicker: "ENGINE ROOM", title: "Starboard Cummins QSC 600", hint: "ESN 73676031", fields: [["stbd.rpm","RPM","rpm",0,"rpm"],["stbd.coolant_f","Coolant","\u00b0F",0,"coolant_f"],["stbd.oil_psi","Oil","psi",0,"oil_psi"],["stbd.fuel_rate_gph","Burn","gph",1,"fuel_rate_gph"]] },
  fuel: { kicker: "TANKS", title: "Fuel", hint: "525 gal.", fields: [["fuel_pct","Level","%",0,"fuel_pct"],["fuel_gal","Remaining","gal",0,"fuel_pct"]] },
  water: { kicker: "TANKS", title: "Fresh water", hint: "Capacity in config.", fields: [["water_pct","Level","%",0,"water_pct"],["water_gal","Remaining","gal",0,"water_pct"]] },
  heads: { kicker: "SANITATION", title: "Holding", hint: "Top red = full.", fields: [["holding_pct","Holding","%",0,"holding_pct"]] },
  mezz: { kicker: "COCKPIT", title: "Mezzanine", hint: "ER hatch.", fields: [["gen.oil_psi","Gen oil","psi",0,"gen_oil_psi"],["gen.ac_v","Gen AC","V",0,"gen_ac_v"]] },
  salon: { kicker: "MAIN DECK", title: "Salon", hint: "House 24V.", fields: [["house_v","House bank","V",1,"volts_24"]] },
  galley: { kicker: "MID-LEVEL", title: "Galley", hint: "",
 fields: [["house_v","House bank","V",1,"volts_24"]] },
  master: { kicker: "FORWARD", title: "Master", hint: "", fields: [["house_v","House bank","V",1,"volts_24"]] },
  guest: { kicker: "PORT", title: "Guest", hint: "", fields: [["house_v","House bank","V",1,"volts_24"]] },
  tower: { kicker: "TOWER", title: "Tuna tower", hint: "", fields: [["port.rpm","Port RPM","rpm",0,"rpm"]] },
  portpod: { kicker: "ZEUS PORT", title: "Port pod", hint: "5-P4DB74KH", fields: [["port.rpm","Engine RPM","rpm",0,"rpm"]] },
  stbdpod: { kicker: "ZEUS STARBOARD", title: "Starboard pod", hint: "5-Q4DB74KH", fields: [["stbd.rpm","Engine RPM","rpm",0,"rpm"]] },
  seakeeper: { kicker: "GYRO", title: "Seakeeper", hint: "", fields: [["seakeeper.rpm","Flywheel","rpm",0,"hours"]] }
};
let zonesCfg = {}, current = "overview", lastState = {};
function getPath(obj, path) { return path.split(".").reduce((o,k) => (o == null ? o : o[k]), obj); }
function zoneFor(key, value, runningHint) {
  const z = zonesCfg[key];
  if (value == null || Number.isNaN(value) || !z) return "idle";
  if (z.running_only_low && !runningHint && z.red_low != null && value < z.red_low) return "idle";
  if (z.red_high != null && value >= z.red_high) return "red";
  if (z.red_low != null && value <= z.red_low) return "red";
  const yg = z.yellow || [null,null], gg = z.green || [null,null];
  if (yg[0] != null && value >= Math.min(yg[0], yg[1]) && value <= Math.max(yg[0], yg[1]) && !(value >= gg[0] && value <= gg[1])) return "yellow";
  if (gg[0] != null && value >= gg[0] && value <= gg[1]) return "green";
  return "green";
}
function fmt(v, d) { if (v === true) return "RUN"; if (v === false) return "OFF"; if (v == null || Number.isNaN(v)) return "—"; return Number(v).toFixed(d); }
function renderZone(name, st) {
  const spec = ZONES[name] || ZONES.overview;
  document.getElementById("zone-kicker").textContent = spec.kicker;
  document.getElementById("zone-title").textContent = spec.title;
  document.getElementById("zone-hint").textContent = spec.hint || "";
  document.getElementById("zone-grid").innerHTML = spec.fields.map(([path,label,unit,digits,zoneKey]) => {
    const raw = getPath(st, path);
    const runningHint = path.startsWith("gen") ? !!(st.gen || {}).running : !!st.running;
    const z = typeof raw === "number" ? zoneFor(zoneKey, raw, runningHint) : (raw ? "green" : "idle");
    const shown = path.endsWith("running") ? (raw ? "RUN" : "OFF") : fmt(raw, digits);
    return '<div class="metric '+z+'"><div class="label">'+label+'</div><div class="value">'+shown+'</div><div class="state">'+z.toUpperCase()+'</div></div>';
  }).join("");
}
function openZone(name) {
  current = name;
  document.getElementById("drawer").classList.add("open");
  renderZone(name, lastState);
}
async function tick() {
  const st = await (await fetch("/api/state", {cache:"no-store"})).json();
  lastState = st;
  if (!zonesCfg.rpm) {
    const cfg = await (await fetch("/api/config", {cache:"no-store"})).json();
    zonesCfg = cfg.zones || {};
  }
  const mode = document.getElementById("mode");
  if (mode) mode.textContent = st.mode || "demo";
  document.querySelectorAll(".hot").forEach((el) => {
    const z = el.dataset.zone;
    el.classList.remove("green","yellow","red","idle");
    el.classList.add("idle");
  });
  renderZone(current, st);
}
document.querySelectorAll(".hot").forEach((el) => el.addEventListener("click", () => openZone(el.dataset.zone)));
const closeBtn = document.getElementById("close-drawer");
if (closeBtn) closeBtn.onclick = () => { current = "overview"; document.getElementById("drawer").classList.remove("open"); renderZone("overview", lastState); };
setInterval(() => { tick().catch(()=>{}); }, 400);
tick().catch(()=>{});
