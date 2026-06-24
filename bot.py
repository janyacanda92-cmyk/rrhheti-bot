"""
Bot de Telegram para buscar expedientes laborales.

Sistema de acceso:
  - Solo el administrador (AUTHORIZED_USER_ID) puede usar el bot libremente.
  - Cualquier otra persona que escriba al bot por primera vez generará una
    solicitud de acceso que se le envía al administrador con botones de
    Aprobar / Rechazar.
  - Los usuarios aprobados quedan guardados en la base de datos y pueden
    usar el bot normalmente sin tocar el código ni redesplegar nada.

Comandos disponibles (para usuarios autorizados):
  /buscar <nombre o carnet>      -> busca un expediente
  /agregar                       -> agrega un expediente nuevo (paso a paso)
  /baja <nombre o carnet>        -> marca un expediente como "Baja"
  /lista                         -> muestra cuántos expedientes hay
  /usuarios                      -> (solo admin) lista usuarios aprobados
  /revocar <id>                  -> (solo admin) revoca el acceso a un usuario
  /ayuda                         -> muestra esta ayuda

Autor: generado con Claude
"""

import logging
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "expedientes.db")

# ID de Telegram del administrador (tu cuenta). Siempre tiene acceso total.
ADMIN_USER_ID = 1186207945


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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios_autorizados (
            user_id INTEGER PRIMARY KEY,
            nombre TEXT,
            username TEXT,
            rol TEXT NOT NULL DEFAULT 'editor'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS solicitudes_pendientes (
            user_id INTEGER PRIMARY KEY,
            nombre TEXT,
            username TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def es_admin(user_id):
    return user_id == ADMIN_USER_ID


def esta_autorizado(user_id):
    if es_admin(user_id):
        return True
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM usuarios_autorizados WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def obtener_rol(user_id):
    """Devuelve 'admin', 'editor', 'lector', o None si no tiene acceso."""
    if es_admin(user_id):
        return "admin"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT rol FROM usuarios_autorizados WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def puede_editar(user_id):
    rol = obtener_rol(user_id)
    return rol in ("admin", "editor")


def hay_solicitud_pendiente(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM solicitudes_pendientes WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def crear_solicitud(user_id, nombre, username):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO solicitudes_pendientes (user_id, nombre, username) VALUES (?, ?, ?)",
        (user_id, nombre, username),
    )
    conn.commit()
    conn.close()


def eliminar_solicitud(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM solicitudes_pendientes WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def aprobar_usuario(user_id, nombre, username, rol="editor"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO usuarios_autorizados (user_id, nombre, username, rol) VALUES (?, ?, ?, ?)",
        (user_id, nombre, username, rol),
    )
    conn.commit()
    conn.close()


def revocar_usuario(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM usuarios_autorizados WHERE user_id = ?", (user_id,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected


def listar_usuarios_autorizados():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, nombre, username, rol FROM usuarios_autorizados")
    rows = cur.fetchall()
    conn.close()
    return rows


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


def marcar_retirado(termino):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    like = f"%{termino}%"
    cur.execute(
        "UPDATE expedientes SET estado = 'Retirado' WHERE nombre LIKE ? OR carnet LIKE ?",
        (like, like),
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected


def eliminar_expediente_por_id(expediente_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM expedientes WHERE id = ?", (expediente_id,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected


def buscar_expediente_con_id(termino):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    like = f"%{termino}%"
    cur.execute(
        """
        SELECT id, nombre, carnet, estado, departamento, ubicacion
        FROM expedientes
        WHERE nombre LIKE ? OR carnet LIKE ?
        """,
        (like, like),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def contar_expedientes():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT estado, COUNT(*) FROM expedientes GROUP BY estado")
    rows = cur.fetchall()
    conn.close()
    return rows


# ---------- Control de acceso ----------

async def verificar_acceso(update: Update) -> bool:
    """
    Devuelve True si el usuario puede continuar.
    Si no tiene acceso, gestiona la solicitud (la crea o avisa que ya está pendiente)
    y devuelve False.
    """
    user = update.effective_user
    if esta_autorizado(user.id):
        return True

    if hay_solicitud_pendiente(user.id):
        await update.message.reply_text(
            "Tu solicitud de acceso ya fue enviada y está esperando aprobación."
        )
        return False

    # Crear nueva solicitud y notificar al administrador
    crear_solicitud(user.id, user.full_name, user.username or "")
    await update.message.reply_text(
        "No tienes acceso a este bot todavía. Se envió una solicitud al administrador.\n"
        "Te avisaré aquí mismo cuando sea aprobada o rechazada."
    )

    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Aprobar (Editor)", callback_data=f"aprobar:editor:{user.id}"),
            ],
            [
                InlineKeyboardButton("🔍 Aprobar (Solo lectura)", callback_data=f"aprobar:lector:{user.id}"),
            ],
            [
                InlineKeyboardButton("❌ Rechazar", callback_data=f"rechazar:-:{user.id}"),
            ],
        ]
    )
    username_txt = f"@{user.username}" if user.username else "(sin username)"
    await update.get_bot().send_message(
        chat_id=ADMIN_USER_ID,
        text=(
            "🔔 Nueva solicitud de acceso al bot:\n\n"
            f"👤 {user.full_name} {username_txt}\n"
            f"🆔 ID: {user.id}"
        ),
        reply_markup=teclado,
    )
    return False


async def manejar_aprobacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_USER_ID:
        await query.answer("Solo el administrador puede hacer esto.", show_alert=True)
        return

    accion, rol, user_id_str = query.data.split(":")
    user_id = int(user_id_str)

    if accion == "aprobar":
        # Intentamos recuperar datos guardados de la solicitud
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT nombre, username FROM solicitudes_pendientes WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        nombre, username = row if row else ("", "")

        aprobar_usuario(user_id, nombre, username, rol)
        eliminar_solicitud(user_id)
        rol_legible = "Editor (puede agregar y dar de baja)" if rol == "editor" else "Solo lectura (solo puede buscar)"
        await query.edit_message_text(f"✅ Aprobado: {nombre} (ID {user_id})\nRol: {rol_legible}")
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Tu acceso fue aprobado. Ya puedes usar el bot, escribe /start.",
        )
    else:
        eliminar_solicitud(user_id)
        await query.edit_message_text(f"❌ Rechazado: ID {user_id}")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Tu solicitud de acceso fue rechazada.",
        )


# ---------- Comandos ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    await update.message.reply_text(
        "Hola, soy tu asistente de expedientes laborales.\n\n"
        "Usa /buscar <nombre o carnet> para encontrar un expediente.\n"
        "Usa /agregar para registrar uno nuevo.\n"
        "Usa /ayuda para ver todos los comandos."
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    texto = (
        "Comandos disponibles:\n\n"
        "/buscar <nombre o carnet> - busca un expediente\n"
        "/agregar - agrega un expediente nuevo (paso a paso)\n"
        "/baja <nombre o carnet> - marca un expediente como Baja\n"
        "/retirar <nombre o carnet> - marca el expediente como Retirado (alguien se lo llevó, conserva historial)\n"
        "/eliminar <nombre o carnet> - borra el expediente para siempre (pide confirmación)\n"
        "/lista - muestra un resumen de cuántos expedientes hay\n"
        "/cancelar - cancela el proceso de agregar en curso"
    )
    if es_admin(update.effective_user.id):
        texto += (
            "\n\nComandos de administrador:\n"
            "/usuarios - lista usuarios con acceso\n"
            "/rol <id> <editor|lector> - cambia el rol de un usuario\n"
            "/revocar <id> - quita el acceso a un usuario"
        )
    await update.message.reply_text(texto)


async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
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
    if not await verificar_acceso(update):
        return
    if not puede_editar(update.effective_user.id):
        await update.message.reply_text("No tienes permiso para modificar expedientes (solo puedes buscar).")
        return
    if not context.args:
        await update.message.reply_text("Escribe así: /baja Ali  (o /baja 12345678)")
        return
    termino = " ".join(context.args)
    afectados = marcar_baja(termino)
    if afectados:
        await update.message.reply_text(f"Se marcó como Baja: {afectados} expediente(s).")
    else:
        await update.message.reply_text(f"No encontré ningún expediente que coincida con '{termino}'.")


async def retirar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    if not puede_editar(update.effective_user.id):
        await update.message.reply_text("No tienes permiso para modificar expedientes (solo puedes buscar).")
        return
    if not context.args:
        await update.message.reply_text("Escribe así: /retirar Ali  (o /retirar 12345678)")
        return
    termino = " ".join(context.args)
    afectados = marcar_retirado(termino)
    if afectados:
        await update.message.reply_text(
            f"📤 Se marcó como Retirado: {afectados} expediente(s).\n"
            "El registro se conserva en la base de datos para historial."
        )
    else:
        await update.message.reply_text(f"No encontré ningún expediente que coincida con '{termino}'.")


async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    if not puede_editar(update.effective_user.id):
        await update.message.reply_text("No tienes permiso para modificar expedientes (solo puedes buscar).")
        return
    if not context.args:
        await update.message.reply_text("Escribe así: /eliminar Ali  (o /eliminar 12345678)")
        return
    termino = " ".join(context.args)
    resultados = buscar_expediente_con_id(termino)
    if not resultados:
        await update.message.reply_text(f"No encontré ningún expediente que coincida con '{termino}'.")
        return
    if len(resultados) > 1:
        await update.message.reply_text(
            "Encontré más de un expediente con ese término. Sé más específico (usa el carnet)."
        )
        return

    expediente_id, nombre, carnet, estado, departamento, ubicacion = resultados[0]
    teclado = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🗑️ Sí, eliminar", callback_data=f"confirmar_eliminar:{expediente_id}"),
                InlineKeyboardButton("Cancelar", callback_data="cancelar_eliminar"),
            ]
        ]
    )
    await update.message.reply_text(
        f"⚠️ ¿Seguro que quieres ELIMINAR PERMANENTEMENTE este expediente?\n\n"
        f"👤 {nombre}\n🪪 Carnet: {carnet or '—'}\n📍 Ubicación: {ubicacion}\n\n"
        "Esta acción no se puede deshacer.",
        reply_markup=teclado,
    )


