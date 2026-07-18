/* global React, ReactDOM */
const { useState, useEffect, useCallback } = React;

// ── API helper (same-origin, session cookie + CSRF) ─────────────────────
const API = "/api/v1";

function getCookie(name) {
  const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
  return m ? m.pop() : "";
}

async function api(path, { method = "GET", body } = {}) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (method !== "GET") opts.headers["X-CSRFToken"] = getCookie("csrftoken");
  const res = await fetch(API + path, opts);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || (Array.isArray(data) ? data.join(", ") : JSON.stringify(data));
    throw new Error(msg);
  }
  return data;
}

const CUR = { INR: "₹", USD: "$", EUR: "€" };
const money = (v, c = "INR") => `${CUR[c] || ""}${Number(v).toFixed(2)}`;

// ── Small UI helpers ────────────────────────────────────────────────────
function Spinner() {
  return (
    <div className="spinner-center">
      <div className="spinner-border text-primary" role="status" />
    </div>
  );
}

function Alert({ msg, onClose }) {
  if (!msg) return null;
  return (
    <div className="alert alert-danger alert-dismissible d-flex" role="alert">
      <div className="flex-grow-1">{msg}</div>
      <button className="btn-close" onClick={onClose} />
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="mb-2">
      <label className="form-label small text-secondary mb-1">{label}</label>
      {children}
    </div>
  );
}

// ── Chart.js wrapper ────────────────────────────────────────────────────
const PALETTE = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444",
  "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#64748b", "#22c55e", "#eab308"];

function ChartCanvas({ type, data, options, height = 240 }) {
  const ref = React.useRef(null);
  const chartRef = React.useRef(null);
  useEffect(() => {
    if (!ref.current || typeof Chart === "undefined") return;
    chartRef.current = new Chart(ref.current, {
      type,
      data,
      options: Object.assign(
        { responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } } },
        options || {}
      ),
    });
    return () => { if (chartRef.current) chartRef.current.destroy(); };
  }, [type, JSON.stringify(data), JSON.stringify(options)]);
  return <div style={{ height }}><canvas ref={ref} /></div>;
}

function EmptyChart({ msg }) {
  return <div className="text-secondary text-center py-4 small">{msg}</div>;
}

// ── Login ───────────────────────────────────────────────────────────────
function Login({ config }) {
  const googleOn = config && config.google_configured;
  const showDev = config && (config.debug || !googleOn);
  return (
    <div className="d-flex flex-column align-items-center justify-content-center" style={{ minHeight: "80vh" }}>
      <div className="card p-4 p-md-5 text-center" style={{ maxWidth: 420 }}>
        <h3 className="mb-1">SplitCash</h3>
        <p className="text-secondary mb-4">Shared expenses with credit-card cashback tracking.</p>
        {googleOn ? (
          <a className="btn btn-primary btn-lg" href="/accounts/google/login/?process=login">
            <i className="bi bi-google me-2" /> Sign in with Google
          </a>
        ) : (
          <div className="alert alert-warning small mb-3">
            <i className="bi bi-exclamation-triangle me-1" />
            Google sign-in isn't configured yet (missing <code>GOOGLE_OAUTH_CLIENT_ID</code>).
            Add credentials to <code>backend/.env</code> to enable it.
          </div>
        )}
        {showDev && (
          <a className="btn btn-outline-secondary" href="/admin/login/?next=/">
            <i className="bi bi-person-badge me-2" />Dev sign-in (admin)
          </a>
        )}
        <p className="text-muted small mt-3 mb-0">
          {googleOn ? "Google is the only supported sign-in method." : "Dev sign-in is for local testing only."}
        </p>
      </div>
    </div>
  );
}

// ── Nav ─────────────────────────────────────────────────────────────────
function Nav({ me, view, onNav, onLogout }) {
  const link = (name, label, icon) => (
    <button className={`btn btn-sm ${view === name ? "btn-primary" : "btn-outline-secondary"}`}
      onClick={() => onNav(name)}><i className={`bi ${icon} me-1`} />{label}</button>
  );
  return (
    <nav className="navbar navbar-expand bg-white shadow-sm mb-4">
      <div className="container app-shell">
        <span className="navbar-brand clickable" onClick={() => onNav("groups")}>
          <i className="bi bi-wallet2 text-primary me-2" />SplitCash
        </span>
        <div className="d-flex align-items-center gap-2 ms-3">
          {link("groups", "Groups", "bi-people")}
          {link("dashboard", "Dashboard", "bi-speedometer2")}
          {link("import", "Import", "bi-box-arrow-in-down")}
        </div>
        <div className="ms-auto d-flex align-items-center gap-3">
          <span className="text-secondary small d-none d-sm-inline">{me.email}</span>
          <button className="btn btn-outline-secondary btn-sm" onClick={onLogout}>Sign out</button>
        </div>
      </div>
    </nav>
  );
}

