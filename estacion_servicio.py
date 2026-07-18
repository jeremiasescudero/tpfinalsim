"""
Simulación - Estación de Servicio
UTN FRC - Materia Simulación

Sistema por defecto (todo es parametrizable desde CLI):
  - 3 surtidores de combustible (1 empleado c/u)
  - 2 empleados de gomería (independientes)
  - 1 empleado de accesorios

Distribuciones por defecto (tiempos internos en segundos):
  - Llegadas:              Normal(media=24, desv=23)
  - Carga de combustible:  Uniforme(media=50, ±5)               -> 50" ± 5"
  - Gomería:               Uniforme(media=1080, ±480)           -> 18' ± 8'
  - Accesorios:            Uniforme(media=180, ±120)            ->  3' ± 2'

Ruteo por defecto:
  - 80 % carga combustible.
        Al terminar: 30 % accesorios, 20 % gomería, 50 % se retira.
  - 20 % NO carga combustible:
        de ese resto: 40 % accesorios, 60 % gomería.

Salida:
  Tabla HTML con una fila por evento y columnas agrupadas por sección
  (evento, próxima llegada, ruteo, servicios, servidores, colas, estadísticas)
  + una columna dinámica por cliente activo (con su estado).

  Se puede acotar la vista con --desde N y --cantidad K (simular todo,
  mostrar solo K filas a partir de la fila N).
"""

from __future__ import annotations

import argparse
import html
import math
import random
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuración de la simulación
# ---------------------------------------------------------------------------
@dataclass
class Config:
    # cantidades
    n_clientes: int = 500
    n_surtidores: int = 3
    n_gomerias: int = 2
    n_accesorios: int = 1

    # llegadas: Normal(media, desv) en segundos
    lleg_media: float = 24.0
    lleg_desv: float = 23.0

    # carga combustible: Uniforme(media - semi, media + semi) en segundos
    carga_media: float = 50.0
    carga_semi: float = 5.0

    # gomería: Uniforme(media - semi, media + semi) en segundos
    gom_media: float = 18 * 60.0
    gom_semi: float = 8 * 60.0

    # accesorios: Uniforme(media - semi, media + semi) en segundos
    acc_media: float = 3 * 60.0
    acc_semi: float = 2 * 60.0

    # probabilidades de ruteo
    p_carga: float = 0.80             # P(nuevo cliente -> combustible)
    p_no_carga_acc: float = 0.40      # P(no-carga -> accesorios)  (resto -> gomería)
    p_post_carga_acc: float = 0.30    # P(post-carga -> accesorios)
    p_post_carga_gom: float = 0.20    # P(post-carga -> gomería)   (resto -> se retira)

    # semilla
    semilla: Optional[int] = None

    # ventana de visualización
    desde: int = 0
    cantidad: Optional[int] = None    # None = todas desde 'desde'


# ---------------------------------------------------------------------------
# Utilidades de generación de variables aleatorias
# ---------------------------------------------------------------------------
def rnd() -> float:
    return random.random()


def rnd_uniforme(a: float, b: float) -> tuple[float, float]:
    r = rnd()
    return r, a + (b - a) * r


def rnd_normal(media: float, desv: float) -> tuple[float, float, float]:
    """Box-Muller. Devuelve (rnd1, rnd2, valor)."""
    r1 = rnd()
    r2 = rnd()
    z = math.sqrt(-2 * math.log(r1)) * math.cos(2 * math.pi * r2)
    return r1, r2, media + desv * z


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------
@dataclass
class Cliente:
    id: int
    llegada: float
    estado: str = "En espera"
    salida: Optional[float] = None
    ruta: str = ""


@dataclass
class Servidor:
    nombre: str
    ocupado: bool = False
    cliente: Optional[Cliente] = None
    fin: float = float("inf")


@dataclass
class Estadisticas:
    cola_max_surtidor: int = 0
    cola_max_gomeria: int = 0
    cola_max_accesorios: int = 0
    tiempo_max_sistema: float = 0.0
    id_cliente_max_tiempo: int = 0


