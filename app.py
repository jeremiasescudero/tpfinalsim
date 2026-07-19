"""
Interfaz web para la simulacion de estacion de servicio.
Ejecutar: python app.py
Abrir: http://localhost:5000
"""

from flask import Flask, request, render_template_string
from estacion_servicio import Config, Simulacion, _fmt
import html as html_mod

app = Flask(__name__)

CAMPOS = [
    ("n_clientes",   "Cantidad de clientes",               500,   "int",   "Simulacion",        "Cuantos clientes se generan"),
    ("semilla",      "Semilla (vacio = aleatoria)",          "",   "oint",  "Simulacion",        "Semilla del generador aleatorio"),
    ("desde",        "Mostrar desde fila",                    0,   "int",   "Visualizacion",     "Indice de la primera fila a mostrar"),
    ("cantidad",     "Cant. filas a mostrar (vacio = todas)","",   "oint",  "Visualizacion",     "Cantidad de filas a mostrar"),
    ("n_surtidores", "Surtidores",                            3,   "int",   "Servidores",        "Cantidad de surtidores de combustible"),
    ("n_gomerias",   "Empleados de gomeria",                  2,   "int",   "Servidores",        "Cantidad de empleados de gomeria"),
    ("n_accesorios", "Puestos de accesorios",                 1,   "int",   "Servidores",        "Cantidad de puestos de venta de accesorios"),
    ("lleg_media",   "Media (seg)",                         24.0,  "float", "Llegadas - Normal",         "Media de la distribucion normal (segundos)"),
    ("lleg_desv",    "Desv. estandar (seg)",                23.0,  "float", "Llegadas - Normal",         "Desviacion estandar (segundos)"),
    ("carga_a",      "A - minimo (seg)",                    45.0,  "float", "Carga combustible - Uniforme(A, B)", "Limite inferior en segundos"),
    ("carga_b",      "B - maximo (seg)",                    55.0,  "float", "Carga combustible - Uniforme(A, B)", "Limite superior en segundos"),
    ("gom_a",        "A - minimo (min)",                    10.0,  "float", "Gomeria - Uniforme(A, B)",  "Limite inferior en minutos"),
    ("gom_b",        "B - maximo (min)",                    26.0,  "float", "Gomeria - Uniforme(A, B)",  "Limite superior en minutos"),
    ("acc_a",        "A - minimo (min)",                     1.0,  "float", "Accesorios - Uniforme(A, B)", "Limite inferior en minutos"),
    ("acc_b",        "B - maximo (min)",                     5.0,  "float", "Accesorios - Uniforme(A, B)", "Limite superior en minutos"),
    ("p_carga",          "P(combustible)",                  0.80,  "float", "Probabilidades de ruteo", "Prob. de que un cliente vaya a cargar combustible"),
    ("p_no_carga_acc",   "P(no-carga -> accesorios)",       0.40,  "float", "Probabilidades de ruteo", "Si no carga: prob. de ir a accesorios (resto -> gomeria)"),
    ("p_post_carga_acc", "P(post-carga -> accesorios)",     0.30,  "float", "Probabilidades de ruteo", "Al terminar la carga: prob. de ir a accesorios"),
    ("p_post_carga_gom", "P(post-carga -> gomeria)",        0.20,  "float", "Probabilidades de ruteo", "Al terminar la carga: prob. de ir a gomeria (resto -> sale)"),
]


def _val(form, field_id, tipo, default):
    raw = form.get(field_id, "").strip()
    if raw == "":
        return default
    if tipo == "int":
        return int(raw)
    if tipo == "oint":
        return int(raw) if raw else None
    if tipo == "float":
        return float(raw)
    return raw