// ── Groups list ─────────────────────────────────────────────────────────
function GroupsList({ onOpen, onError }) {
  const [groups, setGroups] = useState(null);
  const [form, setForm] = useState({ name: "", base_currency: "INR" });
  const [friend, setFriend] = useState({ email: "", other_name: "", base_currency: "INR" });

  const load = useCallback(() => {
    api("/groups/").then(setGroups).catch((e) => onError(e.message));
  }, [onError]);
  useEffect(load, [load]);

  const createGroup = async () => {
    if (!form.name.trim()) return;
    try {
      await api("/groups/", { method: "POST", body: form });
      setForm({ name: "", base_currency: "INR" });
      load();
    } catch (e) { onError(e.message); }
  };
  const createFriend = async () => {
    try {
      const body = { base_currency: friend.base_currency };
      if (friend.email) body.email = friend.email;
      else if (friend.other_name) body.other_name = friend.other_name;
      else return;
      const g = await api("/groups/friend/", { method: "POST", body });
      setFriend({ email: "", other_name: "", base_currency: "INR" });
      load();
      onOpen(g.id);
    } catch (e) { onError(e.message); }
  };

  if (!groups) return <Spinner />;
  return (
    <div className="row g-4">
      <div className="col-lg-7">
        <h5 className="mb-3">Your groups</h5>
        {groups.length === 0 && <p className="text-secondary">No groups yet — create one on the right.</p>}
        <div className="list-group">
          {groups.map((g) => (
            <button key={g.id} className="list-group-item list-group-item-action d-flex align-items-center"
              onClick={() => onOpen(g.id)}>
              <i className={`bi ${g.is_friend ? "bi-person-heart" : "bi-people"} me-3 fs-5 text-primary`} />
              <div className="text-start">
                <div className="fw-semibold">{g.name}</div>
                <div className="small text-secondary">
                  {g.is_friend ? "Friend" : "Group"} · {g.base_currency} · {g.members.length} members
                </div>
              </div>
              <i className="bi bi-chevron-right ms-auto text-secondary" />
            </button>
          ))}
        </div>
      </div>
      <div className="col-lg-5">
        <div className="card p-3 mb-3">
          <h6>New group</h6>
          <Field label="Name">
            <input className="form-control" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Goa Trip" />
          </Field>
          <Field label="Base currency">
            <select className="form-select" value={form.base_currency}
              onChange={(e) => setForm({ ...form, base_currency: e.target.value })}>
              <option>INR</option><option>USD</option><option>EUR</option>
            </select>
          </Field>
          <button className="btn btn-primary w-100 mt-1" onClick={createGroup}>Create group</button>
        </div>
        <div className="card p-3">
          <h6>Add a friend <span className="badge badge-soft ms-1">1:1</span></h6>
          <Field label="Their Google email (if registered)">
            <input className="form-control" value={friend.email}
              onChange={(e) => setFriend({ ...friend, email: e.target.value })} placeholder="ritik@gmail.com" />
          </Field>
          <div className="text-center text-secondary small my-1">or add a placeholder</div>
          <Field label="Name (placeholder)">
            <input className="form-control" value={friend.other_name}
              onChange={(e) => setFriend({ ...friend, other_name: e.target.value })} placeholder="Ritik" />
          </Field>
          <button className="btn btn-outline-primary w-100 mt-1" onClick={createFriend}>Start friend group</button>
        </div>
      </div>
    </div>
  );
}

