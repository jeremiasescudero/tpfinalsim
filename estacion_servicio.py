"""
Simulacion - Estacion de Servicio
UTN FRC - Materia Simulacion

Distribuciones por defecto:
  - Llegadas:              Normal(media=24", desv=23")
  - Carga de combustible:  Uniforme(45", 55")           -> 50" +/- 5"
  - Gomeria:               Uniforme(10', 26')            -> 18' +/- 8'
  - Accesorios:            Uniforme(1', 5')              ->  3' +/- 2'

Ruteo por defecto:
  80% carga combustible -> de esos: 30% acc, 20% gom, 50% sale.
  20% no carga -> 40% acc, 60% gom.
"""

from __future__ import annotations

import argparse
import html
import math
import random
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    n_clientes: int = 500
    n_surtidores: int = 3
    n_gomerias: int = 2
    n_accesorios: int = 1

    lleg_media: float = 24.0
    lleg_desv: float = 23.0

    # uniformes: A y B directos, internamente en minutos
    carga_a: float = 45.0       # segundos
    carga_b: float = 55.0       # segundos
    gom_a: float = 10.0         # minutos
    gom_b: float = 26.0         # minutos
    acc_a: float = 1.0          # minutos
    acc_b: float = 5.0          # minutos

    p_carga: float = 0.80
    p_no_carga_acc: float = 0.40
    p_post_carga_acc: float = 0.30
    p_post_carga_gom: float = 0.20

    semilla: Optional[int] = None
    desde: int = 0
    cantidad: Optional[int] = None


def rnd() -> float:
    return random.random()


def rnd_uniforme(a: float, b: float) -> tuple[float, float]:
    r = rnd()
    return r, a + (b - a) * r


def rnd_normal(media: float, desv: float) -> tuple[float, float, float]:
    r1 = rnd()
    r2 = rnd()
    z = math.sqrt(-2 * math.log(r1)) * math.cos(2 * math.pi * r2)
    return r1, r2, media + desv * z


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
        self.gomerias = [Servidor(f"Gomeria {i+1}")
                         for i in range(cfg.n_gomerias)]
        self.accesorios_list = [Servidor(f"Accesorios {i+1}"
                                if cfg.n_accesorios > 1 else "Accesorios")
                                for i in range(cfg.n_accesorios)]

        self.cola_surtidor: list[Cliente] = []
        self.cola_gomeria: list[Cliente] = []
        self.cola_accesorios: list[Cliente] = []

        self.clientes: dict[int, Cliente] = {}
        self.prox_id = 1
        self.arribados = 0

        self.stats = Estadisticas()

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

    def _programar_prox_llegada(self):
        if self.arribados >= self.cfg.n_clientes:
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
            r, dur = rnd_uniforme(self.cfg.carga_a, self.cfg.carga_b)
            self._asignar(s, cliente, r, dur, "Cargando comb.",
                          "ult_rnd_carga", "ult_t_carga")

    def _iniciar_gomeria(self, cliente: Cliente):
        s = self._libre(self.gomerias)
        if s is None:
            self.cola_gomeria.append(cliente)
            cliente.estado = "En cola gomeria"
        else:
            # A y B en minutos -> convertir a segundos
            a_seg = self.cfg.gom_a * 60
            b_seg = self.cfg.gom_b * 60
            r, dur = rnd_uniforme(a_seg, b_seg)
            self._asignar(s, cliente, r, dur, "En gomeria",
                          "ult_rnd_gom", "ult_t_gom")

    def _iniciar_accesorios(self, cliente: Cliente):
        s = self._libre(self.accesorios_list)
        if s is None:
            self.cola_accesorios.append(cliente)
            cliente.estado = "En cola accesorios"
        else:
            # A y B en minutos -> convertir a segundos
            a_seg = self.cfg.acc_a * 60
            b_seg = self.cfg.acc_b * 60
            r, dur = rnd_uniforme(a_seg, b_seg)
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
                c.ruta = "solo gomeria"
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
            cliente.ruta += " -> gomeria"
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
        self._registrar_fila("Inicializacion")
        self._limpiar_valores_evento()

        while True:
            nombre, t, servidor = self._proximo_evento()
            if t == float("inf"):
                break
            self.reloj = t
            self.n_evento += 1

            if nombre == "Llegada cliente":
                self._evento_llegada()
            elif nombre.startswith("Fin carga"):
                self._fin_carga(servidor)               # type: ignore[arg-type]
            elif "Gomeria" in nombre:
                self._fin_gomeria(servidor)             # type: ignore[arg-type]
            elif "Accesorios" in nombre:
                self._fin_accesorios(servidor)          # type: ignore[arg-type]

            self._actualizar_maximos()
            self._registrar_fila(nombre)
            self._limpiar_valores_evento()

    def _registrar_fila(self, evento: str):
        fila = {
            "N": self.n_evento,
            "Evento": evento,
            "Reloj (s)": round(self.reloj, 2),

            "RND1 lleg.": self.rnd_lleg1,
            "RND2 lleg.": self.rnd_lleg2,
            "T entre lleg. (s)": self.t_lleg,
            "Prox. llegada": (round(self.prox_llegada, 2)
                              if self.prox_llegada != float("inf")
                              else "---"),

            "RND tipo": self.ult_rnd_tipo,
            "RND subruta": self.ult_rnd_sub,
            "RND post-carga": self.ult_rnd_post,

            "RND carga": self.ult_rnd_carga,
            "T carga (s)": self.ult_t_carga,

            "RND gomeria": self.ult_rnd_gom,
            "T gomeria (s)": self.ult_t_gom,

            "RND acces.": self.ult_rnd_acc,
            "T acces. (s)": self.ult_t_acc,
        }

        for s in self.surtidores + self.gomerias + self.accesorios_list:
            fila[s.nombre] = self._estado_servidor(s)

        fila["Cola surt."] = len(self.cola_surtidor)
        fila["Cola gom."] = len(self.cola_gomeria)
        fila["Cola acces."] = len(self.cola_accesorios)

        fila["Max cola surt."] = self.stats.cola_max_surtidor
        fila["Max cola gom."] = self.stats.cola_max_gomeria
        fila["Max cola acces."] = self.stats.cola_max_accesorios
        fila["Max T sistema (s)"] = round(self.stats.tiempo_max_sistema, 2)

        for cid in sorted(self.clientes.keys()):
            fila[f"C{cid}"] = self.clientes[cid].estado

        self.filas.append(fila)

    def _estado_servidor(self, s: Servidor) -> str:
        if not s.ocupado or s.cliente is None:
            return "Libre"
        return f"C{s.cliente.id} (fin {round(s.fin, 1)})"


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"
    return str(v)


