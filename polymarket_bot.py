"""
Polymarket Trading Bot
Estrategia: "Bonos de Alta Probabilidad"

Filtra mercados donde YES/NO cotiza entre $0.88 y $0.96 para capturar
retornos del 4-14% con alta probabilidad implícita.

Modos de operación:
  MODO_SIMULACION=true  → solo analiza y registra, no envía órdenes
  MODO_SIMULACION=false → envía órdenes reales vía py-clob-client
"""

import os
import csv
import time
import logging
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

CLOB_API_BASE   = "https://clob.polymarket.com"
GAMMA_API_BASE  = "https://gamma-api.polymarket.com"

PRECIO_MIN          = float(os.getenv("PRECIO_MIN", 0.88))
PRECIO_MAX          = float(os.getenv("PRECIO_MAX", 0.96))
LIMITE_POR_POSICION = float(os.getenv("LIMITE_POR_POSICION", 2.50))
INTERVALO_MINUTOS   = int(os.getenv("INTERVALO_MINUTOS", 30))
MODO_SIMULACION     = os.getenv("MODO_SIMULACION", "true").lower() == "true"
LOG_CSV             = os.getenv("LOG_CSV", "operaciones.csv")

# Credenciales para modo real
WALLET_PRIVATE_KEY  = os.getenv("WALLET_PRIVATE_KEY", "")
WALLET_ADDRESS      = os.getenv("WALLET_ADDRESS", "")
# 0 = EOA (MetaMask/hardware), 1 = Email/Magic wallet
SIGNATURE_TYPE      = int(os.getenv("SIGNATURE_TYPE", 0))
CHAIN_ID            = int(os.getenv("CHAIN_ID", 137))   # 137 = Polygon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cliente CLOB (modo real)
# ---------------------------------------------------------------------------

_clob_client = None  # inicializado bajo demanda


def obtener_cliente_clob():
    """
    Devuelve el ClobClient autenticado.
    Se inicializa una sola vez y se reutiliza en todos los ciclos.
    """
    global _clob_client
    if _clob_client is not None:
        return _clob_client

    if not WALLET_PRIVATE_KEY or not WALLET_ADDRESS:
        raise EnvironmentError(
            "WALLET_PRIVATE_KEY y WALLET_ADDRESS deben estar definidos en .env "
            "para operar en modo real."
        )

    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        raise ImportError(
            "py-clob-client no está instalado. "
            "Ejecuta: pip install py-clob-client"
        )

    log.info("Inicializando ClobClient (chain_id=%d, sig_type=%d)…", CHAIN_ID, SIGNATURE_TYPE)
    cliente = ClobClient(
        CLOB_API_BASE,
        key=WALLET_PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=SIGNATURE_TYPE,
        funder=WALLET_ADDRESS,
    )

    creds = cliente.create_or_derive_api_creds()
    cliente.set_api_creds(creds)
    log.info("ClobClient autenticado. API key: %s…", str(creds.api_key)[:8])

    _clob_client = cliente
    return _clob_client


def obtener_balance() -> dict:
    """Consulta el balance USDC y el allowance disponible para operar."""
    try:
        cliente = obtener_cliente_clob()
        info = cliente.get_balance_allowance()
        return info
    except Exception as e:
        log.warning("No se pudo obtener balance: %s", e)
        return {}


# ---------------------------------------------------------------------------
# API helpers (lectura pública)
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})


def _get(url: str, params: dict = None, timeout: int = 15) -> dict | list | None:
    try:
        resp = SESSION.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        log.warning("HTTP error %s para %s", e, url)
    except requests.exceptions.RequestException as e:
        log.warning("Error de red: %s", e)
    return None