async def manejar_confirmacion_eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not puede_editar(query.from_user.id):
        await query.edit_message_text("No tienes permiso para hacer esto.")
        return

    if query.data == "cancelar_eliminar":
        await query.edit_message_text("Eliminación cancelada.")
        return

    expediente_id = int(query.data.split(":")[1])
    afectados = eliminar_expediente_por_id(expediente_id)
    if afectados:
        await query.edit_message_text("🗑️ Expediente eliminado permanentemente.")
    else:
        await query.edit_message_text("Ese expediente ya no existe (puede que se haya eliminado antes).")


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return
    rows = contar_expedientes()
    if not rows:
        await update.message.reply_text("Todavía no hay expedientes registrados.")
        return
    texto = "Resumen de expedientes:\n\n"
    for estado, cantidad in rows:
        texto += f"{estado}: {cantidad}\n"
    await update.message.reply_text(texto)


async def usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("Solo el administrador puede usar este comando.")
        return
    rows = listar_usuarios_autorizados()
    if not rows:
        await update.message.reply_text("No hay usuarios adicionales con acceso (solo tú).")
        return
    texto = "Usuarios con acceso:\n\n"
    for user_id, nombre, username, rol in rows:
        username_txt = f"@{username}" if username else "(sin username)"
        rol_txt = "✏️ Editor" if rol == "editor" else "🔍 Solo lectura"
        texto += f"🆔 {user_id} - {nombre} {username_txt} - {rol_txt}\n"
    await update.message.reply_text(texto)


