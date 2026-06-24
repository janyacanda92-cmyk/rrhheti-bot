"""
Bot de Telegram para buscar expedientes laborales.

Comandos disponibles:
  /buscar <nombre o carnet>      -> busca un expediente
  /agregar                       -> agrega un expediente nuevo (te hace preguntas paso a paso)
  /baja <nombre o carnet>        -> marca un expediente como "Baja"
  /lista                         -> muestra cuántos expedientes hay y un resumen
  /ayuda                         -> muestra esta ayuda

Autor: generado con Claude
"""

import logging
import os
import sqlite3
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "expedientes.db")

# ---------- Base de datos ----------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS expedientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            carnet TEXT,
            estado TEXT NOT NULL DEFAULT 'Activo',
            departamento TEXT,
            ubicacion TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def buscar_expediente(termino):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    like = f"%{termino}%"
    cur.execute(
        """
        SELECT nombre, carnet, estado, departamento, ubicacion
        FROM expedientes
        WHERE nombre LIKE ? OR carnet LIKE ?
        """,
        (like, like),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def agregar_expediente(nombre, carnet, estado, departamento, ubicacion):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO expedientes (nombre, carnet, estado, departamento, ubicacion)
        VALUES (?, ?, ?, ?, ?)
        """,
        (nombre, carnet, estado, departamento, ubicacion),
    )
    conn.commit()
    conn.close()


def marcar_baja(termino):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    like = f"%{termino}%"
    cur.execute(
        "UPDATE expedientes SET estado = 'Baja' WHERE nombre LIKE ? OR carnet LIKE ?",
        (like, like),
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected


def contar_expedientes():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT estado, COUNT(*) FROM expedientes GROUP BY estado")
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------- Comandos ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola, soy tu asistente de expedientes laborales.\n\n"
        "Usa /buscar <nombre o carnet> para encontrar un expediente.\n"
        "Usa /agregar para registrar uno nuevo.\n"
        "Usa /ayuda para ver todos los comandos."
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandos disponibles:\n\n"
        "/buscar <nombre o carnet> - busca un expediente\n"
        "/agregar - agrega un expediente nuevo (paso a paso)\n"
        "/baja <nombre o carnet> - marca un expediente como Baja\n"
        "/lista - muestra un resumen de cuántos expedientes hay\n"
        "/cancelar - cancela el proceso de agregar en curso"
    )


async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Escribe así: /buscar Ali  (o /buscar 12345678)")
        return

    termino = " ".join(context.args)
    resultados = buscar_expediente(termino)

    if not resultados:
        await update.message.reply_text(f"No encontré ningún expediente que coincida con '{termino}'.")
        return

    mensajes = []
    for nombre, carnet, estado, departamento, ubicacion in resultados:
        mensajes.append(
            f"👤 {nombre}\n"
            f"🪪 Carnet: {carnet or '—'}\n"
            f"📌 Estado: {estado}\n"
            f"🏢 Departamento: {departamento or '—'}\n"
            f"📍 Ubicación: {ubicacion}"
        )
    await update.message.reply_text("\n\n".join(mensajes))


async def baja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Escribe así: /baja Ali  (o /baja 12345678)")
        return
    termino = " ".join(context.args)
    afectados = marcar_baja(termino)
    if afectados:
        await update.message.reply_text(f"Se marcó como Baja: {afectados} expediente(s).")
    else:
        await update.message.reply_text(f"No encontré ningún expediente que coincida con '{termino}'.")


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = contar_expedientes()
    if not rows:
        await update.message.reply_text("Todavía no hay expedientes registrados.")
        return
    texto = "Resumen de expedientes:\n\n"
    for estado, cantidad in rows:
        texto += f"{estado}: {cantidad}\n"
    await update.message.reply_text(texto)


# ---------- Flujo de /agregar (conversación paso a paso) ----------

NOMBRE, CARNET, ESTADO, DEPARTAMENTO, UBICACION = range(5)


async def agregar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Vamos a agregar un expediente nuevo.\n\n¿Cuál es el nombre completo?")
    return NOMBRE


async def agregar_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nombre"] = update.message.text
    await update.message.reply_text("¿Cuál es el carnet de identidad? (o escribe - si no aplica)")
    return CARNET


async def agregar_carnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["carnet"] = update.message.text
    await update.message.reply_text("¿Está Activo o de Baja?")
    return ESTADO


async def agregar_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["estado"] = update.message.text
    await update.message.reply_text("¿A qué departamento o dirección pertenece (o pertenecía)?")
    return DEPARTAMENTO


async def agregar_departamento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["departamento"] = update.message.text
    await update.message.reply_text("¿Cuál es la ubicación física del expediente? (ej. ABT-12, Estante 3)")
    return UBICACION


async def agregar_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ubicacion"] = update.message.text
    d = context.user_data
    agregar_expediente(
        d["nombre"], d["carnet"], d["estado"], d["departamento"], d["ubicacion"]
    )
    await update.message.reply_text(
        f"✅ Expediente guardado:\n\n"
        f"👤 {d['nombre']}\n"
        f"🪪 Carnet: {d['carnet']}\n"
        f"📌 Estado: {d['estado']}\n"
        f"🏢 Departamento: {d['departamento']}\n"
        f"📍 Ubicación: {d['ubicacion']}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Proceso cancelado.")
    return ConversationHandler.END


# ---------- Main ----------

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Falta la variable de entorno TELEGRAM_BOT_TOKEN. "
            "Configúrala con el token que te dio @BotFather."
        )

    init_db()

    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("agregar", agregar_start)],
        states={
            NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, agregar_nombre)],
            CARNET: [MessageHandler(filters.TEXT & ~filters.COMMAND, agregar_carnet)],
            ESTADO: [MessageHandler(filters.TEXT & ~filters.COMMAND, agregar_estado)],
            DEPARTAMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, agregar_departamento)],
            UBICACION: [MessageHandler(filters.TEXT & ~filters.COMMAND, agregar_ubicacion)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("baja", baja))
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(conv_handler)

    logger.info("Bot iniciado. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()