# ---------------------------------------------------------------------------
# Simulación
# ---------------------------------------------------------------------------
class Simulacion:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        if cfg.semilla is not None:
            random.seed(cfg.semilla)

        self.reloj = 0.0
        self.n_evento = 0

        self.prox_llegada = 0.0
        self.rnd_lleg1: Optional[float] = None
        self.rnd_lleg2: Optional[float] = None
        self.t_lleg: Optional[float] = None

        self.surtidores = [Servidor(f"Surtidor {i+1}")
                           for i in range(cfg.n_surtidores)]
        self.gomerias = [Servidor(f"Gomería {i+1}")
                         for i in range(cfg.n_gomerias)]
        self.accesorios_list = [Servidor(f"Accesorios {i+1}"
                                if cfg.n_accesorios > 1 else "Accesorios")
                                for i in range(cfg.n_accesorios)]

        self.cola_surtidor: list[Cliente] = []
        self.cola_gomeria: list[Cliente] = []
        self.cola_accesorios: list[Cliente] = []

        self.clientes: dict[int, Cliente] = {}
        self.prox_id = 1
        self.arribados = 0                  # cuántos entraron al sistema

        self.stats = Estadisticas()

        # valores aleatorios del evento actual (para pintar solo esa fila)
        self.ult_rnd_carga: Optional[float] = None
        self.ult_t_carga: Optional[float] = None
        self.ult_rnd_gom: Optional[float] = None
        self.ult_t_gom: Optional[float] = None
        self.ult_rnd_acc: Optional[float] = None
        self.ult_t_acc: Optional[float] = None

        self.ult_rnd_tipo: Optional[float] = None
        self.ult_rnd_sub: Optional[float] = None
        self.ult_rnd_post: Optional[float] = None

        self.filas: list[dict] = []

    # ---------- helpers -------------------------------------------------
    def _programar_prox_llegada(self):
        if self.arribados >= self.cfg.n_clientes:
            # ya no llegan más clientes
            self.prox_llegada = float("inf")
            self.rnd_lleg1 = self.rnd_lleg2 = self.t_lleg = None
            return
        r1, r2, t = rnd_normal(self.cfg.lleg_media, self.cfg.lleg_desv)
        t = max(0.1, t)
        self.rnd_lleg1 = r1
        self.rnd_lleg2 = r2
        self.t_lleg = t
        self.prox_llegada = self.reloj + t

    def _libre(self, servidores: list[Servidor]) -> Optional[Servidor]:
        for s in servidores:
            if not s.ocupado:
                return s
        return None

    def _asignar(self, servidor: Servidor, cliente: Cliente,
                 rnd_val: float, dur: float, etiqueta_estado: str,
                 slot_rnd: str, slot_t: str):
        servidor.ocupado = True
        servidor.cliente = cliente
        servidor.fin = self.reloj + dur
        cliente.estado = f"{etiqueta_estado} ({servidor.nombre})"
        setattr(self, slot_rnd, rnd_val)
        setattr(self, slot_t, dur)

    def _iniciar_carga(self, cliente: Cliente):
        s = self._libre(self.surtidores)
        if s is None:
            self.cola_surtidor.append(cliente)
            cliente.estado = "En cola surtidor"
        else:
            a = self.cfg.carga_media - self.cfg.carga_semi
            b = self.cfg.carga_media + self.cfg.carga_semi
            r, dur = rnd_uniforme(a, b)
            self._asignar(s, cliente, r, dur, "Cargando comb.",
                          "ult_rnd_carga", "ult_t_carga")

    def _iniciar_gomeria(self, cliente: Cliente):
        s = self._libre(self.gomerias)
        if s is None:
            self.cola_gomeria.append(cliente)
            cliente.estado = "En cola gomería"
        else:
            a = self.cfg.gom_media - self.cfg.gom_semi
            b = self.cfg.gom_media + self.cfg.gom_semi
            r, dur = rnd_uniforme(a, b)
            self._asignar(s, cliente, r, dur, "En gomería",
                          "ult_rnd_gom", "ult_t_gom")

    def _iniciar_accesorios(self, cliente: Cliente):
        s = self._libre(self.accesorios_list)
        if s is None:
            self.cola_accesorios.append(cliente)
            cliente.estado = "En cola accesorios"
        else:
            a = self.cfg.acc_media - self.cfg.acc_semi
            b = self.cfg.acc_media + self.cfg.acc_semi
            r, dur = rnd_uniforme(a, b)
            self._asignar(s, cliente, r, dur, "Accesorios",
                          "ult_rnd_acc", "ult_t_acc")

    def _salida_cliente(self, cliente: Cliente):
        cliente.salida = self.reloj
        cliente.estado = "Finalizado"
        t_sist = cliente.salida - cliente.llegada
        if t_sist > self.stats.tiempo_max_sistema:
            self.stats.tiempo_max_sistema = t_sist
            self.stats.id_cliente_max_tiempo = cliente.id
        self.clientes.pop(cliente.id, None)

    # ---------- eventos --------------------------------------------------
    def _evento_llegada(self):
        c = Cliente(id=self.prox_id, llegada=self.reloj)
        self.prox_id += 1
        self.arribados += 1
        self.clientes[c.id] = c

        r_tipo = rnd()
        self.ult_rnd_tipo = r_tipo
        if r_tipo < self.cfg.p_carga:
            c.ruta = "combustible"
            self._iniciar_carga(c)
            self.ult_rnd_sub = None
        else:
            r_sub = rnd()
            self.ult_rnd_sub = r_sub
            if r_sub < self.cfg.p_no_carga_acc:
                c.ruta = "solo accesorios"
                self._iniciar_accesorios(c)
            else:
                c.ruta = "solo gomería"
                self._iniciar_gomeria(c)

        self._programar_prox_llegada()

    def _finalizar_servicio(self, servidor: Servidor, proximo_paso):
        cliente = servidor.cliente
        servidor.ocupado = False
        servidor.cliente = None
        servidor.fin = float("inf")
        proximo_paso(cliente)

    def _post_carga(self, cliente: Cliente):
        r = rnd()
        self.ult_rnd_post = r
        acc_hasta = self.cfg.p_post_carga_acc
        gom_hasta = acc_hasta + self.cfg.p_post_carga_gom
        if r < acc_hasta:
            cliente.ruta += " -> accesorios"
            self._iniciar_accesorios(cliente)
        elif r < gom_hasta:
            cliente.ruta += " -> gomería"
            self._iniciar_gomeria(cliente)
        else:
            cliente.ruta += " -> salida"
            self._salida_cliente(cliente)

    def _fin_carga(self, servidor: Servidor):
        self._finalizar_servicio(servidor, self._post_carga)
        if self.cola_surtidor:
            self._iniciar_carga(self.cola_surtidor.pop(0))

    def _fin_gomeria(self, servidor: Servidor):
        self._finalizar_servicio(servidor, self._salida_cliente)
        if self.cola_gomeria:
            self._iniciar_gomeria(self.cola_gomeria.pop(0))

    def _fin_accesorios(self, servidor: Servidor):
        self._finalizar_servicio(servidor, self._salida_cliente)
        if self.cola_accesorios:
            self._iniciar_accesorios(self.cola_accesorios.pop(0))

    # ---------- loop principal -------------------------------------------
    def _actualizar_maximos(self):
        self.stats.cola_max_surtidor = max(
            self.stats.cola_max_surtidor, len(self.cola_surtidor))
        self.stats.cola_max_gomeria = max(
            self.stats.cola_max_gomeria, len(self.cola_gomeria))
        self.stats.cola_max_accesorios = max(
            self.stats.cola_max_accesorios, len(self.cola_accesorios))

    def _proximo_evento(self) -> tuple[str, float, Optional[Servidor]]:
        candidatos: list[tuple[str, float, Optional[Servidor]]] = [
            ("Llegada cliente", self.prox_llegada, None)
        ]
        for s in self.surtidores:
            if s.ocupado:
                candidatos.append((f"Fin carga {s.nombre}", s.fin, s))
        for s in self.gomerias:
            if s.ocupado:
                candidatos.append((f"Fin {s.nombre}", s.fin, s))
        for s in self.accesorios_list:
            if s.ocupado:
                candidatos.append((f"Fin {s.nombre}", s.fin, s))
        return min(candidatos, key=lambda x: x[1])

    def _limpiar_valores_evento(self):
        self.ult_rnd_carga = None
        self.ult_t_carga = None
        self.ult_rnd_gom = None
        self.ult_t_gom = None
        self.ult_rnd_acc = None
        self.ult_t_acc = None
        self.ult_rnd_tipo = None
        self.ult_rnd_sub = None
        self.ult_rnd_post = None
        self.rnd_lleg1 = None
        self.rnd_lleg2 = None
        self.t_lleg = None

    def ejecutar(self):
        self._programar_prox_llegada()
        self._registrar_fila("Inicialización")
        self._limpiar_valores_evento()

        while True:
            nombre, t, servidor = self._proximo_evento()
            if t == float("inf"):
                break               # no quedan eventos por procesar
            self.reloj = t
            self.n_evento += 1

            if nombre == "Llegada cliente":
                self._evento_llegada()
            elif nombre.startswith("Fin carga"):
                self._fin_carga(servidor)               # type: ignore[arg-type]
            elif "Gomería" in nombre:
                self._fin_gomeria(servidor)             # type: ignore[arg-type]
            elif "Accesorios" in nombre:
                self._fin_accesorios(servidor)          # type: ignore[arg-type]

            self._actualizar_maximos()
            self._registrar_fila(nombre)
            self._limpiar_valores_evento()

    # ---------- registro de filas ----------------------------------------
    def _registrar_fila(self, evento: str):
        fila = {
            "N": self.n_evento,
            "Evento": evento,
            "Reloj (s)": round(self.reloj, 2),

            "RND1 lleg.": self.rnd_lleg1,
            "RND2 lleg.": self.rnd_lleg2,
            "Δ llegada (s)": self.t_lleg,
            "Próx. llegada": (round(self.prox_llegada, 2)
                              if self.prox_llegada != float("inf")
                              else "—"),

            "RND tipo": self.ult_rnd_tipo,
            "RND subruta": self.ult_rnd_sub,
            "RND post-carga": self.ult_rnd_post,

            "RND carga": self.ult_rnd_carga,
            "T carga (s)": self.ult_t_carga,

            "RND gomería": self.ult_rnd_gom,
            "T gomería (s)": self.ult_t_gom,

            "RND acces.": self.ult_rnd_acc,
            "T acces. (s)": self.ult_t_acc,
        }

        # columnas de servidores (dinámicas según cantidad configurada)
        for s in self.surtidores + self.gomerias + self.accesorios_list:
            fila[s.nombre] = self._estado_servidor(s)

        fila["Cola surt."] = len(self.cola_surtidor)
        fila["Cola gom."] = len(self.cola_gomeria)
        fila["Cola acces."] = len(self.cola_accesorios)

        fila["Máx cola surt."] = self.stats.cola_max_surtidor
        fila["Máx cola gom."] = self.stats.cola_max_gomeria
        fila["Máx cola acces."] = self.stats.cola_max_accesorios
        fila["Máx T sistema (s)"] = round(self.stats.tiempo_max_sistema, 2)

        for cid in sorted(self.clientes.keys()):
            fila[f"C{cid}"] = self.clientes[cid].estado

        self.filas.append(fila)

    def _estado_servidor(self, s: Servidor) -> str:
        if not s.ocupado or s.cliente is None:
            return "Libre"
        return f"C{s.cliente.id} (fin {round(s.fin, 1)})"


