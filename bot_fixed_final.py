import asyncio
import logging
from datetime import datetime, date, time, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from config import BOT_TOKEN, ADMIN_ID, TIMEZONE, WORK_START_HOUR, WORK_END_HOUR
from keyboards import (
    main_menu, phone_keyboard, info_keyboard, equipment_keyboard,
    quantity_keyboard, booking_edit_keyboard, final_booking_keyboard,
    admin_booking_keyboard, admin_panel_keyboard
)
from rules import RULES_TEXT
from states import BookingStates, AdminStates
from utils import (
    now_local, allowed_date, valid_pickup_date, min_pickup_date,
    time_options, parse_date, dt_iso, fmt_iso, booking_period_valid
)

logging.basicConfig(level=logging.INFO)

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")
if not ADMIN_ID:
    raise RuntimeError("Не задан ADMIN_ID")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

STATUS_TEXT = {
    "pending": "🕐 Очікує підтвердження",
    "confirmed": "✅ Підтверджено",
    "issued": "📦 Обладнання видано",
    "returned": "✔️ Повернуто",
    "rejected": "❌ Відхилено",
    "canceled": "🚫 Скасовано користувачем",
}

def is_admin(user_id):
    return user_id == ADMIN_ID

def calendar_keyboard(prefix: str, selected_date: date | None = None):
    # Простий календар: поточний місяць + наступний. Дати показуються кнопками.
    from calendar import monthrange
    base = selected_date or now_local().date()
    months = [(base.year, base.month)]
    next_month = (base.replace(day=28) + timedelta(days=4)).replace(day=1)
    months.append((next_month.year, next_month.month))

    builder = InlineKeyboardBuilder()
    for y, m in months:
        days = monthrange(y, m)[1]
        builder.button(text=f"📅 {m:02d}.{y}", callback_data="noop")
        for d in range(1, days + 1):
            dt = date(y, m, d)
            if prefix == "pickup" and not valid_pickup_date(dt):
                continue
            if prefix == "return" and not allowed_date(dt):
                continue
            builder.button(text=f"{d:02d}", callback_data=f"{prefix}_date:{dt.isoformat()}")
        builder.adjust(1, 7)
    return builder.as_markup()

def time_keyboard(prefix: str):
    builder = InlineKeyboardBuilder()
    for t in time_options():
        builder.button(text=t.strftime("%H:%M"), callback_data=f"{prefix}_time:{t.strftime('%H:%M')}")
    builder.adjust(4)
    return builder.as_markup()

def booking_summary(data):
    lines = [
        "📋 <b>Ваше бронювання</b>",
        "",
        f"🎯 Захід: {data['event_name']}",
        f"👤 Відповідальна особа: {data['full_name']}",
        f"📞 Телефон: {data['phone']}",
        "",
        "📦 Обладнання:"
    ]
    for eid, qty in data["selected"].items():
        e = db.get_equipment_item(eid)
        lines.append(f"• {e['name']} — {qty} шт.")
    lines += [
        "",
        f"📅 Отримання: {data['pickup_text']}",
        f"📅 Повернення: {data['return_text']}",
        "",
        "Перед надсиланням заявки ознайомтеся з правилами та підтвердьте згоду."
    ]
    return "\n".join(lines)

def admin_booking_text(booking_id):
    b = db.get_booking(booking_id)
    items = db.get_booking_items(booking_id)
    lines = [
        f"🆕 <b>Нове бронювання №{booking_id}</b>",
        "",
        f"👤 {b['full_name']}",
        f"📞 {b['phone']}",
        f"🎯 Захід: {b['event_name']}",
        "",
        "📦 Обладнання:"
    ]
    for item in items:
        lines.append(f"• {item['equipment_name']} — {item['reserved_qty']} шт.")
    lines += [
        "",
        f"📅 Отримання: {fmt_iso(b['pickup_at'])}",
        f"📅 Повернення: {fmt_iso(b['return_at'])}",
        f"☑️ З правилами погоджено: {'так' if b['rules_agreed'] else 'ні'}",
        f"Статус: {STATUS_TEXT.get(b['status'], b['status'])}",
    ]
    return "\n".join(lines)

