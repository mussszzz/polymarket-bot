# Bot de Trading para Polymarket
### Estrategia: "Bonos de Alta Probabilidad"

---

## ¿Qué hace este bot?

El bot analiza continuamente los mercados activos de [Polymarket](https://polymarket.com) buscando contratos YES o NO que coticen entre **$0.88 y $0.96**. En esa franja de precios, el mercado ya está descontando una probabilidad de éxito muy alta (88–96%), pero todavía queda un retorno del **4–14%** si el evento se resuelve a tu favor.

**Ejemplo:**
- Contrato YES cotiza a $0.92
- Compras $2.50 → obtienes 2.717 contratos
- Si resuelve YES → cobras $2.717 (ganancia de $0.217 = +8.7%)
- Retorno esperado = `(1 - 0.92) / 0.92 = 8.70%`

---

## Instalación

### 1. Requisitos previos
- Python 3.11 o superior
- pip

### 2. Clonar el repositorio

```bash
git clone <url-del-repo>
cd personal
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

Edita `.env` con tus preferencias:

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `PRECIO_MIN` | Precio mínimo del filtro | `0.88` |
| `PRECIO_MAX` | Precio máximo del filtro | `0.96` |
| `LIMITE_POR_POSICION` | Máximo USD por operación | `2.50` |
| `INTERVALO_MINUTOS` | Minutos entre ciclos | `30` |
| `MODO_SIMULACION` | `true` = no opera con dinero real | `true` |
| `LOG_CSV` | Nombre del archivo de log | `operaciones.csv` |

---

## Uso

### Modo simulación (recomendado para empezar)

```bash
python polymarket_bot.py
```

Con `MODO_SIMULACION=true` el bot solo analiza y muestra las oportunidades — no envía ninguna orden al exchange.

### Ver el ranking una sola vez (sin bucle)

Puedes ejecutar un ciclo único editando temporalmente `main()` o lanzando directamente:

```python
# En Python interactivo:
from polymarket_bot import ejecutar_ciclo
ejecutar_ciclo()
```

### Revisar el historial de oportunidades

```bash
# Ver las últimas 20 entradas del CSV
tail -20 operaciones.csv

# Abrir en Excel / LibreOffice Calc
# El archivo tiene cabecera y está separado por comas
```

---

## Estructura del proyecto

```
personal/
├── polymarket_bot.py       # Bot principal
├── .env.example            # Plantilla de configuración
├── .env                    # Tu configuración (no subir a git)
├── requirements.txt        # Dependencias Python
├── operaciones.csv         # Log automático (se crea al ejecutar)
└── bot.log                 # Log de texto del bot
```

---

## Salida del bot

Cada ciclo imprime un ranking como este:

```
================================================================================
  RANKING DE OPORTUNIDADES — 2025-01-15 14:30 UTC
  Filtro: $0.88–$0.96 | Límite por posición: $2.50
  Modo: SIMULACIÓN
================================================================================
   Pregunta                                          Outcome  Precio $  Retorno %  Ganancia $ pot.  Vence
0  Will Candidate X win the election?                YES       0.8812    13.48      0.2988           2025-01-20
1  Will the Fed cut rates in January?                YES       0.9100     9.89      0.2475           2025-01-29
2  Will BTC close above $100k on Jan 31?             NO        0.9201     8.68      0.2171           2025-01-31
================================================================================
  Total oportunidades encontradas: 7
================================================================================
```

---

## Consideraciones de riesgo

> **Este bot es una herramienta de análisis. Operar en mercados de predicción conlleva riesgo de pérdida total del capital invertido.**

- Los mercados con precio alto pueden resolverse en contra (eventos de baja probabilidad ocurren).
- Diversifica entre múltiples posiciones pequeñas para reducir el riesgo de concentración.
- Revisa siempre la fecha de vencimiento (`end_date`) antes de entrar.
- Empieza siempre en modo simulación hasta entender el comportamiento del bot.

---

## APIs utilizadas

- **Gamma API** (`gamma-api.polymarket.com`) — metadatos de mercados activos
- **CLOB API** (`clob.polymarket.com`) — order books y precios en tiempo real

Ambas son APIs públicas que no requieren autenticación para consultas de lectura.

---

## Próximos pasos (para operar con dinero real)

1. Crea una wallet en Polymarket (requiere MetaMask u otra wallet Web3)
2. Obtén tu clave privada y configúrala de forma segura
3. Integra `py-clob-client` para enviar órdenes reales
4. Cambia `MODO_SIMULACION=false` en `.env`

---

## Licencia

MIT — úsalo, modifícalo y distribúyelo libremente.