# ---------------------------------------------------------------------------
# Renderizado a HTML
# ---------------------------------------------------------------------------
CSS = """
:root { color-scheme: light dark; }
body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    margin: 24px; background: #fafafa; color: #111;
}
h1 { font-size: 20px; margin-bottom: 4px; }
.resumen {
    background: #fff; border: 1px solid #ddd; padding: 12px 16px;
    border-radius: 8px; display: inline-block; margin: 8px 0 16px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.resumen div { margin: 2px 0; }
.cols { display: flex; gap: 32px; }
.tabla-wrap { overflow-x: auto; border: 1px solid #ccc; border-radius: 6px; }
table { border-collapse: collapse; font-size: 12px; white-space: nowrap; }
th, td {
    padding: 4px 8px; text-align: right;
    border-right: 1px solid #e0e0e0; border-bottom: 1px solid #eee;
}
th { position: sticky; top: 0; z-index: 2; font-weight: 600; }
tbody tr:nth-child(even) { background: #f5f7fb; }
tbody tr:hover { background: #eef3ff; }

th.evt      { background: #37474f; color: #fff; }
th.lleg     { background: #1976d2; color: #fff; }
th.ruta     { background: #6a1b9a; color: #fff; }
th.srv-carga{ background: #ef6c00; color: #fff; }
th.srv-gom  { background: #2e7d32; color: #fff; }
th.srv-acc  { background: #c2185b; color: #fff; }
th.servs    { background: #455a64; color: #fff; }
th.colas    { background: #00838f; color: #fff; }
th.stats    { background: #b71c1c; color: #fff; }
th.cli      { background: #5d4037; color: #fff; }

td.evento{ text-align: left; font-weight: 600; }
td.cli   { text-align: left; font-family: ui-monospace, Consolas, monospace; }

@media (prefers-color-scheme: dark) {
    body { background: #111; color: #eee; }
    .resumen { background: #1c1c1c; border-color: #333; }
    .tabla-wrap { border-color: #333; }
    th, td { border-color: #2a2a2a; }
    tbody tr:nth-child(even) { background: #1a1a1a; }
    tbody tr:hover { background: #263043; }
}
"""


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"
    return str(v)