async def notify_admin_new_booking(booking_id):
    await bot.send_message(
        ADMIN_ID,
        admin_booking_text(booking_id),
        reply_markup=admin_booking_keyboard(booking_id)
    )

async def show_equipment(message: Message, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected", {})
    rows = db.get_equipment()
    await message.answer(
        "📦 <b>Оберіть обладнання</b>\nНатискайте на позиції, щоб додати їх до бронювання.",
        reply_markup=equipment_keyboard(rows, selected)
    )

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    db.upsert_user(message.from_user.id)
    await state.clear()
    await message.answer(
        "Вітаємо у боті Пластового вишкільного центру! 👋\n\n"
        "Тут можна безкоштовно подати заявку на бронювання обладнання.",
        reply_markup=main_menu(is_admin(message.from_user.id))
    )

@dp.message(F.text == "ℹ️ Інформація")
async def info(message: Message):
    await message.answer("ℹ️ Інформація", reply_markup=info_keyboard())

@dp.callback_query(F.data == "info_rules")
async def info_rules(callback: CallbackQuery):
    await callback.message.answer(RULES_TEXT)
    await callback.answer()

@dp.callback_query(F.data == "info_my_data")
async def info_my_data(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    await callback.message.answer(
        f"👤 <b>Мої дані</b>\n\n"
        f"Ім'я та прізвище: {user['full_name'] or 'не вказано'}\n"
        f"Телефон: {user['phone'] or 'не вказано'}"
    )
    await callback.answer()

@dp.message(F.text == "📦 Забронювати обладнання")
async def start_booking(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(selected={})
    await state.set_state(BookingStates.choosing_equipment)
    await show_equipment(message, state)

@dp.callback_query(BookingStates.choosing_equipment, F.data.startswith("eq:"))
async def select_equipment(callback: CallbackQuery, state: FSMContext):
    eid = int(callback.data.split(":", 1)[1])
    e = db.get_equipment_item(eid)
    if not e or e["disabled"]:
        await callback.answer("Це обладнання зараз недоступне.", show_alert=True)
        return
    await state.update_data(quantity_equipment_id=eid, quantity_current=0, quantity_max=int(e["available_qty"]))
    await state.set_state(BookingStates.choosing_quantity)
    await callback.message.edit_text(
        f"📦 <b>{e['name']}</b>\nДоступно: {e['available_qty']} шт.\n\nОберіть кількість:",
        reply_markup=quantity_keyboard(0, int(e["available_qty"]))
    )
    await callback.answer()

@dp.callback_query(BookingStates.choosing_quantity, F.data.startswith("qty:"))
async def quantity_change(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cur = int(data.get("quantity_current", 0))
    maximum = int(data.get("quantity_max", 0))
    action = callback.data.split(":", 1)[1]
    if action == "plus":
        cur = min(maximum, cur + 1)
    elif action == "minus":
        cur = max(0, cur - 1)
    await state.update_data(quantity_current=cur)
    await callback.message.edit_reply_markup(reply_markup=quantity_keyboard(cur, maximum))
    await callback.answer()

@dp.callback_query(BookingStates.choosing_quantity, F.data == "qty_save")
async def quantity_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    eid = data["quantity_equipment_id"]
    qty = int(data["quantity_current"])
    selected = data.get("selected", {})
    if qty == 0:
        selected.pop(eid, None)
    else:
        selected[eid] = qty
    await state.update_data(selected=selected)
    await state.set_state(BookingStates.choosing_equipment)
    await callback.message.edit_text(
        "📦 <b>Оберіть обладнання</b>\n"
        "Вибрані позиції позначені ✅. Можна додати кілька різних позицій.",
        reply_markup=equipment_keyboard(db.get_equipment(), selected)
    )
    await callback.answer()

@dp.callback_query(BookingStates.choosing_equipment, F.data == "eq_done")
async def equipment_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected"):
        await callback.answer("Оберіть хоча б одну позицію.", show_alert=True)
        return
    await state.set_state(BookingStates.choosing_pickup_date)
    await callback.message.edit_text(
        f"📅 <b>Дата отримання</b>\n"
        f"Найраніше: {min_pickup_date().strftime('%d.%m.%Y')}",
        reply_markup=calendar_keyboard("pickup")
    )
    await callback.answer()

@dp.callback_query(BookingStates.choosing_pickup_date, F.data.startswith("pickup_date:"))
async def pickup_date(callback: CallbackQuery, state: FSMContext):
    d = date.fromisoformat(callback.data.split(":", 1)[1])
    if not valid_pickup_date(d):
        await callback.answer("Цю дату не можна обрати.", show_alert=True)
        return
    await state.update_data(pickup_date=d.isoformat())
    await state.set_state(BookingStates.choosing_pickup_time)
    await callback.message.edit_text("🕐 Оберіть час отримання:", reply_markup=time_keyboard("pickup"))
    await callback.answer()

@dp.callback_query(BookingStates.choosing_pickup_time, F.data.startswith("pickup_time:"))
async def pickup_time(callback: CallbackQuery, state: FSMContext):
    await state.update_data(pickup_time=callback.data.split(":", 1)[1])
    await state.set_state(BookingStates.choosing_return_date)
    await callback.message.edit_text(
        "📅 <b>Дата повернення</b>\nОберіть робочий день.",
        reply_markup=calendar_keyboard("return")
    )
    await callback.answer()

@dp.callback_query(BookingStates.choosing_return_date, F.data.startswith("return_date:"))
async def return_date(callback: CallbackQuery, state: FSMContext):
    d = date.fromisoformat(callback.data.split(":", 1)[1])
    data = await state.get_data()
    pickup_d = date.fromisoformat(data["pickup_date"])
    if d < pickup_d:
        await callback.answer("Повернення не може бути раніше отримання.", show_alert=True)
        return
    await state.update_data(return_date=d.isoformat())
    await state.set_state(BookingStates.choosing_return_time)
    await callback.message.edit_text("🕐 Оберіть час повернення:", reply_markup=time_keyboard("return"))
    await callback.answer()

@dp.callback_query(BookingStates.choosing_return_time, F.data.startswith("return_time:"))
async def return_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pickup_d = date.fromisoformat(data["pickup_date"])
    return_d = date.fromisoformat(data["return_date"])
    pickup_t = datetime.strptime(data["pickup_time"], "%H:%M").time()
    return_t = datetime.strptime(callback.data.split(":", 1)[1], "%H:%M").time()
    if not booking_period_valid(pickup_d, pickup_t, return_d, return_t):
        await callback.answer("Час повернення має бути пізніше часу отримання.", show_alert=True)
        return

    pickup_at = dt_iso(pickup_d, pickup_t)
    return_at = dt_iso(return_d, return_t)
    selected = data["selected"]

    unavailable = []
    for eid, qty in selected.items():
        available = db.get_available_for_period(eid, pickup_at, return_at)
        if qty > available:
            e = db.get_equipment_item(eid)
            unavailable.append(f"• {e['name']}: доступно {available} шт.")
    if unavailable:
        await callback.message.answer(
            "⚠️ На обраний період потрібної кількості немає:\n" + "\n".join(unavailable) +
            "\n\nЗмініть кількість або дати."
        )
        await state.set_state(BookingStates.choosing_equipment)
        await show_equipment(callback.message, state)
        await callback.answer()
        return

    user = db.get_user(callback.from_user.id)
    await state.update_data(
        return_time=callback.data.split(":", 1)[1],
        pickup_at=pickup_at,
        return_at=return_at,
        full_name=user["full_name"] or "",
        phone=user["phone"] or "",
    )
    if user["full_name"]:
        await state.set_state(BookingStates.entering_event)
        await callback.message.answer("🎯 Для якого заходу/події потрібне обладнання?")
    else:
        await state.set_state(BookingStates.entering_name)
        await callback.message.answer("👤 Вкажіть ім'я та прізвище відповідальної особи.")
    await callback.answer()

@dp.message(BookingStates.entering_name)
async def enter_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    db.upsert_user(message.from_user.id, full_name=message.text.strip())
    user = db.get_user(message.from_user.id)
    await state.update_data(phone=user["phone"] or "")
    if user["phone"]:
        await state.set_state(BookingStates.entering_event)
        await message.answer("🎯 Для якого заходу/події потрібне обладнання?")
    else:
        await state.set_state(BookingStates.entering_phone)
        await message.answer("📞 Вкажіть номер телефону:", reply_markup=phone_keyboard())

@dp.message(BookingStates.entering_phone, F.contact)
async def phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    db.upsert_user(message.from_user.id, phone=phone)
    await state.update_data(phone=phone)
    await state.set_state(BookingStates.entering_event)
    await message.answer("🎯 Для якого заходу/події потрібне обладнання?", reply_markup=ReplyKeyboardRemove())

@dp.message(BookingStates.entering_phone, F.text == "✍️ Ввести номер вручну")
async def phone_manual_start(message: Message):
    await message.answer("Введіть номер телефону:")

@dp.message(BookingStates.entering_phone, F.text)
async def phone_manual(message: Message, state: FSMContext):
    phone = message.text.strip()
    db.upsert_user(message.from_user.id, phone=phone)
    await state.update_data(phone=phone)
    await state.set_state(BookingStates.entering_event)
    await message.answer("🎯 Для якого заходу/події потрібне обладнання:", reply_markup=ReplyKeyboardRemove())

@dp.message(BookingStates.entering_event)
async def enter_event(message: Message, state: FSMContext):
    await state.update_data(event_name=message.text.strip())
    data = await state.get_data()
    await state.set_state(BookingStates.confirming)
    await message.answer(booking_summary(data), reply_markup=final_booking_keyboard())

@dp.callback_query(BookingStates.confirming, F.data == "show_rules")
async def show_rules(callback: CallbackQuery):
    await callback.message.answer(RULES_TEXT)
    await callback.answer()

@dp.callback_query(BookingStates.confirming, F.data == "agree_rules")
async def agree_rules(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data["rules_agreed_at"] = now_local().isoformat()
    await state.update_data(**data)
    # Додатково показуємо підтвердження перед відправкою.
    await callback.message.answer(
        booking_summary(data) +
        "\n\n☑️ Ви погодилися з правилами.\n\n"
        "Натисніть «Надіслати заявку», щоб передати бронювання працівнику."
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📨 Надіслати заявку", callback_data="submit_booking")
    builder.button(text="❌ Скасувати", callback_data="booking_cancel")
    builder.adjust(1)
    await callback.message.answer("Готово?", reply_markup=builder.as_markup())
    await callback.answer("Згоду зафіксовано.")

@dp.callback_query(BookingStates.confirming, F.data == "submit_booking")
async def submit_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("rules_agreed_at"):
        await callback.answer("Спочатку погодьтеся з правилами.", show_alert=True)
        return

    # Повторна перевірка доступності прямо перед створенням заявки.
    unavailable = []
    for eid, qty in data["selected"].items():
        available = db.get_available_for_period(eid, data["pickup_at"], data["return_at"])
        if qty > available:
            e = db.get_equipment_item(eid)
            unavailable.append(f"• {e['name']}: доступно {available} шт.")
    if unavailable:
        await callback.message.answer(
            "⚠️ Доступність змінилася:\n" + "\n".join(unavailable) +
            "\n\nЗаявку не створено. Змініть кількість або дати."
        )
        await state.set_state(BookingStates.choosing_equipment)
        await show_equipment(callback.message, state)
        await callback.answer()
        return

    booking_id = db.create_booking(
        callback.from_user.id,
        data["full_name"],
        data["phone"],
        data["event_name"],
        data["pickup_at"],
        data["return_at"],
        data["selected"],
        data["rules_agreed_at"],
    )
    await state.clear()
    await callback.message.answer(
        f"🕐 <b>Заявку надіслано</b>\n\n"
        f"Ваше бронювання №{booking_id} прийнято та очікує підтвердження працівником "
        f"Пластового вишкільного центру.\n\n"
        "Після розгляду ви отримаєте повідомлення про рішення.",
        reply_markup=main_menu(is_admin(callback.from_user.id))
    )
    await notify_admin_new_booking(booking_id)
    await callback.answer()

@dp.callback_query(F.data == "booking_cancel")
async def booking_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Бронювання скасовано.", reply_markup=main_menu(is_admin(callback.from_user.id)))
    await callback.answer()

@dp.message(F.text == "📋 Мої бронювання")
async def my_bookings(message: Message):
    rows = db.get_user_bookings(message.from_user.id)
    if not rows:
        await message.answer("У вас поки немає бронювань.")
        return
    for b in rows:
        text = (
            f"📋 <b>Бронювання №{b['id']}</b>\n"
            f"Статус: {STATUS_TEXT.get(b['status'], b['status'])}\n"
            f"🎯 {b['event_name']}\n"
            f"📦 " + ", ".join(
                f"{i['equipment_name']} — {i['reserved_qty']} шт."
                for i in db.get_booking_items(b["id"])
            ) +
            f"\n📅 {fmt_iso(b['pickup_at'])} → {fmt_iso(b['return_at'])}"
        )
        markup = booking_edit_keyboard(b["id"]) if b["status"] in ("pending", "confirmed") else None
        await message.answer(text, reply_markup=markup)

@dp.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_user_booking(callback: CallbackQuery):
    booking_id = int(callback.data.split(":", 1)[1])
    b = db.get_booking(booking_id)
    if not b or b["telegram_id"] != callback.from_user.id:
        await callback.answer("Бронювання не знайдено.", show_alert=True)
        return
    if b["status"] not in ("pending", "confirmed"):
        await callback.answer("Це бронювання вже не можна скасувати.", show_alert=True)
        return
    db.cancel_booking(booking_id)
    await callback.message.answer(f"🚫 Бронювання №{booking_id} скасовано.")
    if b["status"] == "confirmed":
        await bot.send_message(ADMIN_ID, f"🔔 Бронювання №{booking_id} скасовано користувачем.")
    await callback.answer("Скасовано.")

# ---------- ADMIN ----------

@dp.message(F.text == "⚙️ Адмін-панель")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("⚙️ Адмін-панель", reply_markup=admin_panel_keyboard())

@dp.callback_query(F.data == "admin_pending")
async def admin_pending(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    rows = [b for b in db.get_due_bookings_for_reminder() if b["status"] == "confirmed"]
    # pending потрібно окремо, щоб не змішувати з confirmed.
    conn = db.connect()
    pending = conn.execute("SELECT * FROM bookings WHERE status='pending' ORDER BY created_at").fetchall()
    conn.close()
    if not pending:
        await callback.message.answer("Нових заявок немає.")
    for b in pending:
        await callback.message.answer(admin_booking_text(b["id"]), reply_markup=admin_booking_keyboard(b["id"]))
    await callback.answer()

@dp.callback_query(F.data.startswith("adm:approve:"))
async def admin_approve(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    booking_id = int(callback.data.split(":")[2])
    b = db.get_booking(booking_id)
    if not b or b["status"] != "pending":
        await callback.answer("Це бронювання вже оброблено.", show_alert=True)
        return
    # Recheck availability.
    for item in db.get_booking_items(booking_id):
        available = db.get_available_for_period(item["equipment_id"], b["pickup_at"], b["return_at"], booking_id)
        if item["reserved_qty"] > available:
            await callback.answer("На цей період уже недостатньо обладнання.", show_alert=True)
            return
    db.set_booking_status(booking_id, "confirmed")
    await callback.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(
        b["telegram_id"],
        f"🎉 <b>Ваше бронювання підтверджено!</b>\n\n"
        f"Бронювання №{booking_id}\n"
        f"📦 " + "\n".join(
            f"• {i['equipment_name']} — {i['reserved_qty']} шт."
            for i in db.get_booking_items(booking_id)
        ) +
        f"\n\n📅 <b>Отримання:</b> {fmt_iso(b['pickup_at'])}\n"
        f"📅 <b>Повернення:</b> {fmt_iso(b['return_at'])}"
    )
    await callback.answer("Підтверджено.")

@dp.callback_query(F.data.startswith("adm:reject:"))
async def admin_reject_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    booking_id = int(callback.data.split(":")[2])
    await state.update_data(admin_booking_id=booking_id)
    await state.set_state(AdminStates.rejecting)
    await callback.message.answer("✍️ Вкажіть причину відхилення заявки:")
    await callback.answer()

@dp.message(AdminStates.rejecting)
async def admin_reject_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    booking_id = data["admin_booking_id"]
    reason = message.text.strip()
    b = db.get_booking(booking_id)
    db.set_booking_status(booking_id, "rejected", reason)
    await bot.send_message(
        b["telegram_id"],
        f"❌ <b>Бронювання №{booking_id} відхилено</b>\n\nПричина: {reason}"
    )
    await message.answer("Заявку відхилено.")
    await state.clear()

@dp.callback_query(F.data.startswith("adm:time:"))
async def admin_time_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    booking_id = int(callback.data.split(":")[2])
    await state.update_data(admin_booking_id=booking_id)
    await state.set_state(AdminStates.changing_time_pickup_date)
    await callback.message.answer("📅 Оберіть нову дату отримання:", reply_markup=calendar_keyboard("pickup"))
    await callback.answer()

@dp.callback_query(AdminStates.changing_time_pickup_date, F.data.startswith("pickup_date:"))
async def admin_new_pickup_date(callback: CallbackQuery, state: FSMContext):
    d = date.fromisoformat(callback.data.split(":", 1)[1])
    await state.update_data(new_pickup_date=d.isoformat())
    await state.set_state(AdminStates.changing_time_pickup_time)
    await callback.message.answer("🕐 Новий час отримання:", reply_markup=time_keyboard("pickup"))
    await callback.answer()

@dp.callback_query(AdminStates.changing_time_pickup_time, F.data.startswith("pickup_time:"))
async def admin_new_pickup_time(callback: CallbackQuery, state: FSMContext):
    await state.update_data(new_pickup_time=callback.data.split(":", 1)[1])
    await state.set_state(AdminStates.changing_time_return_date)
    await callback.message.answer("📅 Нова дата повернення:", reply_markup=calendar_keyboard("return"))
    await callback.answer()

@dp.callback_query(AdminStates.changing_time_return_date, F.data.startswith("return_date:"))
async def admin_new_return_date(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    d = date.fromisoformat(callback.data.split(":", 1)[1])
    pickup_d = date.fromisoformat(data["new_pickup_date"])
    if d < pickup_d:
        await callback.answer("Повернення не може бути раніше отримання.", show_alert=True)
        return
    await state.update_data(new_return_date=d.isoformat())
    await state.set_state(AdminStates.changing_time_return_time)
    await callback.message.answer("🕐 Новий час повернення:", reply_markup=time_keyboard("return"))
    await callback.answer()

@dp.callback_query(AdminStates.changing_time_return_time, F.data.startswith("return_time:"))
async def admin_new_return_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pickup_d = date.fromisoformat(data["new_pickup_date"])
    return_d = date.fromisoformat(data["new_return_date"])
    pickup_t = datetime.strptime(data["new_pickup_time"], "%H:%M").time()
    return_t = datetime.strptime(callback.data.split(":", 1)[1], "%H:%M").time()
    if not booking_period_valid(pickup_d, pickup_t, return_d, return_t):
        await callback.answer("Час повернення має бути пізніше часу отримання.", show_alert=True)
        return
    booking_id = data["admin_booking_id"]
    pickup_at = dt_iso(pickup_d, pickup_t)
    return_at = dt_iso(return_d, return_t)
    b = db.get_booking(booking_id)
    # Recheck availability against the proposed new period.
    for item in db.get_booking_items(booking_id):
        available = db.get_available_for_period(item["equipment_id"], pickup_at, return_at, booking_id)
        if item["reserved_qty"] > available:
            await callback.message.answer("⚠️ На новий період недостатньо обладнання. Час не змінено.")
            await state.clear()
            await callback.answer()
            return
    db.update_booking_times(booking_id, pickup_at, return_at)
    b = db.get_booking(booking_id)
    db.set_booking_status(booking_id, "confirmed")
    await bot.send_message(
        b["telegram_id"],
        f"✏️ <b>Час бронювання змінено працівником</b>\n\n"
        f"📅 Отримання: {fmt_iso(pickup_at)}\n"
        f"📅 Повернення: {fmt_iso(return_at)}"
    )
    await callback.message.answer("Час успішно змінено та бронювання підтверджено.")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data.startswith("adm:issue:"))
async def admin_issue_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    booking_id = int(callback.data.split(":")[2])
    b = db.get_booking(booking_id)
    if b["status"] != "confirmed":
        await callback.answer("Видати можна лише підтверджене бронювання.", show_alert=True)
        return
    await state.update_data(admin_booking_id=booking_id, issue_items=[i["id"] for i in db.get_booking_items(booking_id)], issue_index=0, issued={})
    await state.set_state(AdminStates.issuing)
    await ask_issue_item(callback.message, state)
    await callback.answer()

async def ask_issue_item(message, state):
    data = await state.get_data()
    ids = data["issue_items"]
    idx = data["issue_index"]
    if idx >= len(ids):
        booking_id = data["admin_booking_id"]
        db.set_issue_quantities(booking_id, data["issued"])
        await message.answer("📦 Видачу зафіксовано. Статус: «Обладнання видано».")
        await state.clear()
        return
    item_id = ids[idx]
    conn = db.connect()
    item = conn.execute(
        """SELECT bi.*, e.name FROM booking_items bi
           JOIN equipment e ON e.id=bi.equipment_id
           WHERE bi.id=?""", (item_id,)
    ).fetchone()
    conn.close()
    await message.answer(
        f"📦 {item['name']}\nЗаброньовано: {item['reserved_qty']} шт.\n"
        "Введіть фактичну кількість виданого обладнання цифрою:"
    )

@dp.message(AdminStates.issuing)
async def admin_issue_item(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
    except ValueError:
        await message.answer("Введіть ціле число.")
        return
    data = await state.get_data()
    item_id = data["issue_items"][data["issue_index"]]
    conn = db.connect()
    item = conn.execute("SELECT reserved_qty FROM booking_items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if qty < 0 or qty > item["reserved_qty"]:
        await message.answer(f"Кількість має бути від 0 до {item['reserved_qty']}.")
        return
    issued = data["issued"]
    issued[item_id] = qty
    await state.update_data(issued=issued, issue_index=data["issue_index"] + 1)
    await ask_issue_item(message, state)

@dp.callback_query(F.data.startswith("adm:return:"))
async def admin_return_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    booking_id = int(callback.data.split(":")[2])
    b = db.get_booking(booking_id)
    if b["status"] != "issued":
        await callback.answer("Повернення можна оформити після видачі.", show_alert=True)
        return
    items = db.get_booking_items(booking_id)
    await state.update_data(
        admin_booking_id=booking_id,
        return_items=[i["id"] for i in items],
        return_index=0,
        returned={}
    )
    await state.set_state(AdminStates.returning)
    await ask_return_item(callback.message, state)
    await callback.answer()

async def ask_return_item(message, state):
    data = await state.get_data()
    ids = data["return_items"]
    idx = data["return_index"]
    if idx >= len(ids):
        booking_id = data["admin_booking_id"]
        db.set_return_data(booking_id, data["returned"])
        # Stock correction: only actually returned items become available.
        conn = db.connect()
        rows = conn.execute(
            "SELECT equipment_id, issued_qty, returned_qty, condition FROM booking_items WHERE booking_id=?",
            (booking_id,)
        ).fetchall()
        conn.close()
        for row in rows:
            # Issued items were deducted from available stock conceptually by reservation.
            # On return, good items re-enter stock; damaged/not returned do not.
            if row["condition"] == "good":
                db.change_available_qty(row["equipment_id"], row["returned_qty"])
        await message.answer("🔄 Повернення зафіксовано. Стан кожної позиції збережено.")
        await state.clear()
        return

    item_id = ids[idx]
    conn = db.connect()
    item = conn.execute(
        """SELECT bi.*, e.name FROM booking_items bi
           JOIN equipment e ON e.id=bi.equipment_id
           WHERE bi.id=?""", (item_id,)
    ).fetchone()
    conn.close()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Все добре", callback_data="retcond:good")
    builder.button(text="⚠️ Пошкоджене", callback_data="retcond:damaged")
    builder.button(text="❌ Не повернуто", callback_data="retcond:not_returned")
    builder.adjust(1)
    await state.update_data(current_return_item=item_id, current_issued=item["issued_qty"])
    await message.answer(
        f"🔄 {item['name']}\nВидано: {item['issued_qty']} шт.\n"
        "Введіть фактичну кількість повернутого обладнання:"
    )

@dp.message(AdminStates.returning)
async def admin_return_qty(message: Message, state: FSMContext):
    data = await state.get_data()
    if "return_qty" not in data:
        try:
            qty = int(message.text.strip())
        except ValueError:
            await message.answer("Введіть ціле число.")
            return
        if qty < 0 or qty > int(data["current_issued"]):
            await message.answer(f"Кількість має бути від 0 до {data['current_issued']}.")
            return
        await state.update_data(return_qty=qty)
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Все добре", callback_data="retcond:good")
        builder.button(text="⚠️ Пошкоджене", callback_data="retcond:damaged")
        builder.button(text="❌ Не повернуто", callback_data="retcond:not_returned")
        builder.adjust(1)
        await message.answer("Оберіть стан:", reply_markup=builder.as_markup())

@dp.callback_query(AdminStates.returning, F.data.startswith("retcond:"))
async def admin_return_condition(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    condition = callback.data.split(":", 1)[1]
    returned = data["returned"]
    returned[data["current_return_item"]] = {
        "qty": int(data["return_qty"]),
        "condition": condition,
        "comment": None
    }
    idx = data["return_index"] + 1
    await state.update_data(returned=returned, return_index=idx, return_qty=None)
    if condition in ("damaged", "not_returned"):
        await state.update_data(await_comment=True)
        await callback.message.answer("✍️ Додайте коментар (що пошкоджено / що не повернуто):")
    else:
        await ask_return_item(callback.message, state)
    await callback.answer()

@dp.message(AdminStates.returning)
async def admin_return_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("await_comment"):
        return
    # The most recent item is the one needing comment.
    item_id = data["return_items"][data["return_index"] - 1]
    returned = data["returned"]
    returned[item_id]["comment"] = message.text.strip()
    await state.update_data(returned=returned, await_comment=False)
    await ask_return_item(message, state)

@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Оберіть дію з меню нижче.",
        reply_markup=main_menu(is_admin(message.from_user.id))
    )

async def reminder_loop():
    sent = set()
    while True:
        try:
            now = now_local()
            rows = db.get_due_bookings_for_reminder()
            for b in rows:
                pickup = datetime.fromisoformat(b["pickup_at"]).astimezone(TIMEZONE)
                ret = datetime.fromisoformat(b["return_at"]).astimezone(TIMEZONE)
                if now.date() == (pickup.date() - timedelta(days=1)) and b["id"] not in sent:
                    await bot.send_message(
                        b["telegram_id"],
                        f"🔔 <b>Нагадування про отримання</b>\n\n"
                        f"Завтра, {fmt_iso(b['pickup_at'])}, у вас заплановане отримання обладнання.\n\n"
                        + "\n".join(
                            f"• {i['equipment_name']} — {i['reserved_qty']} шт."
                            for i in db.get_booking_items(b["id"])
                        )
                    )
                    sent.add(b["id"])
                key = (b["id"], "return")
                if now.date() == (ret.date() - timedelta(days=1)) and key not in sent:
                    await bot.send_message(
                        b["telegram_id"],
                        f"🔔 <b>Нагадування про повернення</b>\n\n"
                        f"Завтра, {fmt_iso(b['return_at'])}, у вас заплановане повернення обладнання."
                    )
                    sent.add(key)
        except Exception:
            logging.exception("Помилка reminder_loop")
        await asyncio.sleep(1800)

async def main():
    db.init_db()
    db.seed_equipment()
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
