import html
import logging
import asyncio
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import messages
from emoji_config import E
import keyboards
import storage
import config

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=ZoneInfo(config.TIMEZONE))


async def auto_complete_booking(bot, booking: dict):
    """Automatically complete booking after visit time has passed"""
    try:
        completed = await storage.complete_booking(booking["id"])
        if completed:
            logger.info(f"Auto-completed booking {booking['id']}")
            # CRIT-004 FIX: Update loyalty on auto-completion (was never called here)
            try:
                _visits = await storage.update_loyalty(completed["telegram_id"], completed.get("name", ""))
                if _visits % config.LOYALTY_VISIT_INTERVAL == 0:
                    _reward = (
                        f"⭐ <b>Поздравляем!</b>\n\n"
                        f"Это ваш {_visits}-й визит! Скидка {config.LOYALTY_DISCOUNT_PERCENT}% на следующую запись."
                    )
                    try:
                        await bot.send_message(completed["telegram_id"], _reward, parse_mode="HTML")
                    except Exception as _le:
                        logger.error(f"Failed to send loyalty reward: {_le}")
            except Exception as _le:
                logger.error(f"Failed to update loyalty {completed['id']}: {_le}")

            

            # HIGH-03 FIX: html.escape all user-controlled fields in HTML message
            admin_text = f"{E.CHECK} <b>Запись завершена</b>\n\n"
            admin_text += f"{E.USER} <b>Клиент:</b> {html.escape(completed['name'])}\n"
            admin_text += f"{E.SCISSORS} <b>Мастер:</b> {html.escape(completed['master'])}\n"
            admin_text += f"{E.BARBER} <b>Услуга:</b> {html.escape(completed['service'])}\n"
            admin_text += f"{E.CALENDAR} <b>Дата:</b> {keyboards._format_date(completed['date'])}\n"
            admin_text += f"{E.CLOCK} <b>Время:</b> {completed['time']}\n"
            admin_text += f"{E.MONEY} <b>Выручка:</b> {completed['price']:,} ₸\n".replace(",", " ")
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to auto-complete booking {booking['id']}: {e}")


async def send_reminder_24h(bot, booking: dict):
    try:
        text = messages.REMINDER_24H.format(
            date=html.escape(keyboards._format_date(booking["date"])),
            time=html.escape(booking["time"]),
            master=html.escape(booking["master"]),
            service=html.escape(booking["service"]),
        )
        await bot.send_message(
            booking["telegram_id"],
            text,
            reply_markup=keyboards.remind_kb(booking["id"]),
            parse_mode="HTML",
        )
    except TelegramForbiddenError:
        # BUG-M2 FIX: cancel all future reminders to avoid log spam
        logger.warning(f"User {booking['telegram_id']} blocked bot - cancelling reminders for booking {booking['id']}")
        await cancel_reminders(booking["id"])
    except TelegramRetryAfter as e:
        logger.warning(f"Rate limited {e.retry_after}s - 24h reminder skipped")
    except Exception as e:
        logger.error(f"Failed to send 24h reminder: {e}")


async def send_reminder_2h(bot, booking: dict):
    try:
        text = messages.REMINDER_2H.format(
            date=html.escape(keyboards._format_date(booking["date"])),
            time=html.escape(booking["time"]),
            master=html.escape(booking["master"]),
            service=html.escape(booking.get("service", "")),
        )
        await bot.send_message(
            booking["telegram_id"],
            text,
            reply_markup=keyboards.remind_2h_kb(booking["id"]),
            parse_mode="HTML",
        )
    except TelegramForbiddenError:
        # BUG-M2 FIX: cancel future reminders
        logger.warning(f"User {booking['telegram_id']} blocked bot - cancelling reminders for booking {booking['id']}")
        await cancel_reminders(booking["id"])
    except TelegramRetryAfter as e:
        logger.warning(f"Rate limited {e.retry_after}s - 2h reminder skipped")
    except Exception as e:
        logger.error(f"Failed to send 2h reminder: {e}")


