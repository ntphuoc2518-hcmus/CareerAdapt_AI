/** How one reminder reads and where it leads; shared by the Nhắc nhở page and the bell's quick list. */
import { esc } from "./core.js";

const LESSON = "#/plan/da/roadmap/lesson/";

/** The server decides the state and the day count; this only turns them into words and a tone. */
export function reminderState(item) {
    const days = Math.abs(item.days ?? 0);
    if (item.state === "OVERDUE") return { tone: "bad", icon: "alert", label: days ? `Quá hạn ${days} ngày` : "Quá hạn" };
    if (item.state === "DUE_SOON") return { tone: "warn", icon: "clock", label: days ? `Còn ${days} ngày` : "Đến hạn hôm nay" };
    if (item.state === "MINI_TEST") return { tone: "brand", icon: "quiz", label: "Đến hạn ôn tập" };
    return { tone: "muted", icon: "calendar", label: "Lịch cần xem lại" };
}

/** The one thing to do next for a reminder. */
export function reminderAction(item) {
    const micro = item.payload?.micro_id;
    if (item.kind === "MINI_TEST" && micro) return { href: `#/mini/${esc(micro)}`, label: "Làm ngay" };
    if (item.activity_id) return { href: `${LESSON}${esc(item.activity_id)}`, label: "Mở bài học" };
    return { href: "#/plan/da/roadmap", label: "Xem lộ trình" };
}

/** The lesson's own name when the reminder is about a lesson; otherwise the stored title. */
export const reminderTitle = item => item.activity_title || item.title;

/** Tell the top bar that the list changed, so the bell count follows without a page change. */
export const remindersChanged = () => document.dispatchEvent(new CustomEvent("reminders-changed"));