def a_html(sim: Simulacion, ruta: Path):
    cfg = sim.cfg

    # ventana
    inicio = max(0, cfg.desde)
    fin = (inicio + cfg.cantidad) if cfg.cantidad is not None else len(sim.filas)
    fin = min(fin, len(sim.filas))
    ventana = sim.filas[inicio:fin]
    total_filas = len(sim.filas)

    # grupos de columnas fijas
    nombres_surt = [s.nombre for s in sim.surtidores]
    nombres_gom = [s.nombre for s in sim.gomerias]
    nombres_acc = [s.nombre for s in sim.accesorios_list]

    grupos = [
        ("evt", "Evento", ["N", "Evento", "Reloj (s)"]),
        ("lleg", "Próxima llegada",
            ["RND1 lleg.", "RND2 lleg.", "Δ llegada (s)", "Próx. llegada"]),
        ("ruta", "Ruteo cliente",
            ["RND tipo", "RND subruta", "RND post-carga"]),
        ("srv-carga", "Servicio: carga", ["RND carga", "T carga (s)"]),
        ("srv-gom", "Servicio: gomería", ["RND gomería", "T gomería (s)"]),
        ("srv-acc", "Servicio: accesorios", ["RND acces.", "T acces. (s)"]),
        ("servs", "Estado servidores",
            nombres_surt + nombres_gom + nombres_acc),
        ("colas", "Longitud colas",
            ["Cola surt.", "Cola gom.", "Cola acces."]),
        ("stats", "Estadísticas máximas",
            ["Máx cola surt.", "Máx cola gom.", "Máx cola acces.",
             "Máx T sistema (s)"]),
    ]

    # columnas dinámicas de clientes: solo los que aparecen en la ventana
    dinam = set()
    for f in ventana:
        for k in f.keys():
            if k.startswith("C") and k[1:].isdigit():
                dinam.add(k)
    dinam_orden = sorted(dinam, key=lambda x: int(x[1:]))

    # encabezado banda (grupo)
    thead_1 = ""
    for clave, titulo, cols in grupos:
        thead_1 += (f'<th class="{clave}" colspan="{len(cols)}">'
                    f'{html.escape(titulo)}</th>')
    if dinam_orden:
        thead_1 += (f'<th class="cli" colspan="{len(dinam_orden)}">'
                    f'Objetos temporales (clientes)</th>')

    # encabezado columna
    thead_2 = ""
    for clave, _, cols in grupos:
        for c in cols:
            thead_2 += f'<th class="{clave}">{html.escape(c)}</th>'
    for c in dinam_orden:
        thead_2 += f'<th class="cli">{html.escape(c)}</th>'

    filas_html = []
    for f in ventana:
        celdas = []
        for clave, _, cols in grupos:
            for c in cols:
                extra_class = "evento" if c == "Evento" else ""
                celdas.append(
                    f'<td class="{clave} {extra_class}">{_fmt(f.get(c))}</td>')
        for c in dinam_orden:
            celdas.append(f'<td class="cli">{_fmt(f.get(c, ""))}</td>')
        filas_html.append("<tr>" + "".join(celdas) + "</tr>")

    tmax_min = sim.stats.tiempo_max_sistema / 60

    resumen_izq = f"""
        <div><b>Clientes configurados:</b> {cfg.n_clientes}</div>
        <div><b>Clientes arribados:</b> {sim.arribados}</div>
        <div><b>Eventos totales:</b> {total_filas - 1}
             &nbsp;<i>(mostrando {len(ventana)}: filas {inicio}–{inicio+len(ventana)-1})</i></div>
        <div><b>Semilla:</b> {cfg.semilla if cfg.semilla is not None else 'aleatoria'}</div>
    """
    resumen_der = f"""
        <div><b>Cola máx surtidores:</b> {sim.stats.cola_max_surtidor}</div>
        <div><b>Cola máx gomería:</b> {sim.stats.cola_max_gomeria}</div>
        <div><b>Cola máx accesorios:</b> {sim.stats.cola_max_accesorios}</div>
        <div><b>T máx en sistema:</b>
             {sim.stats.tiempo_max_sistema:.2f} s ({tmax_min:.2f} min)
             — cliente C{sim.stats.id_cliente_max_tiempo}</div>
    """

    params = f"""
        <div><b>Llegadas:</b> Normal(μ={cfg.lleg_media}, σ={cfg.lleg_desv}) s</div>
        <div><b>Carga:</b> Uniforme({cfg.carga_media}±{cfg.carga_semi}) s</div>
        <div><b>Gomería:</b> Uniforme({cfg.gom_media}±{cfg.gom_semi}) s</div>
        <div><b>Accesorios:</b> Uniforme({cfg.acc_media}±{cfg.acc_semi}) s</div>
        <div><b>Servidores:</b> {cfg.n_surtidores} surt, {cfg.n_gomerias} gom, {cfg.n_accesorios} acc</div>
        <div><b>Ruteo:</b> p(carga)={cfg.p_carga};
             no-carga→acc={cfg.p_no_carga_acc};
             post-carga: acc={cfg.p_post_carga_acc}, gom={cfg.p_post_carga_gom}</div>
    """

    doc = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Simulación Estación de Servicio</title>
