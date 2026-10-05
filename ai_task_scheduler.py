"""A beginner-friendly task manager with a smart daily scheduler.

Run:
    python -m pip install streamlit
    streamlit run ai_task_scheduler.py

Tasks are saved locally in tasks.db. The scheduler uses transparent priority,
deadline, and duration rules; it does not require an AI API key.
"""

from datetime import date, datetime, time, timedelta
import sqlite3
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).with_name("tasks.db")


def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect_db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                notes TEXT DEFAULT '',
                duration INTEGER NOT NULL,
                priority TEXT NOT NULL,
                due_date TEXT,
                created_at TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0
            )"""
        )


def add_task(title, notes, duration, priority, due_date):
    with connect_db() as conn:
        conn.execute(
            """INSERT INTO tasks
               (title, notes, duration, priority, due_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                title.strip(),
                notes.strip(),
                duration,
                priority,
                due_date.isoformat() if due_date else None,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def get_tasks(include_completed=False):
    query = "SELECT * FROM tasks"
    if not include_completed:
        query += " WHERE completed = 0"
    query += " ORDER BY id DESC"
    with connect_db() as conn:
        return conn.execute(query).fetchall()


def set_completed(task_id, completed):
    with connect_db() as conn:
        conn.execute("UPDATE tasks SET completed = ? WHERE id = ?", (int(completed), task_id))


def delete_task(task_id):
    with connect_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def schedule_score(task, today):
    """Higher scores go earlier: priority, urgency, then shorter tasks."""
    priority_points = {"High": 40, "Medium": 20, "Low": 0}[task["priority"]]
    urgency_points = 0
    if task["due_date"]:
        days_left = (date.fromisoformat(task["due_date"]) - today).days
        if days_left < 0:
            urgency_points = 60  # overdue
        elif days_left == 0:
            urgency_points = 50  # due today
        elif days_left == 1:
            urgency_points = 35
        elif days_left <= 3:
            urgency_points = 20
        elif days_left <= 7:
            urgency_points = 10
    # Small tie-breaker that favors a task that can be finished sooner.
    duration_points = max(0, 10 - task["duration"] // 15)
    return priority_points + urgency_points + duration_points


def make_schedule(tasks, start_at, finish_at, break_minutes, today):
    ordered = sorted(tasks, key=lambda task: schedule_score(task, today), reverse=True)
    current = datetime.combine(today, start_at)
    end = datetime.combine(today, finish_at)
    plan = []
    skipped = []

    for task in ordered:
        task_end = current + timedelta(minutes=task["duration"])
        if task_end <= end:
            plan.append((task, current, task_end, schedule_score(task, today)))
            current = task_end + timedelta(minutes=break_minutes)
        else:
            skipped.append(task)
    return plan, skipped


st.set_page_config(page_title="Smart Task Scheduler", page_icon="🗓️", layout="wide")
init_db()
st.title("🗓️ Smart Task Manager")
st.caption("Add tasks, then get a suggested day plan based on priority, deadlines, and task length.")

with st.sidebar:
    st.header("Add a task")
    with st.form("add_task_form", clear_on_submit=True):
        title = st.text_input("Task name", placeholder="Example: Finish my statistics practice")
        notes = st.text_area("Notes (optional)")
        duration = st.number_input("Estimated time (minutes)", min_value=5, max_value=600, value=30, step=5)
        priority = st.selectbox("Priority", ["High", "Medium", "Low"])
        has_due_date = st.checkbox("Add a deadline")
        due_date = st.date_input("Deadline", value=date.today(), disabled=not has_due_date)
        submitted = st.form_submit_button("Save task", use_container_width=True)
        if submitted:
            if not title.strip():
                st.error("Enter a task name first.")
            else:
                add_task(title, notes, int(duration), priority, due_date if has_due_date else None)
                st.success("Task saved.")
                st.rerun()

left, right = st.columns([1, 1.2], gap="large")
with left:
    st.subheader("Your open tasks")
    tasks = get_tasks()
    if not tasks:
        st.info("No open tasks yet. Add one from the left panel.")
    else:
        for task in tasks:
            deadline = task["due_date"] or "No deadline"
            with st.container(border=True):
                top = st.columns([0.09, 0.72, 0.19])
                done = top[0].checkbox("Done", key=f"done_{task['id']}", label_visibility="collapsed")
                top[1].markdown(f"**{task['title']}**  ·  {task['priority']} priority")
                top[2].caption(f"{task['duration']} min")
                if done:
                    set_completed(task["id"], True)
                    st.rerun()
                st.caption(f"Deadline: {deadline}" + (f"  ·  {task['notes']}" if task["notes"] else ""))
                if st.button("Delete", key=f"delete_{task['id']}"):
                    delete_task(task["id"])
                    st.rerun()

with right:
    st.subheader("Build today's schedule")
    st.write("Choose your available time. The app ranks tasks with higher priority and nearer deadlines first.")
    controls = st.columns(2)
    with controls[0]:
        start_at = st.time_input("Start time", value=time(9, 0), key="start_time")
    with controls[1]:
        finish_at = st.time_input("Finish time", value=time(17, 0), key="finish_time")
    break_minutes = st.number_input("Break after each task (minutes)", min_value=0, max_value=60, value=10, step=5)

    if st.button("Suggest my schedule", type="primary", use_container_width=True):
        if finish_at <= start_at:
            st.error("Finish time must be later than start time.")
        elif not tasks:
            st.info("Add at least one open task first.")
        else:
            plan, skipped = make_schedule(tasks, start_at, finish_at, int(break_minutes), date.today())
            if plan:
                st.markdown("### Suggested plan")
                for task, begins, ends, score in plan:
                    due = f" · due {task['due_date']}" if task["due_date"] else ""
                    st.markdown(
                        f"**{begins.strftime('%I:%M %p')}–{ends.strftime('%I:%M %p')}**  "
                        f"{task['title']} · {task['priority']} priority{due}"
                    )
                if skipped:
                    st.warning(
                        f"{len(skipped)} task(s) did not fit in this time window: "
                        + ", ".join(task["title"] for task in skipped)
                    )
            else:
                st.warning("No tasks fit in that time window. Try a longer day or shorter task estimates.")

with st.expander("Completed tasks"):
    completed_tasks = [task for task in get_tasks(include_completed=True) if task["completed"]]
    if not completed_tasks:
        st.caption("Completed tasks will appear here.")
    else:
        for task in completed_tasks:
            row = st.columns([0.75, 0.2, 0.15])
            row[0].write(f"✅ {task['title']}")
            row[1].caption(f"{task['duration']} min")
            if row[2].button("Reopen", key=f"reopen_{task['id']}"):
                set_completed(task["id"], False)
                st.rerun()

st.divider()
st.caption("Scheduling is transparent rule-based prioritization. Your tasks stay in a local SQLite file beside this script.")

