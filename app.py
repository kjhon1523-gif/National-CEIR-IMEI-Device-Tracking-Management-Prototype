import os, re, sqlite3, hashlib, json, csv, io
from datetime import datetime, timezone, timedelta
from functools import wraps
from math import radians, sin, cos, sqrt, atan2
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, Response
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(APP_DIR, "ceir.db"))
SECRET = os.environ.get("SECRET_KEY", "development-only-change-this-secret")

ROLES = {
    "Regulator Administrator": {"dashboard","devices","lists","eir","events","cases","disputes","audit","reports","users"},
    "Regulator Analyst": {"dashboard","devices","lists","eir","events","disputes","reports"},
    "Operator Liaison": {"dashboard","devices","lists","eir","events","disputes","reports"},
    "Law Enforcement Officer": {"dashboard","cases"},
    "Law Enforcement Supervisor": {"dashboard","cases","audit"},
    "Data Protection Auditor": {"dashboard","audit","reports"},
}

app = Flask(__name__)
app.secret_key = SECRET
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
      role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS devices(
      id INTEGER PRIMARY KEY, imei TEXT UNIQUE NOT NULL, tac TEXT NOT NULL, model TEXT,
      brand TEXT, status TEXT NOT NULL DEFAULT 'GREYLISTED',
      source TEXT DEFAULT 'Manual demo entry', notes TEXT DEFAULT '',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS tac_registry(
      tac TEXT PRIMARY KEY, brand TEXT NOT NULL, model TEXT NOT NULL,
      rat TEXT DEFAULT '4G/5G', status TEXT DEFAULT 'ACTIVE', is_demo INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS overrides(
      id INTEGER PRIMARY KEY, imei TEXT NOT NULL, imsi TEXT NOT NULL,
      reason TEXT NOT NULL, authorized_by TEXT NOT NULL, expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS eir_nodes(
      id INTEGER PRIMARY KEY, operator_name TEXT NOT NULL, region TEXT,
      health TEXT DEFAULT 'ONLINE', last_sync TEXT, sync_lag_seconds INTEGER DEFAULT 0,
      local_version INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS sync_log(
      id INTEGER PRIMARY KEY, node_id INTEGER, action TEXT, result TEXT,
      list_version INTEGER, created_at TEXT);
    CREATE TABLE IF NOT EXISTS attach_events(
      id INTEGER PRIMARY KEY, imei TEXT NOT NULL, imsi TEXT NOT NULL,
      cell_id TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
      rat TEXT DEFAULT '4G', event_time TEXT NOT NULL, source TEXT DEFAULT 'SYNTHETIC');
    CREATE TABLE IF NOT EXISTS alerts(
      id INTEGER PRIMARY KEY, imei TEXT NOT NULL, severity TEXT NOT NULL,
      alert_type TEXT NOT NULL, description TEXT NOT NULL,
      status TEXT DEFAULT 'OPEN', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cases(
      id INTEGER PRIMARY KEY, case_ref TEXT UNIQUE NOT NULL, imei TEXT NOT NULL,
      warrant_id TEXT NOT NULL, issuing_court TEXT NOT NULL, purpose TEXT NOT NULL,
      requested_by TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
      supervisor TEXT, decision_note TEXT, created_at TEXT NOT NULL, decided_at TEXT);
    CREATE TABLE IF NOT EXISTS disputes(
      id INTEGER PRIMARY KEY, imei TEXT NOT NULL, claimant_ref TEXT NOT NULL,
      reason TEXT NOT NULL, evidence_note TEXT DEFAULT '',
      status TEXT DEFAULT 'OPEN', resolution TEXT DEFAULT '',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit_log(
      id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
      object_type TEXT NOT NULL, object_id TEXT, purpose TEXT DEFAULT '',
      details TEXT DEFAULT '', created_at TEXT NOT NULL,
      previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        demos = [
          ("admin","Regulator Administrator"),("analyst","Regulator Analyst"),
          ("operator","Operator Liaison"),("officer","Law Enforcement Officer"),
          ("supervisor","Law Enforcement Supervisor"),("auditor","Data Protection Auditor")]
        for username, role in demos:
            con.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                        (username, generate_password_hash("ChangeMe123!"), role, now()))
    if con.execute("SELECT COUNT(*) FROM tac_registry").fetchone()[0] == 0:
        con.executemany("INSERT INTO tac_registry(tac,brand,model,rat) VALUES(?,?,?,?)", [
          ("35678901","DemoMobile","D-Alpha","4G/5G"),
          ("49015420","ExampleTech","ET-One","4G"),
          ("86753090","Sample Devices","S-5G","5G")])
    if con.execute("SELECT COUNT(*) FROM eir_nodes").fetchone()[0] == 0:
        con.executemany("INSERT INTO eir_nodes(operator_name,region,health,last_sync) VALUES(?,?,?,?)", [
          ("Nepal Demo Telecom","Bagmati","ONLINE",now()),
          ("Himalayan Mobile Demo","Gandaki","ONLINE",now()),
          ("Terai Network Demo","Madhesh","DEGRADED",now())])
    if con.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 0:
        # Fictional, synthetically generated IMEIs with valid Luhn digits.
        samples = [make_imei("35678901","000001"), make_imei("49015420","000002"),
                   make_imei("86753090","000003")]
        for i, (imei, status, model, brand) in enumerate([
            (samples[0],"WHITELISTED","D-Alpha","DemoMobile"),
            (samples[1],"GREYLISTED","ET-One","ExampleTech"),
            (samples[2],"BLACKLISTED","S-5G","Sample Devices")]):
            con.execute("INSERT INTO devices(imei,tac,model,brand,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (imei,imei[:8],model,brand,status,now(),now()))
    con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('list_version','1')")
    con.commit()
    con.close()

def make_imei(tac, serial):
    first14 = tac + serial.zfill(6)
    total = 0
    for i, ch in enumerate(first14):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9: n -= 9
        total += n
    return first14 + str((10 - total % 10) % 10)

def validate_imei(value):
    value = (value or "").strip()
    if not re.fullmatch(r"\d{15}", value):
        return False, "IMEI must contain exactly 15 numeric digits."
    total = 0
    for i, ch in enumerate(value[:14]):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9: n -= 9
        total += n
    expected = (10 - total % 10) % 10
    if expected != int(value[-1]):
        return False, "IMEI failed the Luhn check-digit validation."
    return True, "Format and Luhn check passed."

def audit(actor, action, obj_type, obj_id="", purpose="", details=""):
    con = db()
    last = con.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = last["entry_hash"] if last else "GENESIS"
    created = now()
    payload = "|".join([prev, actor, action, obj_type, str(obj_id), purpose, details, created])
    digest = hashlib.sha256(payload.encode()).hexdigest()
    con.execute("""INSERT INTO audit_log(actor,action,object_type,object_id,purpose,details,created_at,previous_hash,entry_hash)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (actor,action,obj_type,str(obj_id),purpose,details,created,prev,digest))
    con.commit(); con.close()

def current_user():
    if "uid" not in session: return None
    con=db(); user=con.execute("SELECT * FROM users WHERE id=? AND active=1",(session["uid"],)).fetchone(); con.close()
    return user

def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user(): return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper

def permission(area):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u=current_user()
            if not u: return redirect(url_for("login"))
            if area not in ROLES.get(u["role"],set()): abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco

@app.context_processor
def inject():
    return {"user":current_user(), "roles":ROLES}

@app.route("/")
def index():
    if not current_user(): return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        con=db(); u=con.execute("SELECT * FROM users WHERE username=? AND active=1",(request.form.get("username","").strip(),)).fetchone(); con.close()
        if u and check_password_hash(u["password_hash"],request.form.get("password","")):
            session.clear(); session["uid"]=u["id"]
            audit(u["username"],"LOGIN","SESSION",u["id"],"Authentication","Successful demo login")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.","danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    u=current_user(); audit(u["username"],"LOGOUT","SESSION",u["id"])
    session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
@permission("dashboard")
def dashboard():
    con=db()
    stats={
      "devices":con.execute("SELECT COUNT(*) FROM devices").fetchone()[0],
      "white":con.execute("SELECT COUNT(*) FROM devices WHERE status='WHITELISTED'").fetchone()[0],
      "grey":con.execute("SELECT COUNT(*) FROM devices WHERE status='GREYLISTED'").fetchone()[0],
      "black":con.execute("SELECT COUNT(*) FROM devices WHERE status='BLACKLISTED'").fetchone()[0],
      "nodes":con.execute("SELECT COUNT(*) FROM eir_nodes").fetchone()[0],
      "alerts":con.execute("SELECT COUNT(*) FROM alerts WHERE status='OPEN'").fetchone()[0],
      "pending":con.execute("SELECT COUNT(*) FROM cases WHERE status='PENDING_APPROVAL'").fetchone()[0],
    }
    recent=con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 8").fetchall()
    nodes=con.execute("SELECT * FROM eir_nodes").fetchall()
    con.close()
    return render_template("dashboard.html",stats=stats,recent=recent,nodes=nodes)

@app.route("/devices")
@login_required
@permission("devices")
def devices():
    q=request.args.get("q","").strip(); status=request.args.get("status","")
    sql="SELECT * FROM devices WHERE 1=1"; args=[]
    if q: sql+=" AND (imei LIKE ? OR tac LIKE ? OR model LIKE ?)"; args += [f"%{q}%"]*3
    if status in ("WHITELISTED","GREYLISTED","BLACKLISTED"): sql+=" AND status=?"; args.append(status)
    sql+=" ORDER BY id DESC"
    con=db(); rows=con.execute(sql,args).fetchall(); con.close()
    return render_template("devices.html",devices=rows,q=q,status=status)

@app.route("/devices/add", methods=["GET","POST"])
@login_required
@permission("devices")
def device_add():
    if request.method=="POST":
        imei=request.form.get("imei","").strip()
        ok,msg=validate_imei(imei)
        if not ok: flash(msg,"danger")
        else:
            con=db(); tac=imei[:8]; tacrow=con.execute("SELECT * FROM tac_registry WHERE tac=? AND status='ACTIVE'",(tac,)).fetchone()
            if not tacrow:
                con.close(); flash("TAC not found in the local demo registry. No external GSMA lookup is performed.","warning")
            else:
                try:
                    con.execute("""INSERT INTO devices(imei,tac,model,brand,status,source,notes,created_at,updated_at)
                                   VALUES(?,?,?,?,?,?,?,?,?)""",
                                (imei,tac,tacrow["model"],tacrow["brand"],request.form.get("status","GREYLISTED"),
                                 "Manual demo entry",request.form.get("notes",""),now(),now()))
                    con.commit(); con.close()
                    audit(current_user()["username"],"DEVICE_CREATE","DEVICE",imei,"Device registration","Added to local prototype registry")
                    flash("Device added to CEIR demo registry.","success"); return redirect(url_for("devices"))
                except sqlite3.IntegrityError:
                    con.close(); flash("This IMEI already exists.","warning")
    return render_template("device_form.html")

@app.route("/devices/<int:device_id>")
@login_required
@permission("devices")
def device_detail(device_id):
    con=db(); d=con.execute("SELECT * FROM devices WHERE id=?",(device_id,)).fetchone()
    if not d: con.close(); abort(404)
    events=con.execute("SELECT * FROM attach_events WHERE imei=? ORDER BY event_time DESC LIMIT 20",(d["imei"],)).fetchall()
    overrides=con.execute("SELECT * FROM overrides WHERE imei=? ORDER BY id DESC",(d["imei"],)).fetchall()
    alerts=con.execute("SELECT * FROM alerts WHERE imei=? ORDER BY id DESC",(d["imei"],)).fetchall()
    con.close(); return render_template("device_detail.html",d=d,events=events,overrides=overrides,alerts=alerts)

@app.route("/devices/<int:device_id>/status",methods=["POST"])
@login_required
@permission("lists")
def device_status(device_id):
    status=request.form.get("status")
    if status not in ("WHITELISTED","GREYLISTED","BLACKLISTED"): abort(400)
    con=db(); d=con.execute("SELECT * FROM devices WHERE id=?",(device_id,)).fetchone()
    if not d: con.close(); abort(404)
    con.execute("UPDATE devices SET status=?,updated_at=? WHERE id=?",(status,now(),device_id))
    con.execute("UPDATE settings SET value=CAST(value AS INTEGER)+1 WHERE key='list_version'")
    con.commit(); con.close()
    audit(current_user()["username"],"LIST_STATUS_CHANGE","DEVICE",d["imei"],"Device list administration",f"{d['status']} -> {status}")
    flash(f"Device status changed to {status}. Simulate EIR sync from EIR Nodes.","success")
    return redirect(url_for("device_detail",device_id=device_id))

@app.route("/devices/<int:device_id>/override",methods=["POST"])
@login_required
@permission("lists")
def override_add(device_id):
    dcon=db(); d=dcon.execute("SELECT * FROM devices WHERE id=?",(device_id,)).fetchone()
    if not d: dcon.close(); abort(404)
    imsi=request.form.get("imsi","").strip(); reason=request.form.get("reason","").strip()
    if not re.fullmatch(r"\d{14,16}",imsi) or not reason:
        dcon.close(); flash("Enter a 14–16 digit demo IMSI and a reason.","danger")
        return redirect(url_for("device_detail",device_id=device_id))
    expiry=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(timespec="seconds")
    dcon.execute("INSERT INTO overrides(imei,imsi,reason,authorized_by,expires_at,created_at) VALUES(?,?,?,?,?,?)",
                 (d["imei"],imsi,reason,current_user()["username"],expiry,now()))
    dcon.commit(); dcon.close()
    audit(current_user()["username"],"BLO_CREATE","OVERRIDE",d["imei"],"Legitimate-pair exception",f"Pair ending {imsi[-4:]}; 30-day demo expiry")
    flash("Demo BLO exception created for 30 days.","success")
    return redirect(url_for("device_detail",device_id=device_id))

@app.route("/eir")
@login_required
@permission("eir")
def eir():
    con=db(); nodes=con.execute("SELECT * FROM eir_nodes ORDER BY id").fetchall()
    logs=con.execute("SELECT s.*,n.operator_name FROM sync_log s LEFT JOIN eir_nodes n ON n.id=s.node_id ORDER BY s.id DESC LIMIT 20").fetchall()
    version=con.execute("SELECT value FROM settings WHERE key='list_version'").fetchone()["value"]
    con.close(); return render_template("eir.html",nodes=nodes,logs=logs,version=version)

@app.route("/eir/<int:node_id>/sync",methods=["POST"])
@login_required
@permission("eir")
def eir_sync(node_id):
    con=db(); node=con.execute("SELECT * FROM eir_nodes WHERE id=?",(node_id,)).fetchone()
    if not node: con.close(); abort(404)
    if node["health"]=="OFFLINE":
        con.execute("INSERT INTO sync_log(node_id,action,result,list_version,created_at) VALUES(?,?,?,?,?)",
                    (node_id,"FULL_SYNC","QUEUED — node offline",0,now()))
        con.commit(); con.close(); flash("Node offline. Update queued for link recovery.","warning")
    else:
        version=int(con.execute("SELECT value FROM settings WHERE key='list_version'").fetchone()["value"])
        # Local simulation: no telecom network or external operator is contacted.
        con.execute("UPDATE eir_nodes SET last_sync=?,sync_lag_seconds=2,local_version=? WHERE id=?",(now(),version,node_id))
        con.execute("INSERT INTO sync_log(node_id,action,result,list_version,created_at) VALUES(?,?,?,?,?)",
                    (node_id,"FULL_SYNC","ACKNOWLEDGED (SIMULATED)",version,now()))
        con.commit(); con.close(); flash("Simulated EIR synchronization acknowledged.","success")
    audit(current_user()["username"],"EIR_SYNC_SIMULATED","EIR_NODE",node_id,"Synchronization test","Local-only simulated synchronization")
    return redirect(url_for("eir"))

@app.route("/eir/<int:node_id>/health",methods=["POST"])
@login_required
@permission("eir")
def eir_health(node_id):
    health=request.form.get("health")
    if health not in ("ONLINE","DEGRADED","OFFLINE"): abort(400)
    con=db(); con.execute("UPDATE eir_nodes SET health=? WHERE id=?",(health,node_id)); con.commit(); con.close()
    audit(current_user()["username"],"EIR_HEALTH_CHANGE","EIR_NODE",node_id,"Demo operations",health)
    return redirect(url_for("eir"))

@app.route("/events",methods=["GET","POST"])
@login_required
@permission("events")
def events():
    con=db()
    if request.method=="POST":
        imei=request.form.get("imei","").strip(); imsi=request.form.get("imsi","").strip()
        cell=request.form.get("cell_id","").strip(); lat=request.form.get("lat",""); lon=request.form.get("lon","")
        try: lat=float(lat); lon=float(lon)
        except: lat=999; lon=999
        ok,_=validate_imei(imei)
        if not ok or not re.fullmatch(r"\d{14,16}",imsi) or not cell or not (-90<=lat<=90 and -180<=lon<=180):
            flash("Enter a valid demo IMEI, 14–16 digit synthetic IMSI, cell ID and valid coordinates.","danger")
        else:
            con.execute("INSERT INTO attach_events(imei,imsi,cell_id,lat,lon,rat,event_time) VALUES(?,?,?,?,?,?,?)",
                        (imei,imsi,cell,lat,lon,request.form.get("rat","4G"),request.form.get("event_time") or now()))
            con.commit(); audit(current_user()["username"],"SYNTHETIC_ATTACH_EVENT","ATTACH_EVENT",imei,"Clone detection demonstration","Synthetic event inserted")
            flash("Synthetic network event added.","success")
    rows=con.execute("SELECT * FROM attach_events ORDER BY id DESC LIMIT 100").fetchall()
    alerts=con.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 30").fetchall()
    con.close(); return render_template("events.html",events=rows,alerts=alerts)

def haversine_km(lat1,lon1,lat2,lon2):
    r=6371.0
    dlat=radians(lat2-lat1); dlon=radians(lon2-lon1)
    a=sin(dlat/2)**2+cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2*r*atan2(sqrt(a),sqrt(1-a))

@app.route("/events/analyze",methods=["POST"])
@login_required
@permission("events")
def analyze_events():
    con=db(); groups=con.execute("SELECT * FROM attach_events ORDER BY imei,event_time").fetchall()
    by={}
    for e in groups: by.setdefault(e["imei"],[]).append(e)
    created=0
    for imei, arr in by.items():
        for a,b in zip(arr,arr[1:]):
            try:
                t1=datetime.fromisoformat(a["event_time"].replace("Z","+00:00"))
                t2=datetime.fromisoformat(b["event_time"].replace("Z","+00:00"))
                hours=abs((t2-t1).total_seconds())/3600
            except: continue
            distance=haversine_km(a["lat"],a["lon"],b["lat"],b["lon"])
            # Deliberately conservative synthetic threshold; alert only, never auto-block.
            if a["imsi"]!=b["imsi"] and hours>0 and distance/(hours) > 500:
                desc=f"Different synthetic IMSIs observed {distance:.1f} km apart in {hours:.2f} h; review required. Alert only."
                exists=con.execute("SELECT id FROM alerts WHERE imei=? AND description=?",(imei,desc)).fetchone()
                if not exists:
                    con.execute("INSERT INTO alerts(imei,severity,alert_type,description,created_at) VALUES(?,?,?,?,?)",
                                (imei,"HIGH","TIME_DISTANCE_CONFLICT",desc,now())); created+=1
                    con.execute("UPDATE devices SET status='GREYLISTED',updated_at=? WHERE imei=? AND status!='BLACKLISTED'",(now(),imei))
    con.commit(); con.close()
    audit(current_user()["username"],"CLONE_ANALYSIS_RUN","ANALYTICS","", "Synthetic anomaly detection",f"{created} new alert(s); no automatic blacklist")
    flash(f"Analysis complete: {created} new alert(s). Alerts require human review; no automatic blacklisting.","info")
    return redirect(url_for("events"))

@app.route("/cases",methods=["GET","POST"])
@login_required
@permission("cases")
def cases():
    con=db()
    if request.method=="POST":
        u=current_user()
        imei=request.form.get("imei","").strip(); warrant=request.form.get("warrant_id","").strip()
        court=request.form.get("court","").strip(); purpose=request.form.get("purpose","").strip()
        valid,_=validate_imei(imei)
        if not valid or not warrant or not court or not purpose:
            flash("Valid IMEI, warrant ID, issuing court and purpose are required.","danger")
        else:
            ref="CASE-"+datetime.now().strftime("%Y%m%d%H%M%S")
            con.execute("""INSERT INTO cases(case_ref,imei,warrant_id,issuing_court,purpose,requested_by,created_at)
                           VALUES(?,?,?,?,?,?,?)""",(ref,imei,warrant,court,purpose,u["username"],now()))
            con.commit(); audit(u["username"],"WARRANT_CASE_SUBMITTED","CASE",ref,"Warrant-gated workflow","Pending independent supervisor approval")
            flash("Case submitted for supervisor approval. No live location query is performed.","success")
    rows=con.execute("SELECT * FROM cases ORDER BY id DESC").fetchall(); con.close()
    return render_template("cases.html",cases=rows)

@app.route("/cases/<int:case_id>/decision",methods=["POST"])
@login_required
@permission("cases")
def case_decision(case_id):
    u=current_user()
    if u["role"]!="Law Enforcement Supervisor": abort(403)
    decision=request.form.get("decision"); note=request.form.get("note","").strip()
    if decision not in ("APPROVED","REJECTED"): abort(400)
    con=db(); c=con.execute("SELECT * FROM cases WHERE id=?",(case_id,)).fetchone()
    if not c: con.close(); abort(404)
    if c["status"]!="PENDING_APPROVAL": con.close(); flash("Case already decided.","warning"); return redirect(url_for("cases"))
    con.execute("UPDATE cases SET status=?,supervisor=?,decision_note=?,decided_at=? WHERE id=?",
                (decision,u["username"],note,now(),case_id)); con.commit(); con.close()
    audit(u["username"],"CASE_"+decision,"CASE",c["case_ref"],"Second-level authorization",note)
    flash(f"Case {decision.lower()}. This demo does not retrieve device location.","success")
    return redirect(url_for("cases"))

@app.route("/disputes",methods=["GET","POST"])
@login_required
@permission("disputes")
def disputes():
    con=db()
    if request.method=="POST":
        imei=request.form.get("imei","").strip(); claimant=request.form.get("claimant_ref","").strip()
        reason=request.form.get("reason","").strip()
        ok,_=validate_imei(imei)
        if not ok or not claimant or not reason: flash("Valid IMEI, claimant reference and reason are required.","danger")
        else:
            con.execute("INSERT INTO disputes(imei,claimant_ref,reason,evidence_note,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                        (imei,claimant,reason,request.form.get("evidence_note",""),now(),now()))
            con.commit(); audit(current_user()["username"],"DISPUTE_CREATE","DISPUTE",imei,"Device dispute","Complaint registered")
            flash("Dispute registered.","success")
    rows=con.execute("SELECT * FROM disputes ORDER BY id DESC").fetchall(); con.close()
    return render_template("disputes.html",disputes=rows)

@app.route("/disputes/<int:dispute_id>/resolve",methods=["POST"])
@login_required
@permission("disputes")
def dispute_resolve(dispute_id):
    status=request.form.get("status")
    if status not in ("UNDER_REVIEW","RESOLVED","REJECTED"): abort(400)
    note=request.form.get("resolution","").strip()
    con=db(); d=con.execute("SELECT * FROM disputes WHERE id=?",(dispute_id,)).fetchone()
    if not d: con.close(); abort(404)
    con.execute("UPDATE disputes SET status=?,resolution=?,updated_at=? WHERE id=?",(status,note,now(),dispute_id))
    con.commit(); con.close(); audit(current_user()["username"],"DISPUTE_UPDATE","DISPUTE",dispute_id,"Dispute resolution",status+" "+note)
    return redirect(url_for("disputes"))

@app.route("/audit")
@login_required
@permission("audit")
def audit_view():
    con=db(); rows=con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 250").fetchall()
    # Verify chain in ascending order.
    allrows=con.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    prev="GENESIS"; valid=True
    for r in allrows:
        payload="|".join([prev,r["actor"],r["action"],r["object_type"],str(r["object_id"] or ""),r["purpose"] or "",r["details"] or "",r["created_at"]])
        expected=hashlib.sha256(payload.encode()).hexdigest()
        if r["previous_hash"]!=prev or r["entry_hash"]!=expected: valid=False; break
        prev=r["entry_hash"]
    con.close(); return render_template("audit.html",rows=rows,chain_valid=valid)

@app.route("/reports")
@login_required
@permission("reports")
def reports():
    con=db()
    counts=con.execute("SELECT status,COUNT(*) AS n FROM devices GROUP BY status").fetchall()
    alert_counts=con.execute("SELECT alert_type,COUNT(*) AS n FROM alerts GROUP BY alert_type").fetchall()
    con.close(); return render_template("reports.html",counts=counts,alert_counts=alert_counts)

@app.route("/reports/devices.csv")
@login_required
@permission("reports")
def export_devices():
    con=db(); rows=con.execute("SELECT imei,tac,brand,model,status,source,created_at,updated_at FROM devices ORDER BY id").fetchall(); con.close()
    out=io.StringIO(); w=csv.writer(out); w.writerow(["IMEI","TAC","Brand","Model","Status","Source","Created","Updated"])
    for r in rows: w.writerow(list(r))
    audit(current_user()["username"],"REPORT_EXPORT","REPORT","devices.csv","Operational reporting","Device inventory CSV exported")
    return Response(out.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=ceir_device_inventory.csv"})

@app.errorhandler(403)
def forbidden(e): return render_template("error.html",code=403,message="Your role is not authorized for this module."),403
@app.errorhandler(404)
def missing(e): return render_template("error.html",code=404,message="The requested record or page was not found."),404

if __name__=="__main__":
    init_db()
    app.run(host="127.0.0.1",port=int(os.environ.get("PORT",5000)),debug=os.environ.get("FLASK_DEBUG")=="1")