<style>{CSS}</style></head><body>
<h1>Simulación — Estación de Servicio</h1>
<div class="cols">
    <div class="resumen">{resumen_izq}</div>
    <div class="resumen">{resumen_der}</div>
    <div class="resumen">{params}</div>
</div>
<div class="tabla-wrap">
<table>
    <thead>
        <tr>{thead_1}</tr>
        <tr>{thead_2}</tr>
    </thead>
    <tbody>
        {''.join(filas_html)}
    </tbody>
</table>
</div>
</body></html>"""

    ruta.write_text(doc, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> Config:
    p = argparse.ArgumentParser(
        description="Simulación estación de servicio (UTN - Simulación)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    g_sim = p.add_argument_group("Simulación")
    g_sim.add_argument("-n", "--clientes", type=int, default=500,
                       help="Cantidad total de clientes a simular")
    g_sim.add_argument("-s", "--semilla", type=int, default=None,
                       help="Semilla del generador aleatorio")

    g_vista = p.add_argument_group("Ventana de visualización (filas mostradas)")
    g_vista.add_argument("--desde", type=int, default=0,
                         help="Índice de la primera fila a mostrar")
    g_vista.add_argument("--cantidad", type=int, default=None,
                         help="Cantidad de filas a mostrar (por defecto: todas)")
    g_vista.add_argument("-o", "--salida", type=str,
                         default="estacion_servicio.html",
                         help="Archivo HTML de salida")
    g_vista.add_argument("--abrir", action="store_true",
                         help="Abrir el HTML en el navegador al terminar")

    g_srv = p.add_argument_group("Servidores")
    g_srv.add_argument("--surtidores", type=int, default=3)
    g_srv.add_argument("--gomerias", type=int, default=2)
    g_srv.add_argument("--accesorios", type=int, default=1)

    g_lleg = p.add_argument_group("Llegadas (Normal, en segundos)")
    g_lleg.add_argument("--lleg-media", type=float, default=24.0)
    g_lleg.add_argument("--lleg-desv", type=float, default=23.0)

    g_carga = p.add_argument_group("Carga de combustible (Uniforme, en segundos)")
    g_carga.add_argument("--carga-media", type=float, default=50.0)
    g_carga.add_argument("--carga-semi", type=float, default=5.0,
                         help="Semi-amplitud: usa media±semi (50±5)")

    g_gom = p.add_argument_group("Gomería (Uniforme, en segundos)")
    g_gom.add_argument("--gom-media", type=float, default=18 * 60.0,
                       help="Default 1080 s (18 min)")
    g_gom.add_argument("--gom-semi", type=float, default=8 * 60.0,
                       help="Default 480 s (8 min)")

    g_acc = p.add_argument_group("Accesorios (Uniforme, en segundos)")
    g_acc.add_argument("--acc-media", type=float, default=3 * 60.0,
                       help="Default 180 s (3 min)")
    g_acc.add_argument("--acc-semi", type=float, default=2 * 60.0,
                       help="Default 120 s (2 min)")

    g_rut = p.add_argument_group("Probabilidades de ruteo")
    g_rut.add_argument("--p-carga", type=float, default=0.80,
                       help="P(cliente nuevo -> combustible)")
    g_rut.add_argument("--p-no-carga-acc", type=float, default=0.40,
                       help="P(no-carga -> accesorios); resto -> gomería")
    g_rut.add_argument("--p-post-carga-acc", type=float, default=0.30,
                       help="P(post-carga -> accesorios)")
    g_rut.add_argument("--p-post-carga-gom", type=float, default=0.20,
                       help="P(post-carga -> gomería); resto -> se retira")

    args = p.parse_args()

    # validación básica de probabilidades
    if not (0 <= args.p_carga <= 1
            and 0 <= args.p_no_carga_acc <= 1
            and 0 <= args.p_post_carga_acc <= 1
            and 0 <= args.p_post_carga_gom <= 1
            and args.p_post_carga_acc + args.p_post_carga_gom <= 1):
        p.error("Las probabilidades deben estar en [0,1] y "
                "p_post_carga_acc + p_post_carga_gom ≤ 1")

    return Config(
        n_clientes=args.clientes,
        n_surtidores=args.surtidores,
        n_gomerias=args.gomerias,
        n_accesorios=args.accesorios,
        lleg_media=args.lleg_media,
        lleg_desv=args.lleg_desv,
        carga_media=args.carga_media,
        carga_semi=args.carga_semi,
        gom_media=args.gom_media,
        gom_semi=args.gom_semi,
        acc_media=args.acc_media,
        acc_semi=args.acc_semi,
        p_carga=args.p_carga,
        p_no_carga_acc=args.p_no_carga_acc,
        p_post_carga_acc=args.p_post_carga_acc,
        p_post_carga_gom=args.p_post_carga_gom,
        semilla=args.semilla,
        desde=args.desde,
        cantidad=args.cantidad,
    ), args.salida, args.abrir


def main():
    cfg, salida, abrir = parse_args()
    sim = Simulacion(cfg)
    sim.ejecutar()

    ruta = Path(salida).resolve()
    a_html(sim, ruta)

    total = len(sim.filas)
    inicio = max(0, cfg.desde)
    fin = (inicio + cfg.cantidad) if cfg.cantidad is not None else total
    fin = min(fin, total)

    print(f"Clientes arribados : {sim.arribados}")
    print(f"Eventos totales    : {total - 1}")
    print(f"Filas mostradas    : {fin - inicio}  (desde {inicio} a {fin-1})")
    print(f"Cola máx surt.     : {sim.stats.cola_max_surtidor}")
    print(f"Cola máx gomería   : {sim.stats.cola_max_gomeria}")
    print(f"Cola máx acces.    : {sim.stats.cola_max_accesorios}")
    print(f"T máx en sistema   : {sim.stats.tiempo_max_sistema:.2f} s "
          f"({sim.stats.tiempo_max_sistema/60:.2f} min) "
          f"(cliente C{sim.stats.id_cliente_max_tiempo})")
    print(f"Archivo HTML       : {ruta}")

    if abrir:
        webbrowser.open(ruta.as_uri())


if __name__ == "__main__":
    main()