def main():
    p = argparse.ArgumentParser(
        description="Simulacion estacion de servicio (UTN - Simulacion)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-n", "--clientes", type=int, default=500)
    p.add_argument("-s", "--semilla", type=int, default=None)
    p.add_argument("--desde", type=int, default=0)
    p.add_argument("--cantidad", type=int, default=None)
    p.add_argument("-o", "--salida", type=str, default="estacion_servicio.html")
    p.add_argument("--abrir", action="store_true")
    p.add_argument("--surtidores", type=int, default=3)
    p.add_argument("--gomerias", type=int, default=2)
    p.add_argument("--accesorios", type=int, default=1)
    p.add_argument("--lleg-media", type=float, default=24.0)
    p.add_argument("--lleg-desv", type=float, default=23.0)
    p.add_argument("--carga-a", type=float, default=45.0, help="Carga: min (seg)")
    p.add_argument("--carga-b", type=float, default=55.0, help="Carga: max (seg)")
    p.add_argument("--gom-a", type=float, default=10.0, help="Gomeria: min (min)")
    p.add_argument("--gom-b", type=float, default=26.0, help="Gomeria: max (min)")
    p.add_argument("--acc-a", type=float, default=1.0, help="Accesorios: min (min)")
    p.add_argument("--acc-b", type=float, default=5.0, help="Accesorios: max (min)")
    p.add_argument("--p-carga", type=float, default=0.80)
    p.add_argument("--p-no-carga-acc", type=float, default=0.40)
    p.add_argument("--p-post-carga-acc", type=float, default=0.30)
    p.add_argument("--p-post-carga-gom", type=float, default=0.20)

    args = p.parse_args()

    cfg = Config(
        n_clientes=args.clientes, semilla=args.semilla,
        n_surtidores=args.surtidores, n_gomerias=args.gomerias,
        n_accesorios=args.accesorios,
        lleg_media=args.lleg_media, lleg_desv=args.lleg_desv,
        carga_a=args.carga_a, carga_b=args.carga_b,
        gom_a=args.gom_a, gom_b=args.gom_b,
        acc_a=args.acc_a, acc_b=args.acc_b,
        p_carga=args.p_carga, p_no_carga_acc=args.p_no_carga_acc,
        p_post_carga_acc=args.p_post_carga_acc,
        p_post_carga_gom=args.p_post_carga_gom,
        desde=args.desde, cantidad=args.cantidad,
    )

    sim = Simulacion(cfg)
    sim.ejecutar()

    total = len(sim.filas)
    print(f"Clientes arribados : {sim.arribados}")
    print(f"Eventos totales    : {total - 1}")
    print(f"Cola max surt.     : {sim.stats.cola_max_surtidor}")
    print(f"Cola max gomeria   : {sim.stats.cola_max_gomeria}")
    print(f"Cola max acces.    : {sim.stats.cola_max_accesorios}")
    print(f"T max en sistema   : {sim.stats.tiempo_max_sistema:.2f} s "
          f"({sim.stats.tiempo_max_sistema/60:.2f} min) "
          f"(cliente C{sim.stats.id_cliente_max_tiempo})")


if __name__ == "__main__":
    main()
