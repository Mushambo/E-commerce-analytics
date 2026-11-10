"""
make_architecture_diagram.py - draws the system architecture from ONE definition and writes
  report/figures/fig0_architecture.svg / .png   (for the report)
  report/architecture.drawio                    (editable in draw.io / diagrams.net)
    python report/make_architecture_diagram.py
"""
import html
import pathlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
W, H = 1620, 900

C = {  # stroke, fill
    "gen": ("#6b6a66", "#f4f4f2"), "mongo": ("#1f8a4c", "#eaf6ee"), "hbase": ("#b8322b", "#fbecea"),
    "lake": ("#6b6a66", "#f4f4f2"), "spark": ("#d9601a", "#fdf1e8"), "step": ("#d9601a", "#ffffff"),
    "int": ("#2a78d6", "#ffffff"), "out": ("#2a78d6", "#eef4fc"), "docker": ("#1d63ed", "#f2f6fe"),
    "chip": ("#1d63ed", "#ffffff"),
}

# id: (x, y, w, h, kind, title, [lines])
N = {
    "gen": (30, 230, 220, 330, "gen", "1. Data generation",
            ["dataset_generator.py", "(seeded, streamed, --scale)", "", "users.json", "products.json",
             "categories.json", "transactions.json", "sessions_0..N.json"]),
    "mongo": (380, 80, 390, 270, "mongo", "MongoDB  ·  document store",
              ["categories  - subcategories embedded", "products  - extended ref + price_history",
               "transactions  - line items embedded", "users  - computed purchase_summary",
               "sessions  - sample of full journeys", "", "Indexes: user_id+timestamp, timestamp,",
               "items.product_id, total_spent"]),
    "hbase": (380, 380, 390, 200, "hbase", "HBase  ·  wide-column store",
              ["user_sessions", "key: user_id | reverse_ts | session_id", "CF: info · pv · cart",
               "", "product_metrics", "key: product_id | yyyymmdd   CF: m"]),
    "lake": (380, 610, 390, 100, "lake", "Parquet data lake  (data/clean)",
             ["9 clean tables, Snappy, partitioned by date"]),
    "spark": (860, 80, 420, 630, "spark", "Apache Spark  (PySpark)", []),
    "s01": (885, 125, 370, 62, "step", "01  clean & normalise", ["explicit schemas · dedupe · repair · flag"]),
    "s02": (885, 200, 370, 50, "step", "02  recommendations", ["bought / viewed together, lift"]),
    "s03": (885, 263, 370, 50, "step", "03  cohort analysis", ["registration-month retention"]),
    "s04": (885, 326, 370, 50, "step", "04  Spark SQL", ["windows, ROLLUP, Mongo/HBase-shaped joins"]),
    "src": (885, 410, 370, 70, "int", "integration/sources.py", ["same DataFrame from files | mongo | hbase"]),
    "clv": (885, 505, 180, 180, "int", "CLV + RFM", ["clv_analysis.py", "", "users + orders", "(MongoDB)", "+ engagement", "(HBase)"]),
    "fun": (1075, 505, 180, 180, "int", "Funnel", ["funnel_analysis.py", "", "journeys + metrics", "(HBase)", "+ purchases", "(MongoDB)"]),
    "out": (1370, 260, 220, 270, "out", "4. Insights",
            ["output/*.csv", "results tables", "", "report/figures", "7 static charts", "",
             "Technical report", "(Word / PDF)"]),
    "docker": (40, 760, 1550, 115, "docker", "Docker Desktop  ·  docker compose up -d --build", []),
    "d1": (330, 805, 300, 52, "chip", "mongo", ["MongoDB 7  ·  :27017"]),
    "d2": (660, 805, 300, 52, "chip", "hbase", ["HBase + Thrift  ·  :9090  UI :16010"]),
    "d3": (990, 805, 300, 52, "chip", "app", ["Python 3.11 + Java 17 + PySpark  ·  :4040"]),
}

# edges: (points, label, label_xy)
E = [
    ([(250, 300), (315, 300), (315, 215), (380, 215)], "load_mongodb.py", (315, 258)),
    ([(250, 480), (380, 480)], "load_hbase.py", (315, 480)),
    ([(140, 230), (140, 50), (1070, 50), (1070, 125)], "raw JSON  (sessions_*.json glob)", (620, 50)),
    ([(770, 300), (845, 300), (845, 430), (885, 430)], "pymongo", (807, 300)),
    ([(770, 470), (885, 470)], "happybase", (815, 470)),
    ([(770, 660), (885, 660)], "write / read", (827, 660)),
    ([(1070, 480), (1070, 505)], None, None),
    ([(1280, 395), (1370, 395)], "CSV + PNG", (1325, 395)),
]

