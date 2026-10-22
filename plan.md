## Target Environment: Linux with herbstluftwm

The primary target environment is a Linux desktop running **herbstluftwm**, a lightweight tiling window manager.

Do not assume that GNOME, KDE Plasma, Cinnamon, XFCE, or another complete desktop environment is installed.

Prioritize compatibility with a minimal Linux desktop setup.

### 1. Desktop Notifications

Use `notify-send` as the initial notification interface, provided a compatible notification daemon is running.

Before implementing notification integration:

- Check whether `notify-send` is installed.
- Check whether a notification daemon is available in the current user session.
- Do not assume that installing `notify-send` automatically provides a notification daemon.
- Handle missing notification infrastructure gracefully.
- Document how to diagnose notification failures.

Keep the notification implementation independent of the window manager.

Do not introduce a custom notification window or GUI framework for the initial release.

### 2. Notification Daemon Compatibility

The application must not depend on a specific desktop environment.

It should work with a compatible notification daemon that supports the standard desktop notification interface.

If notification delivery fails, log a useful diagnostic message and preserve the scheduler's operation.

Do not repeatedly spawn failing notification processes in a tight loop.

At startup, check whether `notify-send` is installed, but do not send a visible test notification. Check daemon and session-bus availability as part of the implementation environment review; at runtime, treat the result of an actual scheduled delivery as the definitive availability check.

Attempt each scheduled notification once. If delivery fails, log an actionable diagnostic, keep the scheduler running, and do not retry that same reminder. Retry only at a later scheduled occurrence. Rate-limit repeated identical failure messages and report when delivery recovers.

### 3. herbstluftwm Startup Integration

Support automatic startup within the user's herbstluftwm session.

Provide an optional startup command that can be added to the user's existing herbstluftwm autostart configuration.

For example, the documented integration may use:

```bash
systemctl --user start linguapulse.service
```

Do not overwrite or replace the user's existing autostart file.

Before suggesting changes, inspect the existing configuration when access to the environment is available.

Provide a manual installation procedure and explain how to undo the change.

If the service is already enabled independently, avoid starting duplicate application instances.

### 4. systemd User Service

Use a `systemd --user` service for background scheduling and lifecycle management.

However, do not assume that a running user service automatically has access to the graphical notification session.

Ensure that the service can access the relevant user-session environment when desktop notifications are required.

Document how to diagnose environment-related notification failures.

Do not hardcode session-specific environment values without checking whether they are needed.

### 5. Terminal-First Workflow

The CLI is a first-class interface.

The following commands must work without requiring a graphical interface:

```bash
linguapulse show
linguapulse next
linguapulse history
linguapulse status
linguapulse validate
```

Terminal output must correctly handle:

- Arabic text.
- English, French, Spanish, and Turkish text.
- Simplified Chinese characters.
- Chinese Pinyin with tone marks.

Do not assume that every terminal font supports Arabic and Chinese.

Document any relevant font or locale requirements.

### 6. Minimal Dependencies

Keep the application lightweight and appropriate for a tiling-window-manager workflow.

Do not add:

- A system tray application.
- A graphical settings window.
- An Electron frontend.
- A web server.
- A background database server.
- A dependency on a complete desktop environment.

Use Python, local JSON files, the standard Linux notification infrastructure, and systemd user services.

### 7. Startup and Shutdown Behavior

The application must not require an interactive terminal to remain open.

It should start and stop cleanly through systemd or the user's existing session-management workflow.

Do not start duplicate schedulers when the user logs in or reloads the window manager configuration.

If desktop notifications are unavailable, preserve CLI functionality and provide clear diagnostic output.

### 8. Acceptance Criteria for herbstluftwm

- [ ] The application works without GNOME, KDE, or Cinnamon.
- [ ] CLI commands work in a terminal session.
- [ ] Desktop notifications work when a compatible notification daemon is available.
- [ ] Missing notification infrastructure produces an actionable diagnostic.
- [ ] The application can start from herbstluftwm's existing autostart workflow.
- [ ] Existing user configuration is preserved.
- [ ] The background service does not create duplicate schedulers.
- [ ] No graphical interface is required.
- [ ] All language and Unicode requirements remain satisfied.
- [ ] Scheduling uses the system's local timezone and behaves consistently across daylight-saving transitions.
- [ ] Resume/restart catch-up follows the missed-reminder policy in section 9 without replaying a backlog.
- [ ] The scheduler wakes no more than once per due card, with no periodic polling loop (see the wakeup policy in section 9).

### 9. Scheduling and Missed Reminders

- Use the system's local timezone and local wall-clock time for schedules, including across daylight-saving transitions.
- After wake or service restart, send only the latest overdue reminder if it is no more than 15 minutes late. Otherwise, skip missed reminders and wait for the next scheduled occurrence.
- Never replay a backlog of missed reminders.
- Persist the identity of the last delivered occurrence so a service restart cannot send it twice.

#### Wakeup Policy

- The scheduler sleeps until the exact due time of the next card. It computes the remaining delay to the next due card and sleeps for that duration.
- Do not run a periodic polling loop. A background thread that wakes on a fixed interval to check for due cards is not permitted.
- The number of process wakeups must not exceed the number of due cards. Each due card produces at most one wakeup.
- Recompute the sleep target after every delivery so that a newly scheduled card is picked up without an extra wakeup.

### 10. Git Workflow

- Before implementation work, verify the project is a Git repository and inspect the current branch and working-tree status.
- If Git has not been initialized, obtain explicit approval to initialize the repository and establish a baseline before beginning implementation work.
- Before each task, create a fresh descriptive branch from the intended base branch. Do not make task changes directly on `main`/`master` or an unrelated branch.
- Preserve pre-existing user changes; do not overwrite or include them unintentionally.
- Run the relevant checks, then review the final diff and working-tree status before reporting completion.
- Commit, push, or open a pull request only when explicitly requested. Do not delete branches during or after merge operations.
