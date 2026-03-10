# Bot de Trading para Polymarket
### Estrategia: "Bonos de Alta Probabilidad"

---

## ¿Qué hace este bot?

El bot analiza continuamente los mercados activos de [Polymarket](https://polymarket.com) buscando contratos YES o NO que coticen entre **$0.88 y $0.96**. En esa franja de precios, el mercado ya está descontando una probabilidad de éxito muy alta (88–96%), pero todavía queda un retorno del **4–14%** si el evento se resuelve a tu favor.

**Ejemplo:**
- Contrato YES cotiza a $0.92
- Compras $2.50 → obtienes 2.717 contratos
- Si resuelve YES → cobras $2.717 (ganancia de $0.217 = **+8.7%**)
- Retorno esperado = `(1 - 0.92) / 0.92 = 8.70%`

---

## Instalación

### 1. Requisitos previos
- Python 3.11 o superior
- Una wallet Ethereum/Polygon (MetaMask u otra compatible con EIP-712)
- USDC en Polygon para operar en modo real

### 2. Clonar el repositorio

```bash
git clone https://github.com/mussszzz/polymarket-bot.git
cd polymarket-bot
```

### 3. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 4. Configurar las variables de entorno

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

| Variable | Descripción | Por defecto |
|---|---|---|
| `PRECIO_MIN` | Precio mínimo del filtro | `0.88` |
| `PRECIO_MAX` | Precio máximo del filtro | `0.96` |
| `LIMITE_POR_POSICION` | Máximo USDC por operación | `2.50` |
| `INTERVALO_MINUTOS` | Minutos entre ciclos | `30` |
| `MODO_SIMULACION` | `true` = no opera con dinero real | `true` |
| `WALLET_PRIVATE_KEY` | Clave privada hex (sin `0x`) | — |
| `WALLET_ADDRESS` | Dirección pública de la wallet | — |
| `SIGNATURE_TYPE` | `0` = EOA / `1` = Magic wallet | `0` |
| `CHAIN_ID` | Red (137 = Polygon) | `137` |
| `LOG_CSV` | Nombre del archivo de log | `operaciones.csv` |

---

## Modos de uso

### Modo simulación (recomendado para empezar)

```bash
python polymarket_bot.py
```

Con `MODO_SIMULACION=true` el bot analiza mercados, muestra el ranking y registra las oportunidades en CSV, **sin enviar ninguna orden**.

---

### Modo real (dinero real en Polygon)

#### Paso 1 — Prepara tu wallet

1. Instala [MetaMask](https://metamask.io) y crea una wallet
2. Añade la red **Polygon** (chain ID 137)
3. Deposita **USDC en Polygon** (`0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`)
4. Registra tu wallet en [Polymarket.com](https://polymarket.com) al menos una vez (para activar el perfil)

#### Paso 2 — Añade las credenciales al .env

```dotenv
MODO_SIMULACION=false
WALLET_PRIVATE_KEY=tu_clave_privada_sin_0x
WALLET_ADDRESS=0xTuDireccionPublica
SIGNATURE_TYPE=0   # EOA estándar
CHAIN_ID=137
```

> ⚠️ **Seguridad**: nunca subas `.env` a git. El archivo ya está en `.gitignore`.
> Considera usar una wallet dedicada exclusivamente para el bot con el saldo
> mínimo necesario.

#### Paso 3 — Aprueba el gasto de USDC (solo EOA, una vez)

Los usuarios con wallet EOA (MetaMask, hardware wallet) deben aprobar que el
exchange de Polymarket pueda mover sus USDC. Ejecuta este script **una sola
vez** antes de operar:

```python
# approve_usdc.py  — ejecutar una sola vez
from py_clob_client.client import ClobClient
import os
from dotenv import load_dotenv

load_dotenv()
client = ClobClient(
    "https://clob.polymarket.com",
    key=os.getenv("WALLET_PRIVATE_KEY"),
    chain_id=137,
    signature_type=0,
    funder=os.getenv("WALLET_ADDRESS"),
)
client.set_api_creds(client.create_or_derive_api_creds())
resp = client.update_balance_allowance()
print("Aprobación enviada:", resp)
```

> Las wallets de email/Magic (SIGNATURE_TYPE=1) no necesitan este paso.

#### Paso 4 — Arranca el bot

```bash
python polymarket_bot.py
```

Al iniciarse en modo real, el bot muestra tu balance USDC y el allowance
disponible antes de comenzar a operar.

---

## Lógica de ejecución de órdenes

En cada ciclo el bot:

1. Construye el ranking de oportunidades
2. Consulta el **balance USDC** de la wallet
3. Itera las **3 mejores oportunidades** (por retorno esperado)
4. Para cada una, envía una **orden límite GTC** (Good-Till-Cancelled) al
   precio de ask con `size = LIMITE_POR_POSICION / precio`
5. Registra el `order_id` y `status` devuelto por Polymarket en el CSV

Las órdenes no ejecutadas permanecen activas en el libro de órdenes hasta
que el mercado se llene o tú las canceles manualmente.

---

## Estructura del proyecto

```
personal/
├── polymarket_bot.py       # Bot principal
├── .env.example            # Plantilla de configuración
├── .env                    # Tu configuración (NO subir a git)
├── requirements.txt        # Dependencias Python
├── operaciones.csv         # Log de oportunidades/órdenes (auto-generado)
└── bot.log                 # Log de texto del bot (auto-generado)
```

---

## Ejemplo de salida en consola

```
==========================================================================================
  RANKING DE OPORTUNIDADES — 2025-01-15 14:30 UTC
  Filtro: $0.88–$0.96  |  Límite por posición: $2.50
  Modo: *** REAL — DINERO REAL ***
==========================================================================================
   Pregunta                                                Outcome  Precio $  Retorno %  Ganancia $ pot.  Vence
0  Will Candidate X win the election?                     YES       0.8812    13.48      0.2988           2025-01-20
1  Will the Fed cut rates in January?                     YES       0.9100     9.89      0.2475           2025-01-29
2  Will BTC close above $100k on Jan 31?                  NO        0.9201     8.68      0.2171           2025-01-31
==========================================================================================
  Total oportunidades encontradas: 7
==========================================================================================
```

---

## Consideraciones de riesgo

> **Operar en mercados de predicción conlleva riesgo de pérdida total del capital.**

- Los eventos de baja probabilidad ocurren — un contrato al 95% puede resolverse en contra.
- Diversifica entre múltiples posiciones pequeñas.
- Revisa siempre la fecha de vencimiento (`end_date`) antes de entrar.
- Empieza siempre con `MODO_SIMULACION=true` hasta entender el comportamiento del bot.
- No dejes la clave privada en servidores compartidos.

---

## APIs utilizadas

| API | Uso |
|---|---|
| `gamma-api.polymarket.com` | Metadatos de mercados activos (pública) |
| `clob.polymarket.com` | Order books, precios y ejecución de órdenes |

---

## Licencia

MIT — úsalo, modifícalo y distribúyelo libremente.
