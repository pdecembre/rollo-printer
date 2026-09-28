# Rollo X1040USB copy-control solution

## Summary

The printer is effectively ignoring the GUI print dialog's copy count for this queue, while the command-line override works:

```bash
lpoptions -p Rollo_X1040USB -o copies=3
```

That means the reliable control point is the CUPS queue default, not the application print dialog. The safest fix is a small tray application that sets the CUPS default copy count before printing and restores it to 1 after printing finishes.

## Recommended architecture

### 1) Python tray app
Use a lightweight desktop app with a system tray icon and a menu.

Features:
- Show current default number of copies
- Allow user to pick preset values like 1, 2, 3, 4, 5, 10
- Allow user to enter a custom number via a menu action labeled `# of pages to print`
- Reset to 1 with one click
- Run quietly in the background
- Start automatically after login and reboot

### 2) CUPS integration
Use the queue option that is already proven to work:

```bash
lpoptions -p Rollo_X1040USB -o copies=3
```

and reset it with:

```bash
lpoptions -p Rollo_X1040USB -o copies=1
```

This is the layer that controls the default copy count for the queue.

### 3) Queue watchdog
The app should not reset the print count immediately after setting it. Instead it should:
- start a job with a chosen copy count
- watch `lpstat` or the queue state
- wait until there are no active jobs for `Rollo_X1040USB`
- then reset the default back to 1

This keeps the app from resetting mid-job.

## Why this approach is the right fit

- The actual queue override is already known to work.
- The app avoids fighting the broken GUI behavior.
- The user experience is simple: choose copy count once, print, let the app restore the default afterward.
- The app can be kept running in the background without user intervention.

## Persistence and lifecycle

### Recommended service model
Run the app as a per-user service:

- `systemd --user` service
- desktop autostart launcher as fallback
- `loginctl enable-linger $USER` to survive logout/reboot

This makes it behave like a background tool that stays available without requiring the user to start it manually.

## High-level flow

1. User opens tray menu.
2. User selects copy count, e.g. 3.
3. App executes:
   ```bash
   lpoptions -p Rollo_X1040USB -o copies=3
   ```
4. User prints normally from the application.
5. App monitors queue activity.
6. When all jobs for this printer stop, it executes:
   ```bash
   lpoptions -p Rollo_X1040USB -o copies=1
   ```
7. The tray UI updates to show the value is back to 1.

## Implementation path

### Phase 1: validate behavior
Verify on the laptop:

```bash
lpoptions -p Rollo_X1040USB -o copies=3
lpstat -p Rollo_X1040USB
```

and then test a real print to confirm the copy count is honored when set via this route.

### Phase 2: build tray app
Create a Python app with:
- tray icon
- menu actions
- copy count selection
- subprocess calls to CUPS commands
- polling loop using `lpstat`

### Phase 3: persist app at startup
Add:
- unit file in `~/.config/systemd/user/`
- autostart `.desktop` entry in `~/.config/autostart/`
- service enablement and lingering

### Phase 4: test end-to-end
Check:
- app launches after login
- tray icon appears
- setting 3 copies works
- printing uses 3 copies
- queue clears and app resets to 1
- reboot keeps the app running

## Suggested technology choices

### Python packages
- `PySide6` or `PyQt6` for tray UI
- no heavy dependencies beyond Qt and standard library

### Linux integration
- `systemd --user`
- shell commands via `subprocess`
- `lpstat` for print state

## Final recommendation

Build a small user-level tray utility that wraps the working CUPS command rather than trying to rewire the print dialog. This directly addresses the root cause and gives the user a reliable, mostly invisible helper that survives reboots and does not need ongoing support.

---

## Example command flow

```bash
# Set queue default to 3 copies
lpoptions -p Rollo_X1040USB -o copies=3

# Reset to default 1 copy after work is done
lpoptions -p Rollo_X1040USB -o copies=1

# Check current queue state
lpstat -p Rollo_X1040USB
```

This is the foundation the tray app will automate for the user.