async def cambiar_rol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("Solo el administrador puede usar este comando.")
        return
    if len(context.args) != 2 or context.args[1] not in ("editor", "lector"):
        await update.message.reply_text("Escribe así: /rol 123456789 editor   (o /rol 123456789 lector)")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ese ID no es válido.")
        return
    nuevo_rol = context.args[1]
    if not esta_autorizado(user_id) or es_admin(user_id):
        await update.message.reply_text("Ese ID no está en la lista de usuarios autorizados.")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE usuarios_autorizados SET rol = ? WHERE user_id = ?", (nuevo_rol, user_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Rol actualizado para el ID {user_id}: {nuevo_rol}")


async def revocar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("Solo el administrador puede usar este comando.")
        return
    if not context.args:
        await update.message.reply_text("Escribe así: /revocar 123456789")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ese ID no es válido.")
        return
    afectados = revocar_usuario(user_id)
    if afectados:
        await update.message.reply_text(f"Acceso revocado para el ID {user_id}.")
    else:
        await update.message.reply_text("Ese ID no estaba en la lista de usuarios autorizados.")


# ---------- Flujo de /agregar (conversación paso a paso) ----------

NOMBRE, CARNET, ESTADO, DEPARTAMENTO, UBICACION = range(5)


async def agregar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await verificar_acceso(update):
        return ConversationHandler.END
    if not puede_editar(update.effective_user.id):
        await update.message.reply_text("No tienes permiso para agregar expedientes (solo puedes buscar).")
        return ConversationHandler.END
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
    app.add_handler(CommandHandler("retirar", retirar))
    app.add_handler(CommandHandler("eliminar", eliminar))
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(CommandHandler("usuarios", usuarios))
    app.add_handler(CommandHandler("rol", cambiar_rol))
    app.add_handler(CommandHandler("revocar", revocar))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(manejar_aprobacion, pattern=r"^(aprobar|rechazar):(editor|lector|-):\d+$"))
    app.add_handler(CallbackQueryHandler(manejar_confirmacion_eliminar, pattern=r"^(confirmar_eliminar:\d+|cancelar_eliminar)$"))

    logger.info("Bot iniciado. Esperando mensajes...")
    app.run_polling()


if __name__ == "__main__":
    main()
