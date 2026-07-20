"""
Simulacion - Estacion de Servicio
UTN FRC - Materia Simulacion

Vector de estado segun modelo de colas planteado en el TP.
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    n_clientes: int = 500
    n_surtidores: int = 3
    n_gomerias: int = 2
    n_accesorios: int = 1

    lleg_media: float = 24.0
    lleg_desv: float = 23.0

    carga_a: float = 45.0
    carga_b: float = 55.0
    gom_a: float = 10.0
    gom_b: float = 26.0
    acc_a: float = 1.0
    acc_b: float = 5.0

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
    estado: str = ""
    tipo: str = ""
    inicio_espera: Optional[float] = None
    fin_atencion: Optional[float] = None
    salida: Optional[float] = None
    cargo_comb: bool = False


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
        self.filas: list[dict] = []

        # valores del evento actual para la fila
        self._ev: dict = {}

    def _limpiar_ev(self):
        self._ev = {}

    def _programar_prox_llegada(self):
        if self.arribados >= self.cfg.n_clientes:
            self.prox_llegada = float("inf")
            return
        r1, r2, t = rnd_normal(self.cfg.lleg_media, self.cfg.lleg_desv)
        t = max(0.1, t)
        self._ev["RND1 lleg."] = r1
        self._ev["RND2 lleg."] = r2
        self._ev["T entre lleg. (s)"] = t
        self.prox_llegada = self.reloj + t
        self._ev["Prox. llegada"] = round(self.prox_llegada, 2)

    def _libre(self, servidores: list[Servidor]) -> Optional[Servidor]:
        for s in servidores:
            if not s.ocupado:
                return s
        return None

    def _asignar_carga(self, cliente: Cliente):
        s = self._libre(self.surtidores)
        if s is None:
            self.cola_surtidor.append(cliente)
            cliente.estado = "En cola surtidor"
            cliente.tipo = "Carga comb."
            cliente.inicio_espera = self.reloj
            cliente.fin_atencion = None
        else:
            r, dur = rnd_uniforme(self.cfg.carga_a, self.cfg.carga_b)
            s.ocupado = True
            s.cliente = cliente
            s.fin = self.reloj + dur
            cliente.estado = f"Siendo atendido ({s.nombre})"
            cliente.tipo = "Carga comb."
            cliente.inicio_espera = None
            cliente.fin_atencion = s.fin
            self._ev["RND carga"] = r
            self._ev["T carga (s)"] = dur
            self._ev["Fin carga"] = round(s.fin, 2)

    def _asignar_gomeria(self, cliente: Cliente):
        s = self._libre(self.gomerias)
        a_seg = self.cfg.gom_a * 60
        b_seg = self.cfg.gom_b * 60
        if s is None:
            self.cola_gomeria.append(cliente)
            cliente.estado = "En cola gomeria"
            cliente.tipo = "Gomeria"
            cliente.inicio_espera = self.reloj
            cliente.fin_atencion = None
        else:
            r, dur = rnd_uniforme(a_seg, b_seg)
            s.ocupado = True
            s.cliente = cliente
            s.fin = self.reloj + dur
            cliente.estado = f"Siendo atendido ({s.nombre})"
            cliente.tipo = "Gomeria"
            cliente.inicio_espera = None
            cliente.fin_atencion = s.fin
            self._ev["RND gomeria"] = r
            self._ev["T gomeria (s)"] = dur
            self._ev["Fin gomeria"] = round(s.fin, 2)

    def _asignar_accesorios(self, cliente: Cliente):
        s = self._libre(self.accesorios_list)
        a_seg = self.cfg.acc_a * 60
        b_seg = self.cfg.acc_b * 60
        if s is None:
            self.cola_accesorios.append(cliente)
            cliente.estado = "En cola accesorios"
            cliente.tipo = "Accesorios"
            cliente.inicio_espera = self.reloj
            cliente.fin_atencion = None
        else:
            r, dur = rnd_uniforme(a_seg, b_seg)
            s.ocupado = True
            s.cliente = cliente
            s.fin = self.reloj + dur
            cliente.estado = f"Siendo atendido ({s.nombre})"
            cliente.tipo = "Accesorios"
            cliente.inicio_espera = None
            cliente.fin_atencion = s.fin
            self._ev["RND acces."] = r
            self._ev["T acces. (s)"] = dur
            self._ev["Fin acces."] = round(s.fin, 2)

    def _salida_cliente(self, cliente: Cliente):
        cliente.salida = self.reloj
        cliente.estado = "Finalizado"
        cliente.fin_atencion = None
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

        # ruteo con un solo RND y probabilidades acumuladas
        r = rnd()
        self._ev["RND servicio"] = r
        p_acc = self.cfg.p_carga + (1 - self.cfg.p_carga) * self.cfg.p_no_carga_acc

        if r < self.cfg.p_carga:
            self._ev["Tipo servicio"] = "Carga comb."
            self._ev["Cargo comb?"] = "Si"
            c.cargo_comb = True
            self._asignar_carga(c)
        elif r < p_acc:
            self._ev["Tipo servicio"] = "Compra acc."
            self._ev["Cargo comb?"] = "No"
            c.cargo_comb = False
            self._asignar_accesorios(c)
        else:
            self._ev["Tipo servicio"] = "Gomeria"
            self._ev["Cargo comb?"] = "No"
            c.cargo_comb = False
            self._asignar_gomeria(c)

        self._programar_prox_llegada()

    def _post_carga(self, cliente: Cliente):
        r = rnd()
        self._ev["RND post"] = r
        acc_hasta = self.cfg.p_post_carga_acc
        gom_hasta = acc_hasta + self.cfg.p_post_carga_gom
        if r < acc_hasta:
            self._ev["Que hace luego"] = "Compra acc."
            self._asignar_accesorios(cliente)
        elif r < gom_hasta:
            self._ev["Que hace luego"] = "Gomeria"
            self._asignar_gomeria(cliente)
        else:
            self._ev["Que hace luego"] = "Se retira"
            self._salida_cliente(cliente)

    def _fin_carga(self, servidor: Servidor):
        cliente = servidor.cliente
        servidor.ocupado = False
        servidor.cliente = None
        servidor.fin = float("inf")
        self._post_carga(cliente)
        if self.cola_surtidor:
            self._asignar_carga(self.cola_surtidor.pop(0))

    def _fin_gomeria(self, servidor: Servidor):
        cliente = servidor.cliente
        servidor.ocupado = False
        servidor.cliente = None
        servidor.fin = float("inf")
        self._salida_cliente(cliente)
        if self.cola_gomeria:
            self._asignar_gomeria(self.cola_gomeria.pop(0))

    def _fin_accesorios(self, servidor: Servidor):
        cliente = servidor.cliente
        servidor.ocupado = False
        servidor.cliente = None
        servidor.fin = float("inf")
        self._salida_cliente(cliente)
        if self.cola_accesorios:
            self._asignar_accesorios(self.cola_accesorios.pop(0))

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

    def ejecutar(self):
        self._limpiar_ev()
        self._programar_prox_llegada()
        self._registrar_fila("Inicializacion")
        self._limpiar_ev()

        while True:
            nombre, t, servidor = self._proximo_evento()
            if t == float("inf"):
                break
            self.reloj = t
            self.n_evento += 1

            if nombre == "Llegada cliente":
                self._evento_llegada()
            elif nombre.startswith("Fin carga"):
                self._fin_carga(servidor)
            elif "Gomeria" in nombre:
                self._fin_gomeria(servidor)
            elif "Accesorios" in nombre:
                self._fin_accesorios(servidor)

            self._actualizar_maximos()
            self._registrar_fila(nombre)
            self._limpiar_ev()

    def _registrar_fila(self, evento: str):
        ev = self._ev
        fila = {
            "N": self.n_evento,
            "Evento": evento,
            "Reloj": round(self.reloj, 2),
        }

        # llegada_cliente
        fila["RND1 lleg."] = ev.get("RND1 lleg.")
        fila["RND2 lleg."] = ev.get("RND2 lleg.")
        fila["T entre lleg. (s)"] = ev.get("T entre lleg. (s)")
        fila["Prox. llegada"] = ev.get("Prox. llegada",
            round(self.prox_llegada, 2) if self.prox_llegada != float("inf") else "---")

        # tipo de servicio
        fila["RND servicio"] = ev.get("RND servicio")
        fila["Tipo servicio"] = ev.get("Tipo servicio")

        # fin_carga_combustible
        fila["RND carga"] = ev.get("RND carga")
        fila["T carga (s)"] = ev.get("T carga (s)")
        fila["Fin carga"] = ev.get("Fin carga")

        # fin_atencion_venta_accesorio
        fila["RND acces."] = ev.get("RND acces.")
        fila["T acces. (s)"] = ev.get("T acces. (s)")
        fila["Fin acces."] = ev.get("Fin acces.")

        # fin_atencion_gomeria
        fila["RND gomeria"] = ev.get("RND gomeria")
        fila["T gomeria (s)"] = ev.get("T gomeria (s)")
        fila["Fin gomeria"] = ev.get("Fin gomeria")

        # evento extra / ruteo
        fila["Cargo comb?"] = ev.get("Cargo comb?")
        fila["RND post"] = ev.get("RND post")
        fila["Que hace luego"] = ev.get("Que hace luego")

        # servidores + colas
        for s in self.surtidores:
            fila[s.nombre] = self._estado_servidor(s)
        fila["Cola surt."] = len(self.cola_surtidor)

        for s in self.gomerias:
            fila[s.nombre] = self._estado_servidor(s)
        fila["Cola gom."] = len(self.cola_gomeria)

        for s in self.accesorios_list:
            fila[s.nombre] = self._estado_servidor(s)
        fila["Cola acces."] = len(self.cola_accesorios)

        # estadisticas
        fila["Max cola surt."] = self.stats.cola_max_surtidor
        fila["Max cola gom."] = self.stats.cola_max_gomeria
        fila["Max cola acces."] = self.stats.cola_max_accesorios
        fila["Max T sist. (s)"] = round(self.stats.tiempo_max_sistema, 2)

        # objetos temporales: 5 sub-columnas por cliente
        for cid in sorted(self.clientes.keys()):
            c = self.clientes[cid]
            prefix = f"C{cid}"
            fila[f"{prefix}_estado"] = c.estado
            fila[f"{prefix}_tipo"] = c.tipo
            fila[f"{prefix}_llegada"] = round(c.llegada, 2)
            fila[f"{prefix}_espera"] = (round(c.inicio_espera, 2)
                                        if c.inicio_espera is not None else "")
            fila[f"{prefix}_fin"] = (round(c.fin_atencion, 2)
                                     if c.fin_atencion is not None else "")

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
    p.add_argument("--surtidores", type=int, default=3)
    p.add_argument("--gomerias", type=int, default=2)
    p.add_argument("--accesorios", type=int, default=1)
    p.add_argument("--lleg-media", type=float, default=24.0)
    p.add_argument("--lleg-desv", type=float, default=23.0)
    p.add_argument("--carga-a", type=float, default=45.0)
    p.add_argument("--carga-b", type=float, default=55.0)
    p.add_argument("--gom-a", type=float, default=10.0)
    p.add_argument("--gom-b", type=float, default=26.0)
    p.add_argument("--acc-a", type=float, default=1.0)
    p.add_argument("--acc-b", type=float, default=5.0)
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
    print(f"Clientes arribados : {sim.arribados}")
    print(f"Eventos totales    : {len(sim.filas) - 1}")
    print(f"Cola max surt.     : {sim.stats.cola_max_surtidor}")
    print(f"Cola max gomeria   : {sim.stats.cola_max_gomeria}")
    print(f"Cola max acces.    : {sim.stats.cola_max_accesorios}")
    print(f"T max en sistema   : {sim.stats.tiempo_max_sistema:.2f} s "
          f"({sim.stats.tiempo_max_sistema/60:.2f} min) "
          f"(cliente C{sim.stats.id_cliente_max_tiempo})")


if __name__ == "__main__":
    main()