async def send_review_request(bot, booking: dict):
    try:
        text = messages.REQUEST_REVIEW.format(
            master=html.escape(booking["master"]),
            date=html.escape(keyboards._format_date(booking["date"])),
        )
        await bot.send_message(
            booking["telegram_id"],
            text,
            reply_markup=keyboards.review_kb(booking["id"]),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to send review request: {e}")


async def _save_job(job_id: str, run_date: str, job_type: str, booking_id: str):
    try:
        await storage.save_scheduler_job(job_id, run_date, job_type, booking_id)
    except Exception as e:
        logger.error(f"Failed to save scheduler job: {e}")


async def schedule_reminders(bot, booking: dict):
    try:
        tz = ZoneInfo(config.TIMEZONE)
        visit_datetime = datetime.strptime(f"{booking['date']} {booking['time']}", "%Y-%m-%d %H:%M")
        visit_datetime = visit_datetime.replace(tzinfo=tz)
        now = datetime.now(tz)

        reminder_24h = visit_datetime - timedelta(hours=24)
        if reminder_24h > now:
            job_id = f"reminder_24h_{booking['id']}"
            await _save_job(job_id, reminder_24h.isoformat(), "reminder_24h", booking["id"])
            scheduler.add_job(
                send_reminder_24h,
                trigger=DateTrigger(run_date=reminder_24h),
                args=[bot, booking],
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"Scheduled 24h reminder for booking {booking['id']} at {reminder_24h}")

        reminder_2h = visit_datetime - timedelta(hours=2)
        if reminder_2h > now:
            job_id = f"reminder_2h_{booking['id']}"
            await _save_job(job_id, reminder_2h.isoformat(), "reminder_2h", booking["id"])
            scheduler.add_job(
                send_reminder_2h,
                trigger=DateTrigger(run_date=reminder_2h),
                args=[bot, booking],
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"Scheduled 2h reminder for booking {booking['id']} at {reminder_2h}")

        # Auto-complete booking 30 minutes after visit time
        completion_time = visit_datetime + timedelta(minutes=30)
        job_id = f"auto_complete_{booking['id']}"
        await _save_job(job_id, completion_time.isoformat(), "auto_complete", booking["id"])
        scheduler.add_job(
            auto_complete_booking,
            trigger=DateTrigger(run_date=completion_time),
            args=[bot, booking],
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled auto-completion for booking {booking['id']} at {completion_time}")

        review_time = visit_datetime + timedelta(hours=3)
        job_id = f"review_{booking['id']}"
        await _save_job(job_id, review_time.isoformat(), "review", booking["id"])
        scheduler.add_job(
            send_review_request,
            trigger=DateTrigger(run_date=review_time),
            args=[bot, booking],
            id=job_id,
            replace_existing=True,
        )
        logger.info(f"Scheduled review request for booking {booking['id']} at {review_time}")

    except Exception as e:
        logger.error(f"Failed to schedule reminders for booking {booking['id']}: {e}")


async def cancel_reminders(booking_id: str):
    for job_id in [f"reminder_24h_{booking_id}", f"reminder_2h_{booking_id}", f"auto_complete_{booking_id}", f"review_{booking_id}"]:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        try:
            await storage.remove_scheduler_job(job_id)
        except Exception:
            pass


async def start_scheduler(bot):
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
        
        # Schedule daily cleanup of old bookings (runs at 3 AM daily)
        scheduler.add_job(
            cleanup_old_bookings_job,
            trigger='cron',
            hour=3,
            minute=0,
            id='cleanup_old_bookings',
            replace_existing=True,
        )
        logger.info("Scheduled daily cleanup of old bookings at 3:00 AM")

        # BUG-C4 FIX: Periodic cleanup of expired slot_locks every 2 minutes
        scheduler.add_job(
            cleanup_slot_locks_job,
            trigger='interval',
            minutes=2,
            id='cleanup_slot_locks',
            replace_existing=True,
        )
        logger.info("Scheduled periodic slot_locks cleanup every 2 minutes")
        
        # Recovery: load jobs from DB and reschedule them
        try:
            jobs = await storage.get_all_scheduler_jobs()
            tz = ZoneInfo(config.TIMEZONE)
            now = datetime.now(tz)
            recovered = 0
            
            for job in jobs:
                try:
                    run_date_str = job["run_date"]
                    run_date = datetime.fromisoformat(run_date_str)
                    if run_date.tzinfo is None:
                        run_date = run_date.replace(tzinfo=tz)
                    if run_date <= now:
                        # Job is in the past, skip it
                        await storage.remove_scheduler_job(job["id"])
                        continue
                    
                    booking_id = job["booking_id"]
                    job_type = job["job_type"]
                    
                    # Get booking details
                    booking = await storage.get_booking_with_user(booking_id)
                    if not booking or booking.get("status") != "active":
                        # Booking no longer active, remove job
                        await storage.remove_scheduler_job(job["id"])
                        continue
                    
                    # Reschedule the job based on type
                    if job_type == "reminder_24h":
                        scheduler.add_job(
                            send_reminder_24h,
                            trigger=DateTrigger(run_date=run_date),
                            args=[bot, booking],
                            id=job["id"],
                            replace_existing=True,
                        )
                        recovered += 1
                    elif job_type == "reminder_2h":
                        scheduler.add_job(
                            send_reminder_2h,
                            trigger=DateTrigger(run_date=run_date),
                            args=[bot, booking],
                            id=job["id"],
                            replace_existing=True,
                        )
                        recovered += 1
                    elif job_type == "auto_complete":
                        scheduler.add_job(
                            auto_complete_booking,
                            trigger=DateTrigger(run_date=run_date),
                            args=[bot, booking],
                            id=job["id"],
                            replace_existing=True,
                        )
                        recovered += 1
                    elif job_type == "review":
                        scheduler.add_job(
                            send_review_request,
                            trigger=DateTrigger(run_date=run_date),
                            args=[bot, booking],
                            id=job["id"],
                            replace_existing=True,
                        )
                        recovered += 1
                    
                except Exception as e:
                    logger.error(f"Failed to recover job {job['id']}: {e}")
                    continue
            
            logger.info(f"Scheduler recovery: {recovered} jobs recovered from DB")
        except Exception as e:
            logger.error(f"Scheduler recovery failed: {e}")


async def cleanup_old_bookings_job():
    """Daily job to cleanup old bookings"""
    try:
        deleted = await storage.cleanup_old_bookings(days=90)
        logger.info(f"Cleaned up {deleted} old bookings (older than 90 days)")
    except Exception as e:
        logger.error(f"Failed to cleanup old bookings: {e}")




async def cleanup_slot_locks_job():
    """BUG-C4 FIX: Periodic job to remove expired slot_locks every 2 minutes.
    Prevents ghost-locked slots when users abandon booking mid-flow."""
    try:
        deleted = await storage.cleanup_expired_slot_locks()
        if deleted:
            logger.debug(f"cleanup_slot_locks_job: cleared {deleted} expired lock(s)")
    except Exception as e:
        logger.error(f"cleanup_slot_locks_job failed: {e}")

def shutdown_scheduler():
    if scheduler.running:
        try:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.warning(f"Scheduler shutdown warning: {e}")