TEMPLATE = r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulacion - Estacion de Servicio</title>
<style>
:root { color-scheme: light dark; --bg: #f5f6fa; --card: #fff; --border: #ddd;
        --text: #111; --text2: #555; --accent: #1976d2; --accent2: #ef6c00; }
@media (prefers-color-scheme: dark) {
    :root { --bg: #0e0e0e; --card: #1a1a1a; --border: #333;
            --text: #eee; --text2: #aaa; --accent: #64b5f6; --accent2: #ffb74d; }
}
*, *::before, *::after { box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 0;
       background: var(--bg); color: var(--text); }
header { background: #263238; color: #fff; padding: 16px 24px; }
header h1 { margin: 0; font-size: 20px; font-weight: 600; }
header p  { margin: 4px 0 0; font-size: 13px; opacity: .7; }

.layout { display: flex; min-height: calc(100vh - 70px); }

.panel { width: 380px; min-width: 300px; background: var(--card);
         border-right: 1px solid var(--border); padding: 16px;
         overflow-y: auto; max-height: calc(100vh - 70px); }
.grupo-titulo {
    font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .5px; color: var(--accent); margin: 18px 0 6px;
    border-bottom: 1px solid var(--border); padding-bottom: 4px;
}
.grupo-titulo:first-of-type { margin-top: 0; }
.campo { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
.campo label { flex: 1; font-size: 13px; color: var(--text2); }
.campo input { width: 100px; padding: 5px 8px; border: 1px solid var(--border);
               border-radius: 4px; font-size: 13px; background: var(--bg);
               color: var(--text); text-align: right; }
.campo input:focus { outline: 2px solid var(--accent); border-color: transparent; }
.btn-row { margin-top: 16px; display: flex; gap: 8px; }
button {
    flex: 1; padding: 10px; border: none; border-radius: 6px; cursor: pointer;
    font-size: 14px; font-weight: 600; transition: .15s;
}
button[type=submit] { background: var(--accent); color: #fff; }
button[type=submit]:hover { filter: brightness(1.15); }
button[type=reset] { background: var(--border); color: var(--text); }

.resultados { flex: 1; padding: 16px; overflow: auto; max-height: calc(100vh - 70px); }
.cards { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 12px 16px; min-width: 200px;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.card h3 { margin: 0 0 6px; font-size: 13px; color: var(--accent); text-transform: uppercase; letter-spacing: .3px; }
.card div { font-size: 13px; margin: 2px 0; }

.tabla-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 6px; }
table { border-collapse: collapse; font-size: 12px; white-space: nowrap; width: max-content; }
th, td { padding: 4px 8px; text-align: right; border-right: 1px solid var(--border);
         border-bottom: 1px solid var(--border); }
th { position: sticky; top: 0; z-index: 2; font-weight: 600; }
tbody tr:nth-child(even) { background: rgba(128,128,128,.06); }
tbody tr:hover { background: rgba(25,118,210,.08); }

th.evt       { background: #37474f; color: #fff; }
th.lleg      { background: #1976d2; color: #fff; }
th.ruta      { background: #6a1b9a; color: #fff; }
th.srv-carga { background: #ef6c00; color: #fff; }
th.srv-gom   { background: #2e7d32; color: #fff; }
th.srv-acc   { background: #c2185b; color: #fff; }
th.servs     { background: #455a64; color: #fff; }
th.colas     { background: #00838f; color: #fff; }
th.stats     { background: #b71c1c; color: #fff; }
th.cli       { background: #5d4037; color: #fff; }

td.evento { text-align: left; font-weight: 600; }
td.cli    { text-align: left; font-family: ui-monospace, Consolas, monospace; font-size: 11px; }

.empty { text-align: center; padding: 80px 20px; color: var(--text2); }
.empty h2 { margin: 0 0 8px; font-size: 18px; }
</style>
</head><body>

<header>
    <h1>Simulacion - Estacion de Servicio</h1>
    <p>UTN FRC - Materia Simulacion - Todos los parametros son configurables</p>
</header>

<div class="layout">
<form class="panel" method="POST" action="/">
{% set ns = namespace(current_group=None) %}
{% for id, label, default, tipo, grupo, tooltip in campos %}
    {% if grupo != ns.current_group %}
        {% set ns.current_group = grupo %}
        <div class="grupo-titulo">{{ grupo }}</div>
    {% endif %}
    <div class="campo" title="{{ tooltip }}">
        <label for="{{ id }}">{{ label }}</label>
        <input id="{{ id }}" name="{{ id }}"
               type="{% if tipo in ('int','oint') %}number{% else %}text{% endif %}"
               {% if tipo in ('int','oint') %}step="1"{% endif %}
               {% if tipo == 'float' %}inputmode="decimal"{% endif %}
               value="{{ valores.get(id, default) }}"
               {% if tipo == 'oint' %}placeholder="---"{% endif %}
        >
    </div>
{% endfor %}

    <div class="btn-row">
        <button type="submit">Simular</button>
        <button type="reset">Reset</button>
    </div>
</form>

<div class="resultados">
{% if not resultado %}
    <div class="empty">
        <h2>Configura los parametros y hace clic en Simular</h2>
        <p>Los valores por defecto corresponden al enunciado original del TP.</p>
    </div>
{% else %}
    <div class="cards">
        <div class="card">
            <h3>Simulacion</h3>
            <div><b>Clientes arribados:</b> {{ resultado.arribados }}</div>
            <div><b>Eventos totales:</b> {{ resultado.total_eventos }}</div>
            <div><b>Filas mostradas:</b> {{ resultado.filas_mostradas }}
                 ({{ resultado.desde }}-{{ resultado.hasta }})</div>
            <div><b>Semilla:</b> {{ resultado.semilla }}</div>
        </div>
        <div class="card">
            <h3>Colas maximas</h3>
            <div><b>Surtidores:</b> {{ resultado.cola_max_surt }}</div>
            <div><b>Gomeria:</b> {{ resultado.cola_max_gom }}</div>
            <div><b>Accesorios:</b> {{ resultado.cola_max_acc }}</div>
        </div>
        <div class="card">
            <h3>Tiempo maximo en sistema</h3>
            <div><b>{{ resultado.t_max_s }}</b> s = <b>{{ resultado.t_max_m }}</b> min</div>
            <div>Cliente <b>C{{ resultado.t_max_cliente }}</b></div>
        </div>
        <div class="card">
            <h3>Parametros usados</h3>
            <div><b>Llegadas:</b> Normal(media={{ resultado.lleg_media }}s, desv={{ resultado.lleg_desv }}s)</div>
            <div><b>Carga:</b> U({{ resultado.carga_a }}, {{ resultado.carga_b }}) seg</div>
            <div><b>Gomeria:</b> U({{ resultado.gom_a }}, {{ resultado.gom_b }}) min</div>
            <div><b>Accesorios:</b> U({{ resultado.acc_a }}, {{ resultado.acc_b }}) min</div>
            <div><b>Servidores:</b> {{ resultado.n_surt }} surt - {{ resultado.n_gom }} gom - {{ resultado.n_acc }} acc</div>
        </div>
    </div>

    <div class="tabla-wrap">
    <table>
        <thead>
            <tr>{{ resultado.thead1 | safe }}</tr>
            <tr>{{ resultado.thead2 | safe }}</tr>
        </thead>
        <tbody>
            {{ resultado.tbody | safe }}
        </tbody>
    </table>
    </div>
{% endif %}
</div>
</div>

</body></html>"""


def build_tabla(sim: Simulacion, desde: int, cantidad):
    cfg = sim.cfg

    inicio = max(0, desde)
    fin = (inicio + cantidad) if cantidad is not None else len(sim.filas)
    fin = min(fin, len(sim.filas))
    ventana = sim.filas[inicio:fin]

    nombres_surt = [s.nombre for s in sim.surtidores]
    nombres_gom = [s.nombre for s in sim.gomerias]
    nombres_acc = [s.nombre for s in sim.accesorios_list]

    grupos = [
        ("evt", "Evento", ["N", "Evento", "Reloj (s)"]),
        ("lleg", "Proxima llegada",
            ["RND1 lleg.", "RND2 lleg.", "T entre lleg. (s)", "Prox. llegada"]),
        ("ruta", "Ruteo cliente",
            ["RND tipo", "RND subruta", "RND post-carga"]),
        ("srv-carga", "Servicio: carga", ["RND carga", "T carga (s)"]),
        ("srv-gom", "Servicio: gomeria", ["RND gomeria", "T gomeria (s)"]),
        ("srv-acc", "Servicio: accesorios", ["RND acces.", "T acces. (s)"]),
        ("servs", "Estado servidores",
            nombres_surt + nombres_gom + nombres_acc),
        ("colas", "Longitud colas",
            ["Cola surt.", "Cola gom.", "Cola acces."]),
        ("stats", "Estadisticas maximas",
            ["Max cola surt.", "Max cola gom.", "Max cola acces.",
             "Max T sistema (s)"]),
    ]

    dinam = set()
    for f in ventana:
        for k in f.keys():
            if k.startswith("C") and k[1:].isdigit():
                dinam.add(k)
    dinam_orden = sorted(dinam, key=lambda x: int(x[1:]))

    thead1 = ""
    for clave, titulo, cols in grupos:
        thead1 += (f'<th class="{clave}" colspan="{len(cols)}">'
                   f'{html_mod.escape(titulo)}</th>')
    if dinam_orden:
        thead1 += (f'<th class="cli" colspan="{len(dinam_orden)}">'
                   f'Objetos temporales (clientes)</th>')

    thead2 = ""
    for clave, _, cols in grupos:
        for c in cols:
            thead2 += f'<th class="{clave}">{html_mod.escape(c)}</th>'
    for c in dinam_orden:
        thead2 += f'<th class="cli">{html_mod.escape(c)}</th>'

    filas_html = []
    for f in ventana:
        celdas = []
        for clave, _, cols in grupos:
            for c in cols:
                extra = " evento" if c == "Evento" else ""
                celdas.append(
                    f'<td class="{clave}{extra}">{_fmt(f.get(c))}</td>')
        for c in dinam_orden:
            celdas.append(f'<td class="cli">{_fmt(f.get(c, ""))}</td>')
        filas_html.append("<tr>" + "".join(celdas) + "</tr>")

    tmax_min = sim.stats.tiempo_max_sistema / 60

    return {
        "thead1": thead1,
        "thead2": thead2,
        "tbody": "\n".join(filas_html),
        "arribados": sim.arribados,
        "total_eventos": len(sim.filas) - 1,
        "filas_mostradas": len(ventana),
        "desde": inicio,
        "hasta": inicio + len(ventana) - 1,
        "semilla": cfg.semilla if cfg.semilla is not None else "aleatoria",
        "cola_max_surt": sim.stats.cola_max_surtidor,
        "cola_max_gom": sim.stats.cola_max_gomeria,
        "cola_max_acc": sim.stats.cola_max_accesorios,
        "t_max_s": f"{sim.stats.tiempo_max_sistema:.2f}",
        "t_max_m": f"{tmax_min:.2f}",
        "t_max_cliente": sim.stats.id_cliente_max_tiempo,
        "lleg_media": cfg.lleg_media,
        "lleg_desv": cfg.lleg_desv,
        "carga_a": cfg.carga_a,
        "carga_b": cfg.carga_b,
        "gom_a": cfg.gom_a,
        "gom_b": cfg.gom_b,
        "acc_a": cfg.acc_a,
        "acc_b": cfg.acc_b,
        "n_surt": cfg.n_surtidores,
        "n_gom": cfg.n_gomerias,
        "n_acc": cfg.n_accesorios,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    resultado = None
    valores = {}

    if request.method == "POST":
        f = request.form
        for campo_id, _, default, tipo, _, _ in CAMPOS:
            raw = f.get(campo_id, "").strip()
            valores[campo_id] = raw if raw else default

        cfg = Config(
            n_clientes=_val(f, "n_clientes", "int", 500),
            semilla=_val(f, "semilla", "oint", None),
            n_surtidores=_val(f, "n_surtidores", "int", 3),
            n_gomerias=_val(f, "n_gomerias", "int", 2),
            n_accesorios=_val(f, "n_accesorios", "int", 1),
            lleg_media=_val(f, "lleg_media", "float", 24.0),
            lleg_desv=_val(f, "lleg_desv", "float", 23.0),
            carga_a=_val(f, "carga_a", "float", 45.0),
            carga_b=_val(f, "carga_b", "float", 55.0),
            gom_a=_val(f, "gom_a", "float", 10.0),
            gom_b=_val(f, "gom_b", "float", 26.0),
            acc_a=_val(f, "acc_a", "float", 1.0),
            acc_b=_val(f, "acc_b", "float", 5.0),
            p_carga=_val(f, "p_carga", "float", 0.80),
            p_no_carga_acc=_val(f, "p_no_carga_acc", "float", 0.40),
            p_post_carga_acc=_val(f, "p_post_carga_acc", "float", 0.30),
            p_post_carga_gom=_val(f, "p_post_carga_gom", "float", 0.20),
        )

        desde = _val(f, "desde", "int", 0)
        cantidad = _val(f, "cantidad", "oint", None)

        sim = Simulacion(cfg)
        sim.ejecutar()
        resultado = build_tabla(sim, desde, cantidad)

    return render_template_string(
        TEMPLATE,
        campos=CAMPOS,
        valores=valores,
        resultado=resultado,
    )


if __name__ == "__main__":
    print("  Abri http://localhost:5000 en tu navegador")
    app.run(debug=True, port=5000)