// ── Members tab ─────────────────────────────────────────────────────────
function MembersTab({ group, reload, onError }) {
  const [add, setAdd] = useState({ email: "", display_name: "" });
  const doAdd = async () => {
    try {
      const body = {};
      if (add.email) body.email = add.email;
      if (add.display_name) body.display_name = add.display_name;
      await api(`/groups/${group.id}/members/`, { method: "POST", body });
      setAdd({ email: "", display_name: "" });
      reload();
    } catch (e) { onError(e.message); }
  };
  const link = async (m) => {
    const email = prompt(`Link "${m.display_name}" to which Google email?`);
    if (!email) return;
    try { await api(`/members/${m.id}/link/`, { method: "POST", body: { email } }); reload(); }
    catch (e) { onError(e.message); }
  };
  return (
    <div className="row g-4">
      <div className="col-md-7">
        <div className="list-group">
          {group.members.map((m) => (
            <div key={m.id} className="list-group-item d-flex align-items-center">
              <i className="bi bi-person-circle me-2 text-secondary" />
              <div>
                <div className="fw-semibold">{m.display_name} {m.role === "owner" && <span className="badge badge-soft">owner</span>}</div>
                <div className="small text-secondary">{m.email || (m.is_placeholder ? "placeholder" : "")}</div>
              </div>
              {m.is_placeholder && (
                <button className="btn btn-sm btn-outline-primary ms-auto" onClick={() => link(m)}>Link account</button>
              )}
            </div>
          ))}
        </div>
      </div>
      {!group.is_friend && (
        <div className="col-md-5">
          <div className="card p-3">
            <h6>Add member</h6>
            <Field label="Google email"><input className="form-control" value={add.email}
              onChange={(e) => setAdd({ ...add, email: e.target.value })} placeholder="friend@gmail.com" /></Field>
            <div className="text-center text-secondary small my-1">or placeholder</div>
            <Field label="Name"><input className="form-control" value={add.display_name}
              onChange={(e) => setAdd({ ...add, display_name: e.target.value })} placeholder="Ritik" /></Field>
            <button className="btn btn-primary w-100 mt-1" onClick={doAdd}>Add</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Expense form ────────────────────────────────────────────────────────
// ── Expense form (create + edit) ────────────────────────────────────────
function ExpenseForm({ group, cards, categories, expense, onDone, onError }) {
  const members = group.members;
  const editing = !!expense;
  const [f, setF] = useState(editing ? {
    description: expense.description, currency: expense.currency,
    total_amount: String(expense.total_amount), date: expense.date,
    merchant: expense.merchant || "", payment_mode: expense.payment_mode || "cash",
    card_id: expense.card || "", simplify_override: expense.simplify_override,
    category_id: expense.category || "",
  } : {
    description: "", currency: group.base_currency, total_amount: "",
    date: new Date().toISOString().slice(0, 10), merchant: "", payment_mode: "cash",
    card_id: "", simplify_override: false, category_id: "",
  });
  const [payers, setPayers] = useState(editing
    ? expense.payers.map((p) => ({ member: p.member, amount_paid: String(p.amount_paid) }))
    : [{ member: members[0]?.id, amount_paid: "" }]);
  const [splits, setSplits] = useState(editing
    ? expense.splits.map((s) => ({ member: s.member, share_amount: String(s.share_amount) }))
    : members.map((m) => ({ member: m.id, share_amount: "" })));
  const [preview, setPreview] = useState(null);
  const [best, setBest] = useState(null);

  const splitEqually = () => {
    const total = parseFloat(f.total_amount || "0");
    if (!total) return;
    const per = Math.floor((total / members.length) * 100) / 100;
    const arr = members.map((m) => ({ member: m.id, share_amount: per.toFixed(2) }));
    let rem = Math.round((total - per * members.length) * 100);
    for (let i = 0; rem > 0; i = (i + 1) % arr.length, rem--)
      arr[i].share_amount = (parseFloat(arr[i].share_amount) + 0.01).toFixed(2);
    setSplits(arr);
  };

  const checkCashback = async () => {
    if (!f.card_id || !f.total_amount) return;
    try {
      const q = await api("/cashback/", { method: "POST", body: { card: Number(f.card_id), merchant: f.merchant, amount: f.total_amount } });
      setPreview(q);
    } catch (e) { onError(e.message); }
  };
  const findBest = async () => {
    if (!f.total_amount) return;
    try {
      const r = await api("/cashback/best-card/", { method: "POST", body: { group: group.id, merchant: f.merchant, amount: f.total_amount } });
      setBest(r.ranked);
    } catch (e) { onError(e.message); }
  };

  const submit = async () => {
    try {
      const body = {
        group: group.id, description: f.description, currency: f.currency,
        total_amount: f.total_amount, date: f.date, merchant: f.merchant,
        payment_mode: f.card_id ? "card" : f.payment_mode,
        simplify_override: f.simplify_override,
        category_id: f.category_id ? Number(f.category_id) : null,
        payers: payers.filter((p) => p.member && p.amount_paid).map((p) => ({ member: Number(p.member), amount_paid: p.amount_paid })),
        splits: splits.filter((s) => s.member && s.share_amount).map((s) => ({ member: Number(s.member), share_amount: s.share_amount })),
      };
      if (f.card_id) body.card_id = Number(f.card_id);
      if (editing) await api(`/expenses/${expense.id}/`, { method: "PUT", body });
      else await api("/expenses/", { method: "POST", body });
      onDone();
    } catch (e) { onError(e.message); }
  };

  const row = (list, setList, key) => list.map((it, i) => (
    <div className="d-flex gap-2 mb-2" key={i}>
      <select className="form-select" value={it.member || ""}
        onChange={(e) => { const c = [...list]; c[i].member = e.target.value; setList(c); }}>
        {members.map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}
      </select>
      <input className="form-control" style={{ maxWidth: 130 }} placeholder="0.00" value={it[key]}
        onChange={(e) => { const c = [...list]; c[i][key] = e.target.value; setList(c); }} />
      <button className="btn btn-outline-danger" onClick={() => setList(list.filter((_, j) => j !== i))}>
        <i className="bi bi-x" /></button>
    </div>
  ));

  return (
    <div className="card p-3">
      <div className="row">
        <div className="col-md-6">
          <Field label="Description"><input className="form-control" value={f.description}
            onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Dinner" /></Field>
        </div>
        <div className="col-md-3">
          <Field label="Amount"><input className="form-control" value={f.total_amount}
            onChange={(e) => setF({ ...f, total_amount: e.target.value })} placeholder="100.00" /></Field>
        </div>
        <div className="col-md-3">
          <Field label="Currency"><select className="form-select" value={f.currency}
            onChange={(e) => setF({ ...f, currency: e.target.value })}>
            <option>INR</option><option>USD</option><option>EUR</option></select></Field>
        </div>
        <div className="col-md-3">
          <Field label="Date"><input type="date" className="form-control" value={f.date}
            onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        </div>
        <div className="col-md-4">
          <Field label="Category">
            <select className="form-select" value={f.category_id}
              onChange={(e) => setF({ ...f, category_id: e.target.value })}>
              <option value="">— none —</option>
              {(categories || []).map((c) => (
                <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="col-md-4">
          <Field label="Merchant"><input className="form-control" value={f.merchant}
            onChange={(e) => setF({ ...f, merchant: e.target.value })} placeholder="Swiggy" /></Field>
        </div>
        <div className="col-md-5">
          <Field label="Paid via card (cashback)">
            <div className="d-flex gap-2">
              <select className="form-select" value={f.card_id}
                onChange={(e) => { setF({ ...f, card_id: e.target.value }); setPreview(null); }}>
                <option value="">— none —</option>
                {cards.map((c) => <option key={c.id} value={c.id}>{c.display_name} ({c.owner_name})</option>)}
              </select>
              <button className="btn btn-outline-secondary" onClick={checkCashback} title="Preview cashback">
                <i className="bi bi-magic" /></button>
              <button className="btn btn-outline-secondary" onClick={findBest} title="Best card">
                <i className="bi bi-trophy" /></button>
            </div>
          </Field>
        </div>
      </div>

      {preview && (
        <div className={`alert ${Number(preview.eligible) > 0 ? "alert-success" : "alert-warning"} py-2`}>
          Cashback: <strong>{money(preview.eligible, group.base_currency)}</strong>
          {" "}({preview.percent}% of base) {preview.capped_by.length > 0 && <span className="small">· capped by {preview.capped_by.join(", ")}</span>}
          {preview.reason && <span className="small"> · {preview.reason}</span>}
        </div>
      )}
      {best && (
        <div className="alert alert-info py-2">
          <strong>Best card:</strong>{" "}
          {best.length ? best.map((b) => `${b.card_name} → ${money(b.eligible, group.base_currency)}`).join("  |  ") : "no cards"}
        </div>
      )}

      <div className="row">
        <div className="col-md-6">
          <label className="form-label small text-secondary mb-1">Paid by</label>
          {row(payers, setPayers, "amount_paid")}
          <button className="btn btn-sm btn-link p-0" onClick={() => setPayers([...payers, { member: members[0]?.id, amount_paid: "" }])}>
            <i className="bi bi-plus" /> add payer</button>
        </div>
        <div className="col-md-6">
          <div className="d-flex justify-content-between">
            <label className="form-label small text-secondary mb-1">Split between</label>
            <button className="btn btn-sm btn-link p-0" onClick={splitEqually}>split equally</button>
          </div>
          {row(splits, setSplits, "share_amount")}
          <button className="btn btn-sm btn-link p-0" onClick={() => setSplits([...splits, { member: members[0]?.id, share_amount: "" }])}>
            <i className="bi bi-plus" /> add split</button>
        </div>
      </div>

      <div className="form-check mt-2">
        <input className="form-check-input" type="checkbox" checked={f.simplify_override}
          onChange={(e) => setF({ ...f, simplify_override: e.target.checked })} id="ov" />
        <label className="form-check-label small" htmlFor="ov">Keep as a direct debt (exclude from simplification)</label>
      </div>
      <div className="d-flex gap-2 mt-3">
        <button className="btn btn-primary" onClick={submit}>{editing ? "Update expense" : "Save expense"}</button>
        <button className="btn btn-outline-secondary" onClick={onDone}>Cancel</button>
      </div>
    </div>
  );
}

// ── Expenses tab ────────────────────────────────────────────────────────
function ExpensesTab({ group, cards, onError }) {
  const [expenses, setExpenses] = useState(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [comment, setComment] = useState("");
  const [categories, setCategories] = useState([]);

  const load = useCallback(() => {
    api(`/expenses/?group=${group.id}`).then((d) => setExpenses(d.results || d)).catch((e) => onError(e.message));
  }, [group.id, onError]);
  useEffect(load, [load]);
  useEffect(() => { api("/categories/").then((d) => setCategories(d.results || d)).catch(() => {}); }, []);

  const del = async (id) => {
    if (!confirm("Delete this expense?")) return;
    try { await api(`/expenses/${id}/`, { method: "DELETE" }); load(); } catch (e) { onError(e.message); }
  };
  const addComment = async (id) => {
    if (!comment.trim()) return;
    try { await api(`/expenses/${id}/comments/`, { method: "POST", body: { body: comment } }); setComment(""); load(); }
    catch (e) { onError(e.message); }
  };

  if (!expenses) return <Spinner />;
  return (
    <div>
      {!adding && !editing && <button className="btn btn-primary mb-3" onClick={() => setAdding(true)}><i className="bi bi-plus-lg me-1" />Add expense</button>}
      {adding && <div className="mb-3"><ExpenseForm group={group} cards={cards} categories={categories}
        onDone={() => { setAdding(false); load(); }} onError={onError} /></div>}
      {editing && <div className="mb-3"><ExpenseForm group={group} cards={cards} categories={categories} expense={editing}
        onDone={() => { setEditing(null); load(); }} onError={onError} /></div>}
      {expenses.length === 0 && <p className="text-secondary">No expenses yet.</p>}
      <div className="list-group">
        {expenses.map((e) => (
          <div key={e.id} className="list-group-item">
            <div className="d-flex align-items-center clickable" onClick={() => setOpenId(openId === e.id ? null : e.id)}>
              <div>
                <div className="fw-semibold">
                  {e.category_icon && <span className="me-1">{e.category_icon}</span>}{e.description}
                  {Number(e.cashback_amount) > 0 && <span className="badge bg-success ms-2">CB {money(e.cashback_amount, group.base_currency)}</span>}
                  {e.simplify_override && <span className="badge bg-secondary ms-1">direct</span>}
                </div>
                <div className="small text-secondary">
                  {e.date} · {money(e.total_amount, e.currency)}{e.currency !== group.base_currency && ` (${money(e.base_amount, group.base_currency)})`}
                  {e.category_name && ` · ${e.category_name}`}
                  {e.card_name && ` · ${e.card_name}`}{e.merchant && ` · ${e.merchant}`}
                </div>
              </div>
              <div className="ms-auto text-secondary small">
                {e.payers.map((p) => p.member_name).join(", ")} paid
                <i className={`bi ms-2 bi-chevron-${openId === e.id ? "up" : "down"}`} />
              </div>
            </div>
            {openId === e.id && (
              <div className="mt-3 border-top pt-3">
                <div className="row">
                  <div className="col-md-6">
                    <div className="small text-secondary">Paid by</div>
                    {e.payers.map((p, i) => <div key={i}>{p.member_name}: {money(p.amount_paid, e.currency)}</div>)}
                  </div>
                  <div className="col-md-6">
                    <div className="small text-secondary">Split</div>
                    {e.splits.map((s, i) => <div key={i}>{s.member_name}: {money(s.share_amount, e.currency)}</div>)}
                  </div>
                </div>
                <div className="mt-3">
                  <div className="small text-secondary mb-1"><i className="bi bi-chat-left-text me-1" />Comments</div>
                  {e.comments.map((c) => (
                    <div key={c.id} className="small mb-1"><strong>{c.author_name}:</strong> {c.body}</div>
                  ))}
                  <div className="d-flex gap-2 mt-2">
                    <input className="form-control form-control-sm" placeholder="Add a comment…"
                      value={comment} onChange={(ev) => setComment(ev.target.value)} />
                    <button className="btn btn-sm btn-outline-primary" onClick={() => addComment(e.id)}>Post</button>
                  </div>
                </div>
                <div className="d-flex gap-2 mt-3">
                  <button className="btn btn-sm btn-outline-secondary" onClick={() => { setEditing(e); setOpenId(null); }}>
                    <i className="bi bi-pencil me-1" />Edit</button>
                  <button className="btn btn-sm btn-outline-danger" onClick={() => del(e.id)}>Delete</button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Balances tab ────────────────────────────────────────────────────────
function BalancesTab({ group, reload, onError }) {
  const [sum, setSum] = useState(null);
  const [settle, setSettle] = useState({ from_member: "", to_member: "", amount: "", note: "" });

  const load = useCallback(() => {
    api(`/balances/?group=${group.id}`).then(setSum).catch((e) => onError(e.message));
  }, [group.id, onError]);
  useEffect(load, [load]);

  const toggleSimplify = async () => {
    try { await api(`/groups/${group.id}/simplify/`, { method: "PATCH", body: { simplify_enabled: !group.simplify_enabled } }); reload(); load(); }
    catch (e) { onError(e.message); }
  };
  const record = async (from, to, amount) => {
    try {
      await api("/settlements/", { method: "POST", body: {
        group: group.id, from_member: Number(from), to_member: Number(to),
        amount, currency: group.base_currency, date: new Date().toISOString().slice(0, 10),
      } });
      load();
    } catch (e) { onError(e.message); }
  };

  if (!sum) return <Spinner />;
  return (
    <div className="row g-4">
      <div className="col-md-6">
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h6 className="mb-0">Balances</h6>
          <div className="form-check form-switch">
            <input className="form-check-input" type="checkbox" checked={group.simplify_enabled} onChange={toggleSimplify} id="simp" />
            <label className="form-check-label small" htmlFor="simp">Simplify debts</label>
          </div>
        </div>
        {sum.balances.length === 0 && <p className="text-secondary">All settled up! 🎉</p>}
        <div className="list-group mb-3">
          {sum.balances.map((b) => (
            <div key={b.member} className="list-group-item d-flex justify-content-between">
              <span>{b.member_name}</span>
              <span className={Number(b.net) >= 0 ? "net-pos" : "net-neg"}>
                {Number(b.net) >= 0 ? "gets back " : "owes "}{money(Math.abs(Number(b.net)), sum.base_currency)}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="col-md-6">
        <h6 className="mb-2">Suggested settlements</h6>
        {sum.suggested_settlements.length === 0 && <p className="text-secondary">Nothing to settle.</p>}
        <div className="list-group">
          {sum.suggested_settlements.map((t, i) => (
            <div key={i} className="list-group-item d-flex align-items-center">
              <span><strong>{t.from_name}</strong> → <strong>{t.to_name}</strong></span>
              <span className="ms-auto me-3">{money(t.amount, sum.base_currency)}</span>
              <button className="btn btn-sm btn-outline-success" onClick={() => record(t.from_member, t.to_member, t.amount)}>
                Mark paid</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Cards tab ───────────────────────────────────────────────────────────
function CardsTab({ group, cards, reloadCards, onError }) {
  const [card, setCard] = useState({ owner: "", display_name: "", issuer: "", network: "other", billing_cycle_day: "", last4: "", expiry: "" });
  const [prog, setProg] = useState({ card: "", merchant: "ANY", percent: "", max_per_txn: "", cap_per_month: "", max_per_day: "", payout: "cash", wallet: "", coin_expiry_days: "" });
  const [wallets, setWallets] = useState([]);
  const [wallet, setWallet] = useState({ owner: "", name: "", coin_rate: "", currency: group.base_currency });

  const loadWallets = useCallback(() => {
    api("/wallets/").then((d) => setWallets((d.results || d).filter((w) => w.group === group.id))).catch(() => {});
  }, [group.id]);
  useEffect(loadWallets, [loadWallets]);

  const addCard = async () => {
    try {
      const body = { group: group.id, owner: Number(card.owner), display_name: card.display_name,
        issuer: card.issuer, network: card.network };
      if (card.billing_cycle_day) body.billing_cycle_day = Number(card.billing_cycle_day);
      if (card.last4) body.last4 = card.last4;
      if (card.expiry) body.expiry = card.expiry;
      await api("/cards/", { method: "POST", body });
      setCard({ owner: "", display_name: "", issuer: "", network: "other", billing_cycle_day: "", last4: "", expiry: "" });
      reloadCards();
    } catch (e) { onError(e.message); }
  };
  const addProgram = async () => {
    try {
      const body = { card: Number(prog.card), merchant: prog.merchant || "ANY", percent: prog.percent, currency: group.base_currency, payout: prog.payout };
      ["max_per_txn", "cap_per_month", "max_per_day"].forEach((k) => { if (prog[k]) body[k] = prog[k]; });
      if (prog.payout === "coins") {
        if (!prog.wallet) { onError("Select a wallet for coin payout."); return; }
        body.wallet = Number(prog.wallet);
        if (prog.coin_expiry_days) body.coin_expiry_days = Number(prog.coin_expiry_days);
      }
      await api("/cashback-programs/", { method: "POST", body });
      setProg({ card: "", merchant: "ANY", percent: "", max_per_txn: "", cap_per_month: "", max_per_day: "", payout: "cash", wallet: "", coin_expiry_days: "" });
      reloadCards();
    } catch (e) { onError(e.message); }
  };
  const addWallet = async () => {
    try {
      await api("/wallets/", { method: "POST", body: {
        group: group.id, owner: Number(wallet.owner), name: wallet.name,
        coin_rate: wallet.coin_rate || "1", currency: group.base_currency,
      } });
      setWallet({ owner: "", name: "", coin_rate: "", currency: group.base_currency });
      loadWallets();
    } catch (e) { onError(e.message); }
  };

  return (
    <div className="row g-4">
      <div className="col-lg-6">
        <h6>Cards in this group</h6>
        {cards.length === 0 && <p className="text-secondary">No cards yet.</p>}
        {cards.map((c) => (
          <div key={c.id} className="card p-3 mb-2">
            <div className="d-flex align-items-center">
              <i className="bi bi-credit-card-2-front fs-4 me-3 text-primary" />
              <div>
                <div className="fw-semibold">{c.display_name} {!c.is_active && <span className="badge bg-secondary">inactive</span>}</div>
                <div className="small text-secondary">{c.issuer} · {c.network} · owner {c.owner_name}{c.has_last4 ? " · ••••" : ""}</div>
              </div>
            </div>
            {c.programs.length > 0 && (
              <ul className="small mt-2 mb-0">
                {c.programs.map((p) => (
                  <li key={p.id}>{p.percent}% @ {p.merchant}{p.max_per_txn ? ` · max ${money(p.max_per_txn, group.base_currency)}/txn` : ""}
                    {p.max_per_day ? ` · ${p.max_per_day}/day` : ""}{p.payout === "coins" ? " · 🪙 coins" : ""}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
      <div className="col-lg-6">
        <div className="card p-3 mb-3">
          <h6>Add card</h6>
          <Field label="Owner"><select className="form-select" value={card.owner}
            onChange={(e) => setCard({ ...card, owner: e.target.value })}>
            <option value="">— select —</option>
            {group.members.map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}</select></Field>
          <div className="row">
            <div className="col-7"><Field label="Display name"><input className="form-control" value={card.display_name}
              onChange={(e) => setCard({ ...card, display_name: e.target.value })} placeholder="Swiggy HDFC" /></Field></div>
            <div className="col-5"><Field label="Issuer"><input className="form-control" value={card.issuer}
              onChange={(e) => setCard({ ...card, issuer: e.target.value })} placeholder="HDFC" /></Field></div>
          </div>
          <div className="row">
            <div className="col-5"><Field label="Network"><select className="form-select" value={card.network}
              onChange={(e) => setCard({ ...card, network: e.target.value })}>
              <option value="visa">Visa</option><option value="mastercard">Mastercard</option>
              <option value="rupay">RuPay</option><option value="amex">Amex</option><option value="other">Other</option>
            </select></Field></div>
            <div className="col-3"><Field label="Bill day"><input className="form-control" value={card.billing_cycle_day}
              onChange={(e) => setCard({ ...card, billing_cycle_day: e.target.value })} placeholder="5" /></Field></div>
            <div className="col-2"><Field label="Last4"><input className="form-control" value={card.last4}
              onChange={(e) => setCard({ ...card, last4: e.target.value })} placeholder="1234" /></Field></div>
            <div className="col-2"><Field label="Expiry"><input className="form-control" value={card.expiry}
              onChange={(e) => setCard({ ...card, expiry: e.target.value })} placeholder="12/28" /></Field></div>
          </div>
          <p className="small text-muted mb-2">Last4/expiry are optional, encrypted, and never shown back.</p>
          <button className="btn btn-primary w-100" onClick={addCard}>Add card</button>
        </div>
        <div className="card p-3">
          <h6>Add cashback program</h6>
          <Field label="Card"><select className="form-select" value={prog.card}
            onChange={(e) => setProg({ ...prog, card: e.target.value })}>
            <option value="">— select —</option>
            {cards.map((c) => <option key={c.id} value={c.id}>{c.display_name}</option>)}</select></Field>
          <div className="row">
            <div className="col-6"><Field label="Merchant (or ANY)"><input className="form-control" value={prog.merchant}
              onChange={(e) => setProg({ ...prog, merchant: e.target.value })} placeholder="Swiggy" /></Field></div>
            <div className="col-6"><Field label="Percent"><input className="form-control" value={prog.percent}
              onChange={(e) => setProg({ ...prog, percent: e.target.value })} placeholder="10" /></Field></div>
          </div>
          <div className="row">
            <div className="col-4"><Field label="Max/txn"><input className="form-control" value={prog.max_per_txn}
              onChange={(e) => setProg({ ...prog, max_per_txn: e.target.value })} placeholder="50" /></Field></div>
            <div className="col-4"><Field label="Cap/month"><input className="form-control" value={prog.cap_per_month}
              onChange={(e) => setProg({ ...prog, cap_per_month: e.target.value })} placeholder="1500" /></Field></div>
            <div className="col-4"><Field label="Max/day (count)"><input className="form-control" value={prog.max_per_day}
              onChange={(e) => setProg({ ...prog, max_per_day: e.target.value })} placeholder="3" /></Field></div>
          </div>
          <div className="row">
            <div className="col-6"><Field label="Payout">
              <select className="form-select" value={prog.payout}
                onChange={(e) => setProg({ ...prog, payout: e.target.value })}>
                <option value="cash">Cash (reduces debt)</option>
                <option value="coins">Wallet coins (perk)</option>
              </select></Field></div>
            {prog.payout === "coins" && (
              <div className="col-6"><Field label="Wallet">
                <select className="form-select" value={prog.wallet}
                  onChange={(e) => setProg({ ...prog, wallet: e.target.value })}>
                  <option value="">— select —</option>
                  {wallets.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select></Field></div>
            )}
          </div>
          {prog.payout === "coins" && (
            <Field label="Coin expiry (days, optional)"><input className="form-control" value={prog.coin_expiry_days}
              onChange={(e) => setProg({ ...prog, coin_expiry_days: e.target.value })} placeholder="365" /></Field>
          )}
          <button className="btn btn-primary w-100 mt-1" onClick={addProgram}>Add program</button>
        </div>
        <div className="card p-3 mt-3">
          <h6><i className="bi bi-coin me-1" />Reward wallets</h6>
          {wallets.length === 0 && <p className="text-secondary small mb-2">No wallets yet (e.g. Flipkart Coins).</p>}
          {wallets.map((w) => (
            <div key={w.id} className="small d-flex justify-content-between border-bottom py-1">
              <span>{w.name} <span className="text-secondary">({w.owner_name})</span></span>
              <span>1 coin = {money(w.coin_rate, w.currency)}</span>
            </div>
          ))}
          <div className="row mt-2">
            <div className="col-5"><Field label="Owner"><select className="form-select" value={wallet.owner}
              onChange={(e) => setWallet({ ...wallet, owner: e.target.value })}>
              <option value="">— select —</option>
              {group.members.map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}</select></Field></div>
            <div className="col-4"><Field label="Name"><input className="form-control" value={wallet.name}
              onChange={(e) => setWallet({ ...wallet, name: e.target.value })} placeholder="Flipkart Coins" /></Field></div>
            <div className="col-3"><Field label="₹/coin"><input className="form-control" value={wallet.coin_rate}
              onChange={(e) => setWallet({ ...wallet, coin_rate: e.target.value })} placeholder="0.25" /></Field></div>
          </div>
          <button className="btn btn-outline-primary w-100" onClick={addWallet}>Add wallet</button>
        </div>
      </div>
    </div>
  );
}

// ── Per-group insights ──────────────────────────────────────────────────
function InsightsTab({ group, onError }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    api(`/analytics/group/?group=${group.id}`).then(setD).catch((e) => onError(e.message));
  }, [group.id]);
  if (!d) return <Spinner />;
  const ccy = d.currency;
  const catData = {
    labels: d.by_category.map((c) => `${c.icon} ${c.category}`),
    datasets: [{ data: d.by_category.map((c) => Number(c.amount)), backgroundColor: PALETTE }],
  };
  const monData = {
    labels: d.by_month.map((m) => m.month),
    datasets: [{ label: `Spend (${ccy})`, data: d.by_month.map((m) => Number(m.amount)), backgroundColor: PALETTE[0] }],
  };
  return (
    <div>
      <div className="row g-3 mb-3">
        <div className="col-sm-4"><div className="card p-3"><div className="text-secondary small">Total spend</div>
          <div className="fs-4 fw-semibold">{money(d.total_spend, ccy)}</div></div></div>
        <div className="col-sm-4"><div className="card p-3"><div className="text-secondary small">Cashback (cash)</div>
          <div className="fs-4 fw-semibold text-success">{money(d.total_cashback, ccy)}</div></div></div>
        <div className="col-sm-4"><div className="card p-3"><div className="text-secondary small">Expenses</div>
          <div className="fs-4 fw-semibold">{d.expense_count}</div></div></div>
      </div>
      <div className="row g-3">
        <div className="col-lg-5"><div className="card p-3"><h6>By category</h6>
          {d.by_category.length ? <ChartCanvas type="doughnut" data={catData} /> : <EmptyChart msg="No categorized expenses yet." />}</div></div>
        <div className="col-lg-7"><div className="card p-3"><h6>Monthly spend</h6>
          {d.by_month.length ? <ChartCanvas type="bar" data={monData} /> : <EmptyChart msg="No spend yet." />}</div></div>
      </div>
      {d.top_merchants.length > 0 && (
        <div className="card p-3 mt-3"><h6>Top merchants</h6>
          {d.top_merchants.map((m, i) => (
            <div key={i} className="d-flex justify-content-between small"><span>{m.name}</span><span>{money(m.amount, ccy)}</span></div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Cross-group dashboard ───────────────────────────────────────────────
function Dashboard({ onError }) {
  const [me, setMe] = useState(null);
  const [cards, setCards] = useState(null);
  useEffect(() => {
    api("/analytics/me/").then(setMe).catch((e) => onError(e.message));
    api("/analytics/cards/").then(setCards).catch((e) => onError(e.message));
  }, []);
  if (!me || !cards) return <Spinner />;
  const ccy = me.currency;
  const catData = {
    labels: me.by_category.map((c) => `${c.icon} ${c.category}`),
    datasets: [{ data: me.by_category.map((c) => Number(c.amount)), backgroundColor: PALETTE }],
  };
  const monData = {
    labels: me.by_month.map((m) => m.month),
    datasets: [{ label: `My spend (${ccy})`, data: me.by_month.map((m) => Number(m.amount)),
      borderColor: PALETTE[0], backgroundColor: "rgba(79,70,229,.15)", fill: true, tension: 0.3 }],
  };
  return (
    <div>
      <h4 className="mb-3"><i className="bi bi-speedometer2 me-2 text-primary" />Your dashboard</h4>
      <div className="card p-3 mb-3">
        <div className="text-secondary small">Your total spend (all groups, in {ccy})</div>
        <div className="fs-3 fw-semibold">{money(me.total_my_spend, ccy)}</div>
      </div>
      <div className="row g-3">
        <div className="col-lg-5"><div className="card p-3"><h6>Where your money goes</h6>
          {me.by_category.length ? <ChartCanvas type="doughnut" data={catData} /> : <EmptyChart msg="Add categorized expenses to see this." />}</div></div>
        <div className="col-lg-7"><div className="card p-3"><h6>Monthly trend</h6>
          {me.by_month.length ? <ChartCanvas type="line" data={monData} /> : <EmptyChart msg="No spend yet." />}</div></div>
      </div>

      <div className="row g-3 mt-1">
        <div className="col-lg-6"><div className="card p-3">
          <h6><i className="bi bi-credit-card me-1" />How friends used my cards</h6>
          {cards.my_cards.length === 0 && <EmptyChart msg="No cards of yours have been used yet." />}
          {cards.my_cards.map((c) => (
            <div key={c.card_id} className="mb-2 border-bottom pb-2">
              <div className="fw-semibold">{c.card_name}
                <span className="badge bg-success ms-2">earned {money(c.cashback_earned, ccy)}</span></div>
              <div className="small text-secondary">{c.count} expenses · {money(c.spend, ccy)} spent</div>
              {c.used_by.map((u, i) => (
                <div key={i} className="small d-flex justify-content-between"><span>{u.name}</span><span>{money(u.amount, ccy)}</span></div>
              ))}
            </div>
          ))}
        </div></div>
        <div className="col-lg-6"><div className="card p-3">
          <h6><i className="bi bi-wallet2 me-1" />How I used friends' cards</h6>
          {cards.friends_cards.length === 0 && <EmptyChart msg="You haven't used a friend's card yet." />}
          {cards.friends_cards.map((c) => (
            <div key={c.card_id} className="mb-2 border-bottom pb-2 d-flex justify-content-between">
              <div><div className="fw-semibold">{c.card_name}</div>
                <div className="small text-secondary">owner {c.owner} · {c.count} times</div></div>
              <div className="text-end"><div>{money(c.my_spend, ccy)}</div>
                <div className="small text-success">saved {money(c.my_cashback_benefit, ccy)}</div></div>
            </div>
          ))}
        </div></div>
      </div>

      {cards.wallets.length > 0 && (
        <div className="card p-3 mt-3">
          <h6><i className="bi bi-coin me-1" />My reward wallets</h6>
          {cards.wallets.map((w) => (
            <div key={w.wallet_id} className="d-flex justify-content-between align-items-center mb-1">
              <div><span className="fw-semibold">{w.name}</span>
                <span className="small text-secondary ms-2">{w.coins} coins @ {w.coin_rate}</span>
                {Number(w.expiring_soon_coins) > 0 && <span className="badge bg-warning text-dark ms-2">{w.expiring_soon_coins} expiring soon</span>}</div>
              <div className="fw-semibold text-success">{money(w.value, w.currency)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Splitwise import ────────────────────────────────────────────────────
function ImportSplitwise({ onError, onImported }) {
  const [apiKey, setApiKey] = useState("");
  const [groups, setGroups] = useState(null);
  const [selected, setSelected] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const preview = async () => {
    setBusy(true); setResult(null);
    try {
      const d = await api("/import/splitwise/groups/", { method: "POST", body: { api_key: apiKey } });
      setGroups(d.groups);
      setSelected(Object.fromEntries(d.groups.map((g) => [g.id, true])));
    } catch (e) { onError(e.message); } finally { setBusy(false); }
  };
  const doImport = async () => {
    setBusy(true);
    try {
      const ids = Object.keys(selected).filter((k) => selected[k]).map(Number);
      const d = await api("/import/splitwise/", { method: "POST", body: { api_key: apiKey, group_ids: ids } });
      setResult(d.results); onImported && onImported();
    } catch (e) { onError(e.message); } finally { setBusy(false); }
  };

  return (
    <div style={{ maxWidth: 640 }}>
      <h4 className="mb-1"><i className="bi bi-box-arrow-in-down me-2 text-primary" />Import from Splitwise</h4>
      <p className="text-secondary small">Paste your Splitwise API key (from secure.splitwise.com/apps → register app / get API key). The key is used once and never stored.</p>
      <div className="card p-3">
        <Field label="Splitwise API key">
          <input className="form-control" value={apiKey} type="password"
            onChange={(e) => setApiKey(e.target.value)} placeholder="paste key" />
        </Field>
        <button className="btn btn-outline-primary" onClick={preview} disabled={!apiKey || busy}>
          {busy ? "Working…" : "List my Splitwise groups"}</button>
      </div>

      {groups && (
        <div className="card p-3 mt-3">
          <h6>Select groups to import</h6>
          {groups.length === 0 && <p className="text-secondary small">No groups found.</p>}
          {groups.map((g) => (
            <div className="form-check" key={g.id}>
              <input className="form-check-input" type="checkbox" checked={!!selected[g.id]}
                onChange={(e) => setSelected({ ...selected, [g.id]: e.target.checked })} id={`g${g.id}`} />
              <label className="form-check-label" htmlFor={`g${g.id}`}>{g.name} <span className="text-secondary small">({g.members} members)</span></label>
            </div>
          ))}
          <button className="btn btn-primary mt-2" onClick={doImport} disabled={busy}>
            {busy ? "Importing…" : "Import selected"}</button>
        </div>
      )}

      {result && (
        <div className="alert alert-success mt-3">
          <div className="fw-semibold mb-1">Import complete</div>
          {result.map((r, i) => (
            <div key={i} className="small">{r.group}: {r.imported} expenses, {r.settlements} settlements{r.skipped ? `, ${r.skipped} skipped` : ""}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Group detail ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
function GroupDetail({ groupId, onBack, onError }) {
  const [group, setGroup] = useState(null);
  const [cards, setCards] = useState([]);
  const [tab, setTab] = useState("expenses");

  const reload = useCallback(() => {
    api(`/groups/${groupId}/`).then(setGroup).catch((e) => onError(e.message));
  }, [groupId, onError]);
  const reloadCards = useCallback(() => {
    api("/cards/").then((d) => setCards((d.results || d).filter((c) => c.group === Number(groupId)))).catch(() => {});
  }, [groupId]);
  useEffect(() => { reload(); reloadCards(); }, [reload, reloadCards]);

  if (!group) return <Spinner />;
  const tabs = [
    ["expenses", "Expenses", "bi-receipt"],
    ["balances", "Balances", "bi-bar-chart"],
    ["insights", "Insights", "bi-graph-up"],
    ["cards", "Cards", "bi-credit-card"],
    ["members", "Members", "bi-people"],
  ];
  return (
    <div>
      <button className="btn btn-link p-0 mb-2" onClick={onBack}><i className="bi bi-arrow-left me-1" />All groups</button>
      <div className="d-flex align-items-center mb-3">
        <h4 className="mb-0">{group.name}</h4>
        <span className="badge badge-soft ms-2">{group.base_currency}</span>
        {group.is_friend && <span className="badge bg-light text-dark ms-1">friend</span>}
      </div>
      <ul className="nav nav-pills mb-4">
        {tabs.map(([k, label, icon]) => (
          <li className="nav-item" key={k}>
            <button className={`nav-link ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>
              <i className={`bi ${icon} me-1`} />{label}</button>
          </li>
        ))}
      </ul>
      {tab === "expenses" && <ExpensesTab group={group} cards={cards} onError={onError} />}
      {tab === "balances" && <BalancesTab group={group} reload={reload} onError={onError} />}
      {tab === "insights" && <InsightsTab group={group} onError={onError} />}
      {tab === "cards" && <CardsTab group={group} cards={cards} reloadCards={reloadCards} onError={onError} />}
      {tab === "members" && <MembersTab group={group} reload={reload} onError={onError} />}
    </div>
  );
}

// ── Root app ────────────────────────────────────────────────────────────
function App() {
  const [me, setMe] = useState(undefined); // undefined = loading
  const [config, setConfig] = useState(null);
  const [view, setView] = useState({ name: "groups" });
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(API + "/auth/csrf/", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((cfg) => { setConfig(cfg); return api("/auth/me/"); })
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  const logout = async () => {
    try { await api("/auth/logout/", { method: "POST" }); } catch (_) {}
    window.location.href = "/accounts/logout/";
  };

  if (me === undefined) return <Spinner />;
  if (!me) return <Login config={config} />;

  return (
    <div>
      <Nav me={me} view={view.name} onNav={(name) => setView({ name })} onLogout={logout} />
      <div className="container app-shell pb-5">
        <Alert msg={error} onClose={() => setError("")} />
        {view.name === "groups" && <GroupsList onOpen={(id) => setView({ name: "group", id })} onError={setError} />}
        {view.name === "group" && <GroupDetail groupId={view.id} onBack={() => setView({ name: "groups" })} onError={setError} />}
        {view.name === "dashboard" && <Dashboard onError={setError} />}
        {view.name === "import" && <ImportSplitwise onError={setError} onImported={() => setView({ name: "groups" })} />}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