def obtener_mercados_activos(limite: int = 500) -> list[dict]:
    """Obtiene mercados activos desde la Gamma API (metadatos enriquecidos)."""
    mercados = []
    offset = 0
    batch = 100

    while len(mercados) < limite:
        data = _get(
            f"{GAMMA_API_BASE}/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": batch,
                "offset": offset,
            },
        )
        if not data:
            break
        items = data.get("markets", data.get("data", [])) if isinstance(data, dict) else data
        if not items:
            break
        mercados.extend(items)
        if len(items) < batch:
            break
        offset += batch

    log.info("Mercados activos obtenidos: %d", len(mercados))
    return mercados


def obtener_orderbook(token_id: str) -> dict | None:
    """Obtiene el order book de un token (YES o NO)."""
    return _get(f"{CLOB_API_BASE}/book", params={"token_id": token_id})


def mejor_precio_ask(orderbook: dict) -> float | None:
    """Devuelve el mejor precio de venta (ask) disponible en el order book."""
    asks = orderbook.get("asks", []) if orderbook else []
    if not asks:
        return None
    try:
        return min(float(a["price"]) for a in asks)
    except (KeyError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Lógica de filtrado y análisis
# ---------------------------------------------------------------------------

def extraer_token_ids(mercado: dict) -> dict:
    """Extrae los token IDs de YES y NO de un mercado."""
    tokens = {}
    for token in mercado.get("tokens", []):
        outcome = token.get("outcome", "").upper()
        if outcome in ("YES", "NO"):
            tokens[outcome] = token.get("token_id", "")
    return tokens


def calcular_retorno_esperado(precio: float) -> float:
    """Retorno esperado = (1 - precio) / precio."""
    if precio <= 0:
        return 0.0
    return (1.0 - precio) / precio


def analizar_mercado(mercado: dict) -> list[dict]:
    """
    Analiza un mercado y devuelve oportunidades que cumplen el filtro de precio.
    Puede devolver 0, 1 o 2 entradas (una por token YES/NO si aplica).
    """
    oportunidades = []
    token_ids = extraer_token_ids(mercado)

    for outcome, token_id in token_ids.items():
        if not token_id:
            continue

        ob = obtener_orderbook(token_id)
        precio = mejor_precio_ask(ob)

        if precio is None:
            continue

        if PRECIO_MIN <= precio <= PRECIO_MAX:
            retorno = calcular_retorno_esperado(precio)
            contratos = round(LIMITE_POR_POSICION / precio, 4)
            oportunidades.append(
                {
                    "mercado_id":        mercado.get("id", ""),
                    "slug":              mercado.get("slug", ""),
                    "pregunta":          mercado.get("question", mercado.get("title", "")),
                    "outcome":           outcome,
                    "token_id":          token_id,
                    "precio":            round(precio, 4),
                    "retorno_esperado":  round(retorno * 100, 2),
                    "limite_posicion":   LIMITE_POR_POSICION,
                    "contratos":         contratos,
                    "ganancia_potencial": round(contratos * (1 - precio), 4),
                    "end_date":          mercado.get("end_date_iso", mercado.get("endDate", "")),
                    "timestamp":         datetime.utcnow().isoformat(),
                }
            )

    return oportunidades


# ---------------------------------------------------------------------------
# Ranking y presentación
# ---------------------------------------------------------------------------

def construir_ranking(mercados: list[dict]) -> pd.DataFrame:
    """Analiza todos los mercados y construye el ranking de oportunidades."""
    oportunidades = []
    total = len(mercados)

    for idx, mercado in enumerate(mercados, start=1):
        if idx % 50 == 0:
            log.info("Procesando mercado %d/%d…", idx, total)
        oportunidades.extend(analizar_mercado(mercado))

    if not oportunidades:
        return pd.DataFrame()

    df = pd.DataFrame(oportunidades)
    df.sort_values("retorno_esperado", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def mostrar_ranking(df: pd.DataFrame, top_n: int = 20) -> None:
    """Imprime el ranking de mejores oportunidades en consola."""
    if df.empty:
        log.info("No se encontraron oportunidades en el rango $%.2f–$%.2f", PRECIO_MIN, PRECIO_MAX)
        return

    print("\n" + "=" * 90)
    print(f"  RANKING DE OPORTUNIDADES — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Filtro: ${PRECIO_MIN}–${PRECIO_MAX}  |  Límite por posición: ${LIMITE_POR_POSICION}")
    print(f"  Modo: {'SIMULACIÓN' if MODO_SIMULACION else '*** REAL ***'}")
    print("=" * 90)

    cols = ["pregunta", "outcome", "precio", "retorno_esperado", "ganancia_potencial", "end_date"]
    display = df[cols].head(top_n).copy()
    display.columns = ["Pregunta", "Outcome", "Precio $", "Retorno %", "Ganancia $ pot.", "Vence"]
    display["Pregunta"] = display["Pregunta"].str[:55]

    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.width", 130)
    print(display.to_string(index=True))
    print("=" * 90)
    print(f"  Total oportunidades encontradas: {len(df)}")
    print("=" * 90 + "\n")


# ---------------------------------------------------------------------------
# Log CSV de operaciones
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "timestamp", "modo", "mercado_id", "slug", "pregunta", "outcome",
    "token_id", "precio", "retorno_esperado", "limite_posicion",
    "contratos", "ganancia_potencial", "end_date", "order_id", "order_status",
]


def guardar_en_csv(df: pd.DataFrame, extras: dict = None) -> None:
    """Guarda las oportunidades del ciclo actual en el CSV de log."""
    if df.empty:
        return

    archivo_existe = os.path.isfile(LOG_CSV)
    df_log = df.copy()
    df_log["modo"]         = "SIMULACION" if MODO_SIMULACION else "REAL"
    df_log["order_id"]     = extras.get("order_id", "") if extras else ""
    df_log["order_status"] = extras.get("order_status", "") if extras else ""

    with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not archivo_existe:
            writer.writeheader()
        for _, fila in df_log.iterrows():
            writer.writerow(fila.to_dict())

    log.info("Log actualizado en %s (%d filas nuevas)", LOG_CSV, len(df_log))


# ---------------------------------------------------------------------------
# Ejecución de órdenes reales
# ---------------------------------------------------------------------------

def colocar_orden_limite(oportunidad: dict) -> dict:
    """
    Envía una orden límite de compra (BUY) al CLOB de Polymarket.

    Usa GTC (Good-Till-Cancelled): la orden queda activa hasta que se
    ejecute o se cancele manualmente.

    Retorna el response de la API o un dict con el error.
    """
    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
    except ImportError:
        raise ImportError("py-clob-client no instalado. Ejecuta: pip install py-clob-client")

    cliente = obtener_cliente_clob()

    order_args = OrderArgs(
        token_id=oportunidad["token_id"],
        price=oportunidad["precio"],
        size=oportunidad["contratos"],
        side=BUY,
    )

    log.info(
        "[REAL] Enviando orden: COMPRA %s %s @ $%.4f (%.4f contratos, $%.2f total)…",
        oportunidad["outcome"],
        oportunidad["pregunta"][:45],
        oportunidad["precio"],
        oportunidad["contratos"],
        LIMITE_POR_POSICION,
    )

    signed  = cliente.create_order(order_args)
    resp    = cliente.post_order(signed, OrderType.GTC)

    order_id     = resp.get("orderID", resp.get("id", ""))
    order_status = resp.get("status", "enviada")
    log.info("[REAL] Orden confirmada → ID: %s | Status: %s", order_id, order_status)

    return {"order_id": order_id, "order_status": order_status, "raw": resp}


def procesar_oportunidades_reales(df: pd.DataFrame) -> None:
    """
    En modo real, comprueba el balance disponible y envía órdenes
    para las 3 mejores oportunidades del ciclo.

    Cada orden respeta el LIMITE_POR_POSICION definido en .env.
    """
    if df.empty:
        return

    balance_info = obtener_balance()
    balance_usdc = float(balance_info.get("balance", 0))
    log.info("Balance USDC disponible: $%.4f", balance_usdc)

    if balance_usdc < LIMITE_POR_POSICION:
        log.warning(
            "Balance insuficiente ($%.4f) para colocar una posición de $%.2f. "
            "Ciclo saltado.",
            balance_usdc,
            LIMITE_POR_POSICION,
        )
        return

    top = df.head(3)
    gastado = 0.0

    for _, fila in top.iterrows():
        if gastado + LIMITE_POR_POSICION > balance_usdc:
            log.warning("Balance insuficiente para la siguiente orden. Deteniendo ciclo.")
            break

        try:
            resultado = colocar_orden_limite(fila.to_dict())
            guardar_en_csv(
                pd.DataFrame([fila]),
                extras={
                    "order_id":     resultado["order_id"],
                    "order_status": resultado["order_status"],
                },
            )
            gastado += LIMITE_POR_POSICION
        except Exception as e:
            log.error("Error al colocar orden para %s: %s", fila.get("pregunta", "")[:45], e)


# ---------------------------------------------------------------------------
# Simulación de orden
# ---------------------------------------------------------------------------

def simular_orden(oportunidad: dict) -> None:
    """Registra una orden simulada sin enviarla al exchange."""
    log.info(
        "[SIM] COMPRA %s | %s @ $%.4f | Contratos: %.4f | Ganancia pot.: $%.4f",
        oportunidad["outcome"],
        oportunidad["pregunta"][:50],
        oportunidad["precio"],
        oportunidad["contratos"],
        oportunidad["ganancia_potencial"],
    )


# ---------------------------------------------------------------------------
# Ciclo principal
# ---------------------------------------------------------------------------

def ejecutar_ciclo() -> None:
    """Un ciclo completo: obtener mercados → analizar → ranking → log → órdenes."""
    log.info("=== Iniciando ciclo de análisis ===")
    mercados = obtener_mercados_activos()

    if not mercados:
        log.warning("No se pudieron obtener mercados. Reintentando en el próximo ciclo.")
        return

    df = construir_ranking(mercados)
    mostrar_ranking(df)

    if MODO_SIMULACION:
        guardar_en_csv(df)
        if not df.empty:
            log.info("Modo simulación — registrando las 3 mejores oportunidades:")
            for _, fila in df.head(3).iterrows():
                simular_orden(fila.to_dict())
    else:
        procesar_oportunidades_reales(df)

    log.info("=== Ciclo finalizado. Próximo ciclo en %d minutos ===", INTERVALO_MINUTOS)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Bot Polymarket iniciado.")
    log.info(
        "Config: rango $%.2f–$%.2f | límite $%.2f/posición | cada %d min | modo: %s",
        PRECIO_MIN,
        PRECIO_MAX,
        LIMITE_POR_POSICION,
        INTERVALO_MINUTOS,
        "SIMULACIÓN" if MODO_SIMULACION else "*** REAL — DINERO REAL ***",
    )

    if not MODO_SIMULACION:
        # Validar credenciales y mostrar balance antes de operar
        try:
            info = obtener_balance()
            log.info(
                "Wallet conectada. Balance: $%.4f USDC | Allowance: $%.4f",
                float(info.get("balance", 0)),
                float(info.get("allowance", 0)),
            )
        except Exception as e:
            log.error("No se pudo conectar la wallet: %s", e)
            log.error("Verifica WALLET_PRIVATE_KEY y WALLET_ADDRESS en .env")
            return

    while True:
        try:
            ejecutar_ciclo()
        except KeyboardInterrupt:
            log.info("Bot detenido manualmente.")
            break
        except Exception as e:
            log.error("Error inesperado en el ciclo: %s", e, exc_info=True)

        time.sleep(INTERVALO_MINUTOS * 60)


if __name__ == "__main__":
    main()
