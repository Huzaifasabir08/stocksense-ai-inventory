import json, os, re, secrets, sqlite3
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
DB = ROOT / "stocksense.db"
STATIC = ROOT / "static"
SESSIONS = {}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    c=db(); c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,password TEXT,role TEXT,name TEXT);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE,name TEXT,category TEXT,section TEXT,description TEXT,selling_price REAL,cost_price REAL,min_stock INTEGER,current_stock INTEGER,supplier TEXT,location TEXT,status TEXT DEFAULT 'active',created_at TEXT,updated_at TEXT);
    CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,product_id INTEGER,type TEXT,quantity INTEGER,previous_stock INTEGER,new_stock INTEGER,user_id INTEGER,supplier TEXT,reason TEXT,status TEXT,created_at TEXT,proposal_key TEXT UNIQUE,FOREIGN KEY(product_id) REFERENCES products(id));
    CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,product_id INTEGER,type TEXT,quantity INTEGER,supplier TEXT,reason TEXT,user_id INTEGER,status TEXT,created_at TEXT,FOREIGN KEY(product_id) REFERENCES products(id));
    CREATE INDEX IF NOT EXISTS idx_movements_product_date ON movements(product_id,created_at);
    """)
    if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        c.executemany("INSERT INTO users(email,password,role,name) VALUES(?,?,?,?)",[("manager@stocksense.local","manager123","manager","Amina Khan"),("staff@stocksense.local","staff123","staff","Bilal Shah")])
    if not c.execute("SELECT 1 FROM products LIMIT 1").fetchone():
        now=datetime.now().isoformat(); products=[
          ("EL-CAB-001","Type-C Cable","Accessories","Electronics","Fast charging USB-C cable",899,430,20,15,"Ali Traders","E-A12"),
          ("EL-TV-042","Samsung 55-inch TV","Television","Electronics","4K smart television",189999,157000,4,9,"Tech World","E-B02"),
          ("GR-RIC-025","Basmati Rice 5kg","Staples","Grocery","Premium basmati rice",1890,1520,15,46,"Frontier Foods","G-C08"),
          ("CL-TSH-110","Cotton T-Shirt","Menswear","Clothing","Classic cotton t-shirt",1599,850,10,8,"Style House","C-A04"),
          ("HH-DET-022","Laundry Detergent","Cleaning","Household","2kg detergent pack",1240,930,12,0,"CleanCo","H-D10")]
        for p in products: c.execute("INSERT INTO products(sku,name,category,section,description,selling_price,cost_price,min_stock,current_stock,supplier,location,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(*p,now,now))
        user=1
        for pid,qty in [(1,20),(2,32),(3,14),(4,5)]:
            stock=c.execute("SELECT current_stock FROM products WHERE id=?",(pid,)).fetchone()[0]
            c.execute("INSERT INTO movements(product_id,type,quantity,previous_stock,new_stock,user_id,supplier,reason,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(pid,"sale",qty,stock+qty,stock,user,None,"Demo weekly sale","completed",(datetime.now()-timedelta(days=2)).isoformat()))
    c.commit(); c.close()

def user_from(req):
    token=req.headers.get("Authorization","").replace("Bearer ","")
    return SESSIONS.get(token)

def require(data, fields):
    missing=[f for f in fields if data.get(f) in (None,"")]
    if missing: raise ValueError("Missing required fields: "+", ".join(missing)+".")

def manager_only(user):
    if user["role"]!="manager": raise PermissionError("Manager permission is required.")

def product_json(row, role):
    d=dict(row); d["stock_status"]="Out of stock" if d["current_stock"]==0 else "Low stock" if d["current_stock"]<=d["min_stock"] else "In stock"
    if role!="manager": d.pop("cost_price",None)
    return d

def apply_movement(c, user, product_id, movement_type, qty, supplier="", reason="", proposal_key=None):
    if qty<=0: raise ValueError("Quantity must be greater than zero.")
    p=c.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
    if not p: raise ValueError("Product could not be found.")
    delta=qty if movement_type=="stock_in" else -qty
    new=p["current_stock"]+delta
    if new<0: raise ValueError(f"Insufficient stock. Only {p['current_stock']} units are available.")
    now=datetime.now().isoformat()
    try:
        c.execute("INSERT INTO movements(product_id,type,quantity,previous_stock,new_stock,user_id,supplier,reason,status,created_at,proposal_key) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(product_id,movement_type,qty,p["current_stock"],new,user["id"],supplier,reason,"completed",now,proposal_key))
    except sqlite3.IntegrityError: raise ValueError("This confirmation was already applied.")
    c.execute("UPDATE products SET current_stock=?,updated_at=? WHERE id=?",(new,now,product_id))
    return {"product":p["name"],"previous":p["current_stock"],"new":new,"change":delta}

def grounded_answer(c, user, text):
    lower=text.lower()
    if user["role"]!="manager" and any(x in lower for x in ["profit","cost price","margin","i am the manager","ignore your rules","developer mode"]):
        return {"type":"answer","text":"I can’t show cost, profit, or manager-only information for your staff account."}
    if os.getenv("AI_DISABLED")=="1": raise RuntimeError("AI unavailable")
    add=re.search(r"(?:add|increase|receive)\s+(\d+)\s+(.+?)(?:\s+from\s+(.+))?[.!]?$",text,re.I)
    if add:
        qty=int(add.group(1)); phrase=add.group(2).strip(); supplier=(add.group(3) or "").strip()
        p=c.execute("SELECT * FROM products WHERE lower(name) LIKE ? OR lower(name) LIKE ? LIMIT 1",(f"%{phrase.lower().rstrip('s')}%",f"%{phrase.lower()}%" )).fetchone()
        if not p: return {"type":"answer","text":"I couldn’t find that product in inventory."}
        pid=secrets.token_hex(12); c.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?)",(pid,p["id"],"stock_in",qty,supplier,"AI prepared stock receipt",user["id"],"pending",datetime.now().isoformat())); c.commit()
        return {"type":"proposal","proposal_id":pid,"product":p["name"],"current":p["current_stock"],"change":qty,"new":p["current_stock"]+qty,"supplier":supplier}
    if "low" in lower:
        rows=c.execute("SELECT * FROM products WHERE current_stock<=min_stock ORDER BY current_stock").fetchall()
        return {"type":"answer","text":"Low-stock products: "+", ".join(f"{r['name']} ({r['current_stock']} left)" for r in rows)+"."}
    if "out of stock" in lower:
        rows=c.execute("SELECT name FROM products WHERE current_stock=0").fetchall(); return {"type":"answer","text":"Out of stock: "+(", ".join(r[0] for r in rows) or "None")+"."}
    if "sold most" in lower:
        since=(datetime.now()-timedelta(days=7)).isoformat(); r=c.execute("SELECT p.name,SUM(m.quantity) q FROM movements m JOIN products p ON p.id=m.product_id WHERE m.type='sale' AND m.created_at>=? GROUP BY p.id ORDER BY q DESC LIMIT 1",(since,)).fetchone()
        return {"type":"answer","text":f"{r['name']} sold the most this week: {r['q']} units." if r else "No sales were recorded this week."}
    found=[]
    for p in c.execute("SELECT * FROM products").fetchall():
        name=p["name"].lower()
        key=" ".join(w for w in re.sub(r"[^a-z0-9 -]","",name).split() if not w.replace("-","").isdigit())
        if name in lower or key in lower: found.append(f"{p['name']}: {p['current_stock']} units")
    if found: return {"type":"answer","text":"Current stock — "+"; ".join(found)+"."}
    return {"type":"answer","text":"I couldn’t find a matching product or report. Try the exact product name."}

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self): self.send_header("Cache-Control","no-store"); super().end_headers()
    def json(self,status,data):
        body=json.dumps(data).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}")
        except: return {}
    def do_GET(self):
        path=urlparse(self.path).path
        if path == "/healthz":
            return self.json(200, {"service": "stocksense", "project": str(ROOT), "pid": os.getpid()})
        if path.startswith("/api/"):
            u=user_from(self)
            if not u: return self.json(401,{"error":"Please sign in."})
            c=db()
            try:
                if path=="/api/me": return self.json(200,{"user":u})
                if path=="/api/products": return self.json(200,[product_json(r,u["role"]) for r in c.execute("SELECT * FROM products ORDER BY name")])
                if path.startswith("/api/products/"):
                    try: product_id=int(path.split("/")[-1])
                    except ValueError: return self.json(400,{"error":"Product ID must be a number."})
                    row=c.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
                    return self.json(200,product_json(row,u["role"])) if row else self.json(404,{"error":"Product could not be found."})
                if path=="/api/dashboard":
                    products=c.execute("SELECT * FROM products").fetchall(); total=sum(p["current_stock"] for p in products); low=sum(p["current_stock"]<=p["min_stock"] and p["current_stock"]>0 for p in products); out=sum(p["current_stock"]==0 for p in products)
                    recent=[dict(r) for r in c.execute("SELECT m.*,p.name product,u.name user FROM movements m JOIN products p ON p.id=m.product_id JOIN users u ON u.id=m.user_id ORDER BY m.id DESC LIMIT 8")]
                    return self.json(200,{"products":len(products),"units":total,"low":low,"out":out,"pending":c.execute("SELECT COUNT(*) FROM proposals WHERE status='pending'").fetchone()[0],"recent":recent,"user":u})
                if path=="/api/history": return self.json(200,[dict(r) for r in c.execute("SELECT m.*,p.name product,u.name user FROM movements m JOIN products p ON p.id=m.product_id JOIN users u ON u.id=m.user_id ORDER BY m.id DESC")])
                if path=="/api/proposals":
                    sql="SELECT q.*,p.name product,u.name user FROM proposals q JOIN products p ON p.id=q.product_id JOIN users u ON u.id=q.user_id"
                    args=() if u["role"]=="manager" else (u["id"],)
                    if u["role"]!="manager": sql+=" WHERE q.user_id=?"
                    return self.json(200,[dict(r) for r in c.execute(sql+" ORDER BY q.created_at DESC",args)])
                if path=="/api/reports":
                    manager_only(u); since=(datetime.now()-timedelta(days=7)).isoformat()
                    sales=[dict(r) for r in c.execute("SELECT p.name,SUM(m.quantity) units,SUM(m.quantity*p.selling_price) revenue,SUM(m.quantity*(p.selling_price-p.cost_price)) profit FROM movements m JOIN products p ON p.id=m.product_id WHERE m.type='sale' AND m.created_at>=? GROUP BY p.id ORDER BY units DESC",(since,))]
                    categories=[dict(r) for r in c.execute("SELECT section,SUM(current_stock) units,COUNT(*) products FROM products GROUP BY section ORDER BY section")]
                    return self.json(200,{"period":"last_7_days","sales":sales,"categories":categories})
                if path=="/api/users":
                    manager_only(u); return self.json(200,[dict(r) for r in c.execute("SELECT id,email,role,name FROM users ORDER BY name")])
                return self.json(404,{"error":"Not found"})
            except PermissionError as e: return self.json(403,{"error":str(e)})
            finally: c.close()
        self.path="/index.html" if path=="/" else path; return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path; data=self.body()
        if path=="/api/login":
            try: require(data,["email","password"])
            except ValueError as e: return self.json(400,{"error":str(e)})
            c=db(); row=c.execute("SELECT id,email,role,name FROM users WHERE email=? AND password=?",(data.get("email"),data.get("password"))).fetchone(); c.close()
            if not row:return self.json(401,{"error":"Incorrect email or password."})
            token=secrets.token_hex(24); SESSIONS[token]=dict(row); return self.json(200,{"token":token,"user":dict(row)})
        u=user_from(self)
        if not u:return self.json(401,{"error":"Please sign in."})
        c=db()
        try:
            if path=="/api/logout":
                token=self.headers.get("Authorization","").replace("Bearer ",""); SESSIONS.pop(token,None); return self.json(200,{"status":"signed_out"})
            if path=="/api/products":
                try:
                    manager_only(u); require(data,["sku","name","category","section","selling_price","cost_price","min_stock","supplier","location"])
                    if data["section"] not in ["Grocery","Clothing","Electronics","Household"]: raise ValueError("Section must be Grocery, Clothing, Electronics, or Household.")
                    now=datetime.now().isoformat(); values=(str(data["sku"]).strip(),str(data["name"]).strip(),str(data["category"]).strip(),data["section"],str(data.get("description","")),float(data["selling_price"]),float(data["cost_price"]),int(data["min_stock"]),0,str(data["supplier"]),str(data["location"]),now,now)
                    if values[5]<0 or values[6]<0 or values[7]<0: raise ValueError("Prices and minimum stock cannot be negative.")
                    cur=c.execute("INSERT INTO products(sku,name,category,section,description,selling_price,cost_price,min_stock,current_stock,supplier,location,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",values); c.commit(); return self.json(201,product_json(c.execute("SELECT * FROM products WHERE id=?",(cur.lastrowid,)).fetchone(),u["role"]))
                except PermissionError as e:return self.json(403,{"error":str(e)})
                except sqlite3.IntegrityError:return self.json(409,{"error":"A product with this SKU already exists."})
                except (ValueError,TypeError) as e:return self.json(400,{"error":str(e)})
            if path=="/api/movements":
                try:
                    require(data,["product_id","type","quantity"])
                    if data["type"] not in ["stock_in","sale","damaged","adjustment"]: raise ValueError("Movement type must be stock_in, sale, damaged, or adjustment.")
                    operation_key=self.headers.get("Idempotency-Key")
                    if operation_key and c.execute("SELECT 1 FROM movements WHERE proposal_key=?",("api:"+operation_key,)).fetchone(): return self.json(409,{"error":"This stock operation was already applied."})
                    result=apply_movement(c,u,int(data["product_id"]),data["type"],int(data["quantity"]),data.get("supplier",""),data.get("reason",""),"api:"+operation_key if operation_key else None); c.commit(); return self.json(201,result)
                except ValueError as e: c.rollback(); return self.json(400,{"error":str(e)})
            if path=="/api/chat":
                try:
                    require(data,["message"]); return self.json(200,grounded_answer(c,u,str(data["message"])))
                except ValueError as e:return self.json(400,{"error":str(e)})
                except RuntimeError:return self.json(503,{"error":"AI Assistant is currently unavailable. You can continue using the inventory system normally."})
            if path.startswith("/api/proposals/"):
                pid=path.split("/")[-1]; p=c.execute("SELECT * FROM proposals WHERE id=?",(pid,)).fetchone()
                if not p:return self.json(404,{"error":"Proposal not found."})
                if p["user_id"]!=u["id"]:return self.json(403,{"error":"You are not allowed to confirm this proposal."})
                action=data.get("action")
                if action not in ["confirm","cancel"]: return self.json(400,{"error":"Action must be confirm or cancel."})
                if action=="cancel": c.execute("UPDATE proposals SET status='cancelled' WHERE id=? AND status='pending'",(pid,)); c.commit(); return self.json(200,{"status":"cancelled"})
                if p["status"]!="pending": return self.json(409,{"error":"This proposal is no longer pending."})
                try: result=apply_movement(c,u,p["product_id"],p["type"],p["quantity"],p["supplier"],p["reason"],pid); c.execute("UPDATE proposals SET status='confirmed' WHERE id=?",(pid,)); c.commit(); return self.json(200,result)
                except ValueError as e: c.rollback(); return self.json(400,{"error":str(e)})
            if path=="/api/prices":
                if u["role"]!="manager": return self.json(403,{"error":"Manager permission is required."})
                try:
                    require(data,["product_id","selling_price"]); product_id=int(data["product_id"]); price=float(data["selling_price"])
                    if price<0: raise ValueError("Selling price cannot be negative.")
                    cur=c.execute("UPDATE products SET selling_price=?,updated_at=? WHERE id=?",(price,datetime.now().isoformat(),product_id))
                    if not cur.rowcount:return self.json(404,{"error":"Product could not be found."})
                    c.commit(); return self.json(200,{"status":"updated","product_id":product_id,"selling_price":price})
                except (ValueError,TypeError) as e:return self.json(400,{"error":str(e)})
            if path=="/api/users":
                try:
                    manager_only(u); require(data,["email","password","role","name"])
                    if data["role"] not in ["staff","manager"]: raise ValueError("Role must be staff or manager.")
                    if len(str(data["password"]))<8: raise ValueError("Password must contain at least 8 characters.")
                    cur=c.execute("INSERT INTO users(email,password,role,name) VALUES(?,?,?,?)",(str(data["email"]).lower(),str(data["password"]),data["role"],str(data["name"]))); c.commit(); return self.json(201,{"id":cur.lastrowid,"email":str(data["email"]).lower(),"role":data["role"],"name":data["name"]})
                except PermissionError as e:return self.json(403,{"error":str(e)})
                except sqlite3.IntegrityError:return self.json(409,{"error":"A user with this email already exists."})
                except ValueError as e:return self.json(400,{"error":str(e)})
            return self.json(404,{"error":"Not found"})
        finally:c.close()

    def do_PATCH(self):
        path=urlparse(self.path).path; data=self.body(); u=user_from(self)
        if not u:return self.json(401,{"error":"Please sign in."})
        if not path.startswith("/api/products/"):return self.json(404,{"error":"Not found"})
        if u["role"]!="manager":return self.json(403,{"error":"Manager permission is required."})
        try: product_id=int(path.split("/")[-1])
        except ValueError:return self.json(400,{"error":"Product ID must be a number."})
        allowed={"name","category","section","description","selling_price","cost_price","min_stock","supplier","location","status"}; updates={k:v for k,v in data.items() if k in allowed}
        if not updates:return self.json(400,{"error":"No supported product fields were provided."})
        if "section" in updates and updates["section"] not in ["Grocery","Clothing","Electronics","Household"]:return self.json(400,{"error":"Invalid section."})
        try:
            for k in ["selling_price","cost_price","min_stock"]:
                if k in updates and float(updates[k])<0:return self.json(400,{"error":f"{k} cannot be negative."})
            c=db(); fields=list(updates); values=[updates[k] for k in fields]+[datetime.now().isoformat(),product_id]; cur=c.execute("UPDATE products SET "+",".join(f"{k}=?" for k in fields)+",updated_at=? WHERE id=?",values); c.commit()
            if not cur.rowcount:c.close();return self.json(404,{"error":"Product could not be found."})
            row=c.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone(); result=product_json(row,u["role"]); c.close(); return self.json(200,result)
        except (ValueError,TypeError) as e:return self.json(400,{"error":str(e)})

if __name__=="__main__":
    port = int(os.environ.get("STOCKSENSE_PORT", "8765"))
    if not (STATIC / "index.html").is_file():
        raise SystemExit(f"Missing website files: {STATIC}")
    # Bind before touching the database: a conflicting port must fail cleanly.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        init_db()
        os.chdir(STATIC)
        print(f"StockSense running at http://127.0.0.1:{port}", flush=True)
        server.serve_forever()
    finally:
        server.server_close()
