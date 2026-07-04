# 🩻 Agente diario de radiología por Telegram

Cada día a las **7:00 am (Ciudad de México)** este agente:

1. Busca en **PubMed** los artículos indexados en las últimas 24 h en las
   principales revistas de radiología (Radiology, AJR, European Radiology,
   RadioGraphics, JACR, AJNR, JVIR, etc. — lista editable en
   `daily_radiology.py`, variable `JOURNALS`).
2. Genera un **mini resumen en español** de cada artículo con Claude
   (modelo Haiku). Si no configuras la clave de Anthropic, envía en su
   lugar el inicio del abstract original en inglés.
3. Envía el digest a tu **Telegram** con enlaces a PubMed y DOI.

Corre automáticamente con GitHub Actions: no necesita servidor ni que tu
computadora esté encendida. PubMed es público, no requiere cuenta.

## Configuración (una sola vez)

### 1. Crea tu bot de Telegram

1. En Telegram, abre [@BotFather](https://t.me/BotFather) y envía `/newbot`.
2. Dale un nombre y un usuario (p. ej. `radiologia_diaria_bot`).
3. BotFather te dará un **token** tipo `123456789:AAF...`. Guárdalo.

### 2. Obtén tu chat ID

1. Abre un chat con tu nuevo bot y envíale cualquier mensaje (p. ej. "hola").
2. Visita en el navegador:
   `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
3. Busca `"chat":{"id":123456789,...}` — ese número es tu **chat ID**.

### 3. Agrega los secretos en GitHub

En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**:

| Secreto | Valor | ¿Obligatorio? |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | El token de BotFather | Sí |
| `TELEGRAM_CHAT_ID` | Tu chat ID | Sí |
| `ANTHROPIC_API_KEY` | Clave de [console.anthropic.com](https://console.anthropic.com) | No (sin ella, se usa el abstract en inglés) |

### 4. Pruébalo

En la pestaña **Actions → "Digest diario de radiología" → Run workflow**
puedes lanzarlo manualmente y verificar que llega el mensaje.

## Ajustes opcionales

- **Hora de envío**: edita el `cron` en `.github/workflows/daily-radiology.yml`
  (está en UTC; CDMX = UTC-6).
- **Revistas**: edita la lista `JOURNALS` en `daily_radiology.py`.
- **Ventana de búsqueda**: variable de entorno `LOOKBACK_DAYS` (default 1).
- **Máximo de artículos por día**: `MAX_ARTICLES` (default 25).

## Prueba local

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export ANTHROPIC_API_KEY="..."   # opcional
python3 radiology_agent/daily_radiology.py
```