# ------------------------------------------------------------------ SVG
def svg():
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'font-family="Segoe UI, DejaVu Sans, Arial, sans-serif">',
         '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0,0 L10,5 L0,10 z" fill="#52514e"/></marker>'
         '<marker id="b" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M10,0 L0,5 L10,10 z" fill="#52514e"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="40" y="30" font-size="20" font-weight="700" fill="#1b1b1a">System architecture - '
         f'distributed multi-model e-commerce analytics</text>']
    for k in ["docker", "spark", "gen", "mongo", "hbase", "lake", "s01", "s02", "s03", "s04", "src", "clv", "fun",
              "out", "d1", "d2", "d3"]:
        x, y, w, h, kind, title, lines = N[k]
        stroke, fill = C[kind]
        dash = ' stroke-dasharray="6 4"' if kind in ("docker",) else ""
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>')
        big = kind in ("gen", "mongo", "hbase", "lake", "spark", "out", "docker")
        if big:
            o.append(f'<rect x="{x}" y="{y}" width="{w}" height="34" rx="10" fill="{stroke}"/>'
                     f'<rect x="{x}" y="{y + 20}" width="{w}" height="14" fill="{stroke}"/>')
            o.append(f'<text x="{x + 14}" y="{y + 23}" font-size="15" font-weight="700" fill="#ffffff">{html.escape(title)}</text>')
            ty, size, anchor, tx = y + 58, 13.5, "start", x + 16
        else:
            center = kind in ("chip", "int") and w < 250
            anchor, tx = ("middle", x + w / 2) if center else ("start", x + 14)
            o.append(f'<text x="{tx}" y="{y + 22}" font-size="14.5" font-weight="700" fill="{stroke}" text-anchor="{anchor}">{html.escape(title)}</text>')
            ty, size = y + 42, 12.5
        for ln in lines:
            if ln:
                bold = ' font-weight="600"' if (big and ln in ("user_sessions", "product_metrics")) else ""
                o.append(f'<text x="{tx}" y="{ty}" font-size="{size}" fill="#2f2e2b" text-anchor="{anchor}"{bold}>{html.escape(ln)}</text>')
            ty += 19 if big else 17
    for pts, label, lxy in E:
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        both = ' marker-start="url(#b)"' if label == "write / read" else ""
        o.append(f'<path d="{d}" fill="none" stroke="#52514e" stroke-width="2" marker-end="url(#a)"{both}/>')
        if label:
            lx, ly = lxy
            wlab = 7.0 * len(label) + 14
            o.append(f'<rect x="{lx - wlab / 2}" y="{ly - 11}" width="{wlab}" height="22" rx="11" fill="#ffffff" stroke="#d6d5d0"/>')
            o.append(f'<text x="{lx}" y="{ly + 4.5}" font-size="12" fill="#1b1b1a" text-anchor="middle">{html.escape(label)}</text>')
    o.append("</svg>")
    return "\n".join(o)


# ------------------------------------------------------------------ draw.io
def drawio():
    cells, eid = [], 0
    order = ["docker", "spark", "gen", "mongo", "hbase", "lake", "s01", "s02", "s03", "s04", "src", "clv", "fun",
             "out", "d1", "d2", "d3"]
    for k in order:
        x, y, w, h, kind, title, lines = N[k]
        stroke, fill = C[kind]
        body = "<br>".join(html.escape(l) for l in lines)
        label = f"<b>{html.escape(title)}</b>" + (f"<br><font style='font-size:11px'>{body}</font>" if body else "")
        valign = "top" if kind in ("spark", "docker", "gen", "mongo", "hbase", "out") else "middle"
        style = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=2;"
                 f"verticalAlign={valign};align={'center' if kind in ('chip', 'int') else 'left'};spacingLeft=10;"
                 f"fontColor=#1b1b1a;{'dashed=1;' if kind == 'docker' else ''}")
        cells.append(f'<mxCell id="{k}" value="{html.escape(label)}" style="{style}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for pts, label, _ in E:
        eid += 1
        (sx, sy), (tx, ty) = pts[0], pts[-1]
        mids = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts[1:-1])
        cells.append(
            f'<mxCell id="e{eid}" value="{html.escape(label or "")}" style="edgeStyle=none;html=1;endArrow=block;{"startArrow=block;" if label == "write / read" else ""}'
            f'strokeColor=#52514e;strokeWidth=2;labelBackgroundColor=#ffffff;fontSize=11;" edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry"><mxPoint x="{sx}" y="{sy}" as="sourcePoint"/>'
            f'<mxPoint x="{tx}" y="{ty}" as="targetPoint"/>{"<Array as=" + chr(34) + "points" + chr(34) + ">" + mids + "</Array>" if mids else ""}'
            f'</mxGeometry></mxCell>')
    return ('<mxfile host="app.diagrams.net"><diagram name="Architecture" id="arch">'
            f'<mxGraphModel dx="1600" dy="900" grid="1" gridSize="10" page="1" pageWidth="{W}" pageHeight="{H}">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) +
            '</root></mxGraphModel></diagram></mxfile>')


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    svg_path = os.path.join(FIG, "fig0_architecture.svg")
    open(svg_path, "w", encoding="utf-8").write(svg())
    open(os.path.join(HERE, "architecture.drawio"), "w", encoding="utf-8").write(drawio())
    try:  # PNG via headless Chromium (playwright) if available
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
            pg.goto(pathlib.Path(svg_path).resolve().as_uri())  # correct file:/// URL on Windows too
            pg.screenshot(path=os.path.join(FIG, "fig0_architecture.png"))
            b.close()
        print("wrote fig0_architecture.svg/.png and architecture.drawio")
    except ImportError:
        print("wrote SVG + drawio (install playwright for PNG, or open the SVG and export)")
