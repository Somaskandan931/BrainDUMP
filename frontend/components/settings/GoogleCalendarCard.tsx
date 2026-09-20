"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { calendarApi } from "@/services/api";
import { GoogleCalendarStatus } from "@/services/types";
import { friendlyApiError } from "@/lib/format";

type Notice = { tone: "success" | "error"; text: string } | null;

/**
 * Settings section for the signed-in user's own Google Calendar connection
 * (backend/api/calendar.py). Connecting sends the browser through Google's
 * consent screen; the backend callback then redirects back here with
 * ?calendar=connected or ?calendar=error, which is read once and cleared.
 */
export function GoogleCalendarCard() {
  const [status, setStatus] = useState<GoogleCalendarStatus | null>(null);
  const [busy, setBusy] = useState<"connect" | "disconnect" | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await calendarApi.googleStatus());
    } catch (err) {
      setNotice({ tone: "error", text: friendlyApiError(err, "Couldn't load calendar status.") });
    }
  }, []);

  useEffect(() => {
    // Read the callback's outcome once, then strip it so a reload doesn't repeat it.
    const params = new URLSearchParams(window.location.search);
    const outcome = params.get("calendar");
    if (outcome === "connected") {
      setNotice({ tone: "success", text: "Google Calendar connected." });
    } else if (outcome === "error") {
      setNotice({
        tone: "error",
        text: "Google Calendar wasn't connected. Try again, and make sure you approve calendar access.",
      });
    }
    if (outcome) {
      params.delete("calendar");
      const query = params.toString();
      window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : ""));
    }
    void refresh();
  }, [refresh]);

  const connect = async () => {
    setBusy("connect");
    setNotice(null);
    try {
      const { authorization_url } = await calendarApi.googleConnect();
      window.location.assign(authorization_url); // leaves the app; the callback brings the user back
    } catch (err) {
      setBusy(null);
      setNotice({ tone: "error", text: friendlyApiError(err, "Couldn't start the Google connection.") });
    }
  };

  const disconnect = async () => {
    setBusy("disconnect");
    setNotice(null);
    try {
      await calendarApi.googleDisconnect();
      setNotice({ tone: "success", text: "Google Calendar disconnected." });
      await refresh();
    } catch (err) {
      setNotice({ tone: "error", text: friendlyApiError(err, "Couldn't disconnect.") });
    } finally {
      setBusy(null);
    }
  };

  const connected = status?.connected ?? false;
  const unavailable = status !== null && !status.oauth_client_configured;

  return (
    <Card>
      <CardHeader
        eyebrow="Integrations"
        title="Google Calendar"
        action={connected ? <Badge tone="primary">Connected</Badge> : undefined}
      />
      <p className="mb-3 text-[13px] text-ink-muted">
        Connect your own Google account so the scheduler plans around your real meetings and
        classes, and your focus sessions show up on your phone calendar. Each account connects
        separately; disconnecting removes the imported events (sessions Brain Dump created are
        kept).
      </p>

      {unavailable && (
        <p className="mb-3 text-[12px] text-ink-muted">
          Calendar sync isn&rsquo;t set up on this server yet — the administrator needs to
          configure a Google OAuth client (see INTEGRATIONS.md).
        </p>
      )}

      {notice && (
        <p
          role="status"
          className={`mb-3 text-[12px] ${notice.tone === "error" ? "text-red-500" : "text-ink-muted"}`}
        >
          {notice.text}
        </p>
      )}

      <div className="flex gap-2">
        {connected ? (
          <Button variant="danger" loading={busy === "disconnect"} onClick={disconnect}>
            Disconnect
          </Button>
        ) : (
          <Button
            variant="primary"
            loading={busy === "connect"}
            disabled={status === null || unavailable}
            onClick={connect}
          >
            {busy !== "connect" && <CalendarDays size={14} />}
            Connect Google Calendar
          </Button>
        )}
      </div>
    </Card>
  );
}
